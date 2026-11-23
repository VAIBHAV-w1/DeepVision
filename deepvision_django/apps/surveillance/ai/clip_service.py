"""
DeepVision Genuine CLIP Scene Understanding Service.

Provides:
  - Configurable, lazily-loaded OpenAI CLIP (default: openai/clip-vit-base-patch32)
    via Hugging Face Transformers (primary) or OpenCLIP (optional backend).
  - Automatic compatible hardware detection (CUDA / XPU / MPS / CPU fallback; never assumes CUDA).
  - OpenCV BGR frame preprocessing -> RGB PIL conversion -> L2-normalized image & text embeddings.
  - Precomputed/cached normalized text embeddings for configurable scene descriptions.
  - Explicit separation between raw cosine similarity scores (`cosine_similarity`) and
    candidate-set relative softmax (`relative_candidate_score`, NOT a calibrated probability).
  - Controlled non-blocking background scheduling (`ClipSceneScheduler`) with bounded
    per-camera frame slots, cooldown deduplication, and schema-safe forensic logging.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_NAME = "openai/clip-vit-base-patch32"
_MAX_SCENE_EVENTS = 250
_MAX_PROMPTS = 24

DEFAULT_SCENE_DESCRIPTIONS: List[Dict[str, Any]] = [
    {"id": "restricted_area", "prompt": "Person in a restricted area.", "security_relevant": True, "severity": "high"},
    {"id": "entrance_person", "prompt": "Person near an entrance.", "security_relevant": True, "severity": "low"},
    {"id": "crowd_gathering", "prompt": "Crowd gathering.", "security_relevant": True, "severity": "medium"},
    {"id": "vehicle_restricted", "prompt": "Vehicle in a restricted zone.", "security_relevant": True, "severity": "high"},
    {"id": "unusual_activity", "prompt": "Unusual activity.", "security_relevant": True, "severity": "medium"},
    {"id": "unattended_object", "prompt": "Possible unattended object.", "security_relevant": True, "severity": "medium"},
    {"id": "empty_scene", "prompt": "Empty scene.", "security_relevant": False, "severity": "low"},
    {"id": "normal_outdoor", "prompt": "Normal outdoor activity.", "security_relevant": False, "severity": "low"},
]


def _default_clip_enabled() -> bool:
    raw = os.getenv("DEEPVISION_CLIP_ENABLED")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if os.getenv("RENDER") or os.getenv("VERCEL"):
        return False
    return _probe_runtime_packages().get("any_available", False)


def _get_clip_config_path() -> str:
    override = (os.getenv("DEEPVISION_CLIP_CONFIG_PATH") or "").strip()
    if override:
        os.makedirs(os.path.dirname(os.path.abspath(override)), exist_ok=True)
        return override
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "instance"))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "clip_scene_config.json")


def _get_clip_events_path() -> str:
    override = (os.getenv("DEEPVISION_CLIP_EVENTS_PATH") or "").strip()
    if override:
        os.makedirs(os.path.dirname(os.path.abspath(override)), exist_ok=True)
        return override
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "instance"))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "clip_scene_events.json")


def _get_clip_cache_dir() -> str:
    override = (os.getenv("DEEPVISION_CLIP_CACHE_DIR") or "").strip()
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "models", "clip_cache"))
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _probe_runtime_packages() -> Dict[str, Any]:
    """Safely probes available Python ML packages via find_spec without heavy imports or weight loading."""
    import importlib.util
    import sys

    cv2_ok = importlib.util.find_spec("cv2") is not None
    pil_ok = importlib.util.find_spec("PIL") is not None
    torch_ok = importlib.util.find_spec("torch") is not None
    transformers_ok = importlib.util.find_spec("transformers") is not None
    open_clip_ok = importlib.util.find_spec("open_clip") is not None

    device = "cpu"
    device_detail = "CPU"
    torch_ver = None
    transformers_ver = None

    # Only query live torch device if torch is already imported in process (never force-import ~400MB at probe time)
    if torch_ok and "torch" in sys.modules:
        torch = sys.modules["torch"]
        torch_ver = str(getattr(torch, "__version__", "installed"))
        try:
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                device = "cuda"
                try:
                    device_detail = torch.cuda.get_device_name(0)
                except Exception:
                    device_detail = "CUDA GPU"
            elif hasattr(torch, "xpu") and torch.xpu.is_available():
                device = "xpu"
                device_detail = "Intel XPU"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
                device_detail = "Apple MPS"
        except Exception:
            device = "cpu"
            device_detail = "CPU"

    if transformers_ok and "transformers" in sys.modules:
        transformers_ver = str(getattr(sys.modules["transformers"], "__version__", "installed"))

    return {
        "torch_available": torch_ok,
        "torch_version": torch_ver,
        "transformers_available": transformers_ok,
        "transformers_version": transformers_ver,
        "open_clip_available": open_clip_ok,
        "pil_available": pil_ok,
        "cv2_available": cv2_ok,
        "any_available": bool(torch_ok and pil_ok and (transformers_ok or open_clip_ok)),
        "selected_device": device,
        "device_detail": device_detail,
    }


def sanitize_scene_descriptions(raw_items: Any) -> List[Dict[str, Any]]:
    """Normalizes configurable scene description entries safely."""
    if not isinstance(raw_items, list):
        return [dict(item) for item in DEFAULT_SCENE_DESCRIPTIONS]

    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for idx, item in enumerate(raw_items[:_MAX_PROMPTS]):
        if isinstance(item, str):
            prompt = " ".join(item.split()).strip()[:180]
            if not prompt:
                continue
            low = prompt.lower()
            if low in seen:
                continue
            seen.add(low)
            is_routine = low.startswith(("empty scene", "normal "))
            cleaned.append({
                "id": f"scene_{idx + 1}",
                "prompt": prompt,
                "security_relevant": not is_routine,
                "severity": "low" if is_routine else "medium",
            })
        elif isinstance(item, dict):
            prompt = " ".join(str(item.get("prompt") or item.get("text") or "").split()).strip()[:180]
            if not prompt:
                continue
            low = prompt.lower()
            if low in seen:
                continue
            seen.add(low)
            raw_id = str(item.get("id") or f"scene_{idx + 1}").strip()[:48] or f"scene_{idx + 1}"
            sev = str(item.get("severity") or "medium").strip().lower()
            if sev not in ("critical", "high", "medium", "low"):
                sev = "medium"
            cleaned.append({
                "id": raw_id,
                "prompt": prompt,
                "security_relevant": bool(item.get("security_relevant", not low.startswith(("empty scene", "normal ")))),
                "severity": sev,
            })

    return cleaned if cleaned else [dict(item) for item in DEFAULT_SCENE_DESCRIPTIONS]


def _default_config_dict() -> Dict[str, Any]:
    interval = max(1.5, min(120.0, float(os.getenv("DEEPVISION_CLIP_INTERVAL_SEC", "5.0") or 5.0)))
    cos_thr = max(0.10, min(0.60, float(os.getenv("DEEPVISION_CLIP_COSINE_THRESHOLD", "0.24") or 0.24)))
    cooldown = max(10.0, min(600.0, float(os.getenv("DEEPVISION_CLIP_COOLDOWN_SEC", "60.0") or 60.0)))
    backend = (os.getenv("DEEPVISION_CLIP_BACKEND") or "auto").strip().lower()
    if backend not in ("auto", "transformers", "open_clip"):
        backend = "auto"
    model_name = (os.getenv("DEEPVISION_CLIP_MODEL") or _DEFAULT_MODEL_NAME).strip() or _DEFAULT_MODEL_NAME
    return {
        "enabled": _default_clip_enabled(),
        "backend": backend,
        "model_name": model_name,
        "device_preference": (os.getenv("DEEPVISION_CLIP_DEVICE") or "auto").strip().lower() or "auto",
        "analysis_interval_seconds": interval,
        "cosine_threshold": cos_thr,
        "alert_cooldown_seconds": cooldown,
        "create_alerts_from_scene": str(os.getenv("DEEPVISION_CLIP_EMIT_ALERTS", "false")).strip().lower() in ("1", "true", "yes"),
        "scene_descriptions": [dict(d) for d in DEFAULT_SCENE_DESCRIPTIONS],
        "updated_at": None,
    }


def _extract_tensor(out: Any):
    import torch

    if isinstance(out, torch.Tensor):
        return out
    if hasattr(out, "image_embeds") and out.image_embeds is not None:
        return out.image_embeds
    if hasattr(out, "text_embeds") and out.text_embeds is not None:
        return out.text_embeds
    if hasattr(out, "pooler_output") and out.pooler_output is not None:
        return out.pooler_output
    if isinstance(out, (tuple, list)) and out:
        return out[0]
    raise TypeError(f"Unsupported CLIP output type: {type(out)}")


class ClipSceneAnalyzer:
    """
    Singleton-friendly lazy CLIP scene analyzer with cached normalized text embeddings
    and atomic runtime reconfiguration.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._model = None
        self._processor = None
        self._open_clip_preprocess = None
        self._open_clip_tokenizer = None
        self._active_backend: Optional[str] = None
        self._active_model_name: Optional[str] = None
        self._active_device: str = "cpu"
        self._load_error: Optional[str] = None
        self._model_load_count: int = 0
        self._text_cache_key: Optional[Tuple[Any, ...]] = None
        self._text_features = None
        self._text_cache_hits: int = 0
        self._text_cache_misses: int = 0
        self._config: Dict[str, Any] = self._load_persisted_config()

    def _load_persisted_config(self) -> Dict[str, Any]:
        cfg = _default_config_dict()
        path = _get_clip_config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    saved = json.load(fh)
                if isinstance(saved, dict):
                    raw_env = os.getenv("DEEPVISION_CLIP_ENABLED")
                    if raw_env is None or str(raw_env).strip() == "":
                        if "enabled" in saved:
                            cfg["enabled"] = bool(saved["enabled"])
                    if isinstance(saved.get("backend"), str) and saved["backend"].strip().lower() in ("auto", "transformers", "open_clip"):
                        cfg["backend"] = saved["backend"].strip().lower()
                    if isinstance(saved.get("model_name"), str) and saved["model_name"].strip():
                        cfg["model_name"] = saved["model_name"].strip()[:120]
                    if "analysis_interval_seconds" in saved:
                        cfg["analysis_interval_seconds"] = max(1.5, min(120.0, float(saved["analysis_interval_seconds"])))
                    if "cosine_threshold" in saved:
                        cfg["cosine_threshold"] = max(0.10, min(0.60, float(saved["cosine_threshold"])))
                    if "alert_cooldown_seconds" in saved:
                        cfg["alert_cooldown_seconds"] = max(10.0, min(600.0, float(saved["alert_cooldown_seconds"])))
                    if "create_alerts_from_scene" in saved:
                        cfg["create_alerts_from_scene"] = bool(saved["create_alerts_from_scene"])
                    if "scene_descriptions" in saved:
                        cfg["scene_descriptions"] = sanitize_scene_descriptions(saved["scene_descriptions"])
                    cfg["updated_at"] = saved.get("updated_at")
            except Exception as exc:
                logger.warning(f"[CLIP_CONFIG_LOAD_WARN] {exc}")
        return cfg

    def _persist_config(self) -> None:
        path = _get_clip_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp.{threading.get_ident()}"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(self._config, fh, indent=2)
        os.replace(tmp_path, path)

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._config,
                "scene_descriptions": [dict(d) for d in self._config.get("scene_descriptions", [])],
            }

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(updates, dict):
            return self.get_config()
        reset_model = False
        invalidate_text = False
        with self._lock:
            if "enabled" in updates:
                self._config["enabled"] = bool(updates["enabled"])
            if "backend" in updates:
                b = str(updates["backend"] or "").strip().lower()
                if b in ("auto", "transformers", "open_clip") and b != self._config["backend"]:
                    self._config["backend"] = b
                    reset_model = True
            if "model_name" in updates:
                m = str(updates["model_name"] or "").strip()[:120]
                if m and m != self._config["model_name"]:
                    self._config["model_name"] = m
                    reset_model = True
            if "analysis_interval_seconds" in updates:
                self._config["analysis_interval_seconds"] = max(1.5, min(120.0, float(updates["analysis_interval_seconds"])))
            if "cosine_threshold" in updates:
                self._config["cosine_threshold"] = max(0.10, min(0.60, float(updates["cosine_threshold"])))
            if "alert_cooldown_seconds" in updates:
                self._config["alert_cooldown_seconds"] = max(10.0, min(600.0, float(updates["alert_cooldown_seconds"])))
            if "create_alerts_from_scene" in updates:
                self._config["create_alerts_from_scene"] = bool(updates["create_alerts_from_scene"])
            if "scene_descriptions" in updates:
                self._config["scene_descriptions"] = sanitize_scene_descriptions(updates["scene_descriptions"])
                invalidate_text = True
            self._config["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._persist_config()

            if reset_model:
                self._model = None
                self._processor = None
                self._open_clip_preprocess = None
                self._open_clip_tokenizer = None
                self._active_backend = None
                self._active_model_name = None
                self._load_error = None
                invalidate_text = True
            if invalidate_text:
                self._text_cache_key = None
                self._text_features = None
            return self.get_config()

    def get_status(self) -> Dict[str, Any]:
        env_probe = _probe_runtime_packages()
        with self._lock:
            enabled = bool(self._config.get("enabled", False))
            loaded = self._model is not None
            err = self._load_error
            if not enabled:
                status = "disabled_by_config"
            elif err:
                status = "error"
            elif loaded:
                status = "ready"
            elif not env_probe["any_available"]:
                status = "unavailable_missing_runtime"
            else:
                status = "standby_lazy"
            return {
                "enabled": enabled,
                "available": bool(env_probe["any_available"] and not err),
                "loaded": loaded,
                "status": status,
                "backend": self._active_backend or self._config.get("backend", "auto"),
                "model_name": self._active_model_name or self._config.get("model_name", _DEFAULT_MODEL_NAME),
                "device": self._active_device if loaded else env_probe["selected_device"],
                "device_detail": env_probe["device_detail"],
                "model_load_count": self._model_load_count,
                "text_cache_hits": self._text_cache_hits,
                "text_cache_misses": self._text_cache_misses,
                "load_error": err,
                "runtime_packages": {
                    "torch": env_probe["torch_available"],
                    "transformers": env_probe["transformers_available"],
                    "open_clip": env_probe["open_clip_available"],
                },
                "analysis_interval_seconds": self._config.get("analysis_interval_seconds", 5.0),
                "cosine_threshold": self._config.get("cosine_threshold", 0.24),
                "scene_descriptions_count": len(self._config.get("scene_descriptions", [])),
            }

    def _resolve_target_device(self, env_probe: Dict[str, Any]) -> str:
        pref = str(self._config.get("device_preference") or "auto").lower()
        if pref == "cpu":
            return "cpu"
        try:
            import torch
            if pref in ("auto", "cuda") and hasattr(torch, "cuda") and torch.cuda.is_available():
                return "cuda"
            if pref in ("auto", "xpu") and hasattr(torch, "xpu") and torch.xpu.is_available():
                return "xpu"
            if pref in ("auto", "mps") and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    def ensure_loaded(self, local_files_only: bool = False) -> Tuple[bool, str]:
        """Lazily loads the configured CLIP model once under lock."""
        with self._lock:
            if not self._config.get("enabled", False):
                return False, "CLIP scene understanding is disabled by configuration."
            if self._model is not None:
                return True, "ok"

            env_probe = _probe_runtime_packages()
            if not env_probe["any_available"]:
                self._load_error = "CLIP runtime packages (torch + transformers or open_clip) are not installed."
                return False, self._load_error

            req_backend = str(self._config.get("backend") or "auto").lower()
            if req_backend == "auto":
                chosen_backend = "transformers" if env_probe["transformers_available"] else "open_clip"
            elif req_backend == "transformers" and env_probe["transformers_available"]:
                chosen_backend = "transformers"
            elif req_backend == "open_clip" and env_probe["open_clip_available"]:
                chosen_backend = "open_clip"
            else:
                self._load_error = f"Requested CLIP backend '{req_backend}' is not installed."
                return False, self._load_error

            model_name = str(self._config.get("model_name") or _DEFAULT_MODEL_NAME)
            target_device = self._resolve_target_device(env_probe)
            cache_dir = _get_clip_cache_dir()
            local_only = bool(local_files_only or os.getenv("DEEPVISION_CLIP_OFFLINE", "").strip().lower() in ("1", "true"))

            try:
                t0 = time.perf_counter()
                if chosen_backend == "transformers":
                    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
                    from transformers import CLIPModel, CLIPProcessor
                    # Always prefer cached local weights first so offline hosts never stall on HF Hub network checks.
                    try:
                        model = CLIPModel.from_pretrained(model_name, cache_dir=cache_dir, local_files_only=True)
                        proc = CLIPProcessor.from_pretrained(model_name, cache_dir=cache_dir, local_files_only=True)
                    except Exception:
                        if local_only:
                            raise
                        model = CLIPModel.from_pretrained(model_name, cache_dir=cache_dir, local_files_only=False)
                        proc = CLIPProcessor.from_pretrained(model_name, cache_dir=cache_dir, local_files_only=False)
                    model.to(target_device)
                    model.eval()
                    self._model = model
                    self._processor = proc
                    self._open_clip_preprocess = None
                    self._open_clip_tokenizer = None
                else:
                    import open_clip
                    arch = "ViT-B-32" if "vit-base-patch32" in model_name.lower() else model_name
                    pretrained = os.getenv("DEEPVISION_OPENCLIP_PRETRAINED", "openai")
                    model, _, preprocess = open_clip.create_model_and_transforms(
                        arch, pretrained=pretrained, device=target_device, cache_dir=cache_dir
                    )
                    model.eval()
                    self._model = model
                    self._processor = None
                    self._open_clip_preprocess = preprocess
                    self._open_clip_tokenizer = open_clip.get_tokenizer(arch)

                self._active_backend = chosen_backend
                self._active_model_name = model_name
                self._active_device = target_device
                self._load_error = None
                self._model_load_count += 1
                self._text_cache_key = None
                self._text_features = None
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                logger.info(
                    "[CLIP_LOADED] backend=%s model=%s device=%s load_ms=%.1f load_count=%d",
                    chosen_backend,
                    model_name,
                    target_device,
                    elapsed_ms,
                    self._model_load_count,
                )
                return True, "ok"
            except Exception as exc:
                self._model = None
                self._processor = None
                self._load_error = f"CLIP model initialization failed: {exc}"
                logger.warning("[CLIP_LOAD_FAILED] model=%s err=%s", model_name, exc)
                return False, self._load_error

    def _get_cached_text_embeddings(self, descriptions: List[Dict[str, Any]]):
        import torch

        prompts = tuple(d["prompt"] for d in descriptions)
        cache_key = (self._active_backend, self._active_model_name, self._active_device, prompts)
        if self._text_features is not None and self._text_cache_key == cache_key:
            self._text_cache_hits += 1
            return self._text_features, True

        with torch.inference_mode():
            if self._active_backend == "transformers":
                inputs = self._processor(text=list(prompts), return_tensors="pt", padding=True)
                inputs = {k: v.to(self._active_device) for k, v in inputs.items()}
                raw_tf = self._model.get_text_features(**inputs)
                tf = _extract_tensor(raw_tf)
            else:
                tokens = self._open_clip_tokenizer(list(prompts)).to(self._active_device)
                tf = self._model.encode_text(tokens)
            tf = tf / tf.norm(dim=-1, keepdim=True).clamp(min=1e-12)

        self._text_cache_key = cache_key
        self._text_features = tf
        self._text_cache_misses += 1
        return tf, False

    def analyze_bgr_frame(
        self,
        bgr_frame: Any,
        *,
        descriptions: Optional[List[Dict[str, Any]]] = None,
        cosine_threshold: Optional[float] = None,
        local_files_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs genuine CLIP image/text cosine-similarity analysis on an OpenCV BGR frame.
        Always returns explicit structured status (`disabled`, `unavailable`, `error`, or `analyzed`).
        """
        t_total0 = time.perf_counter()
        if bgr_frame is None or getattr(bgr_frame, "size", 0) == 0:
            return {
                "available": False,
                "analyzed": False,
                "status": "invalid_frame",
                "error": "Empty or invalid frame provided.",
                "top_matches": [],
            }

        with self._lock:
            if not self._config.get("enabled", False):
                return {
                    "available": False,
                    "analyzed": False,
                    "status": "disabled_by_config",
                    "model_name": self._config.get("model_name", _DEFAULT_MODEL_NAME),
                    "top_matches": [],
                }
            active_descriptions = sanitize_scene_descriptions(descriptions) if descriptions is not None else list(
                self._config.get("scene_descriptions") or DEFAULT_SCENE_DESCRIPTIONS
            )
            thr = float(cosine_threshold if cosine_threshold is not None else self._config.get("cosine_threshold", 0.24))

        ok, msg = self.ensure_loaded(local_files_only=local_files_only)
        if not ok:
            return {
                "available": False,
                "analyzed": False,
                "status": "unavailable",
                "error": msg,
                "model_name": self._config.get("model_name", _DEFAULT_MODEL_NAME),
                "top_matches": [],
            }

        try:
            import cv2
            import torch
            from PIL import Image

            rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)

            with self._lock:
                text_features, cache_hit = self._get_cached_text_embeddings(active_descriptions)
                t_inf0 = time.perf_counter()
                with torch.inference_mode():
                    if self._active_backend == "transformers":
                        img_inputs = self._processor(images=pil_image, return_tensors="pt")
                        img_inputs = {k: v.to(self._active_device) for k, v in img_inputs.items()}
                        raw_imf = self._model.get_image_features(**img_inputs)
                        imf = _extract_tensor(raw_imf)
                        logit_scale = getattr(self._model, "logit_scale", None)
                        scale_val = float(logit_scale.exp().clamp(max=100.0).item()) if logit_scale is not None else 100.0
                    else:
                        img_tensor = self._open_clip_preprocess(pil_image).unsqueeze(0).to(self._active_device)
                        imf = self._model.encode_image(img_tensor)
                        logit_scale = getattr(self._model, "logit_scale", None)
                        scale_val = float(logit_scale.exp().clamp(max=100.0).item()) if logit_scale is not None else 100.0

                    imf = imf / imf.norm(dim=-1, keepdim=True).clamp(min=1e-12)
                    cos_sims = (imf @ text_features.T)[0]
                    rel_scores = torch.softmax(cos_sims * scale_val, dim=-1)
                    cos_list = [round(float(x), 4) for x in cos_sims.detach().cpu().tolist()]
                    rel_list = [round(float(x), 4) for x in rel_scores.detach().cpu().tolist()]
                inference_ms = round((time.perf_counter() - t_inf0) * 1000.0, 2)

            ranked: List[Dict[str, Any]] = []
            for desc, cos_val, rel_val in zip(active_descriptions, cos_list, rel_list):
                ranked.append({
                    "id": desc["id"],
                    "description": desc["prompt"],
                    "cosine_similarity": cos_val,
                    "relative_candidate_score": rel_val,
                    "above_threshold": bool(cos_val >= thr),
                    "security_relevant": bool(desc.get("security_relevant", True)),
                    "severity": str(desc.get("severity") or "medium"),
                })
            ranked.sort(key=lambda r: r["cosine_similarity"], reverse=True)
            best = ranked[0] if ranked else None
            best_sec = next((r for r in ranked if r["security_relevant"] and r["above_threshold"]), None)
            matched = bool(best and best["above_threshold"])

            return {
                "available": True,
                "analyzed": True,
                "status": "analyzed",
                "result_kind": "clip_scene_similarity",
                "score_semantics": "Raw CLIP image-text cosine similarity [-1.0, 1.0]; not a calibrated detection probability.",
                "model_name": self._active_model_name or _DEFAULT_MODEL_NAME,
                "backend": self._active_backend or "transformers",
                "device": self._active_device,
                "text_cache_hit": cache_hit,
                "embedding_dim": int(text_features.shape[-1]),
                "cosine_threshold": round(thr, 3),
                "matched": matched,
                "matched_description": best["description"] if matched else None,
                "matched_id": best["id"] if matched else None,
                "top_description": best["description"] if best else None,
                "top_cosine_similarity": best["cosine_similarity"] if best else None,
                "top_relative_candidate_score": best["relative_candidate_score"] if best else None,
                "security_match": best_sec,
                "top_matches": ranked[:5],
                "inference_ms": inference_ms,
                "total_ms": round((time.perf_counter() - t_total0) * 1000.0, 2),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning("[CLIP_INFERENCE_ERROR] %s", exc)
            return {
                "available": False,
                "analyzed": False,
                "status": "error",
                "error": str(exc)[:240],
                "model_name": self._config.get("model_name", _DEFAULT_MODEL_NAME),
                "top_matches": [],
            }

    def analyze_image_path(self, image_path: str, local_files_only: bool = False) -> Dict[str, Any]:
        """Reads an image snapshot on disk via OpenCV and runs CLIP scene analysis."""
        try:
            import cv2
        except Exception as exc:
            return {"available": False, "analyzed": False, "status": "error", "error": str(exc), "top_matches": []}

        if not image_path or not os.path.exists(image_path):
            return {"available": False, "analyzed": False, "status": "missing_image", "top_matches": []}
        bgr = cv2.imread(image_path)
        if bgr is None:
            return {"available": False, "analyzed": False, "status": "decode_failed", "top_matches": []}
        return self.analyze_bgr_frame(bgr, local_files_only=local_files_only)


class ClipSceneScheduler:
    """
    Bounded non-blocking background worker executing CLIP scene inference at a
    controlled cadence per camera without delaying camera capture or YOLO26 tracking.
    """

    def __init__(self, analyzer: ClipSceneAnalyzer):
        self.analyzer = analyzer
        self._lock = threading.Lock()
        self._pending: Dict[int, Tuple[int, Any, Optional[int]]] = {}
        self._notify_q: queue.Queue = queue.Queue(maxsize=32)
        self._worker_thread: Optional[threading.Thread] = None
        self._latest_by_camera: Dict[int, Dict[str, Any]] = {}
        self._last_submit_mono: Dict[int, float] = {}
        self._cooldown_by_cam_prompt: Dict[Tuple[int, str], float] = {}
        self._streak_by_cam_prompt: Dict[Tuple[int, str], int] = {}

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="DeepVision-CLIPSceneScheduler",
                daemon=True,
            )
            self._worker_thread.start()

    def submit_frame(self, camera_id: int, user_id: Optional[int], bgr_frame: Any, *, force: bool = False) -> bool:
        """
        Non-blocking frame submission. Respects configurable `analysis_interval_seconds`
        and keeps only the single newest resized frame per camera.
        """
        if bgr_frame is None or getattr(bgr_frame, "size", 0) == 0:
            return False

        cfg = self.analyzer.get_config()
        if not cfg.get("enabled", False):
            return False

        now_mono = time.monotonic()
        interval = float(cfg.get("analysis_interval_seconds") or 5.0)
        cam_id = int(camera_id)

        with self._lock:
            last_sub = self._last_submit_mono.get(cam_id)
            if not force and last_sub is not None and (now_mono - last_sub) < interval:
                return False
            self._last_submit_mono[cam_id] = now_mono

        # Downscale wide frames cleanly before queuing to bound memory usage
        try:
            import cv2
            fh, fw = bgr_frame.shape[:2]
            if fw > 640:
                scale = 640.0 / float(fw)
                queued_frame = cv2.resize(bgr_frame, (640, max(1, int(round(fh * scale)))), interpolation=cv2.INTER_AREA)
            else:
                queued_frame = bgr_frame.copy()
        except Exception:
            queued_frame = bgr_frame.copy()

        with self._lock:
            self._pending[cam_id] = (cam_id, queued_frame, int(user_id) if user_id is not None else None)
        self._ensure_thread()
        try:
            self._notify_q.put_nowait(cam_id)
        except queue.Full:
            pass
        return True

    def _run_loop(self) -> None:
        while True:
            try:
                cam_id = self._notify_q.get(timeout=5.0)
            except queue.Empty:
                continue

            item = None
            with self._lock:
                item = self._pending.pop(cam_id, None)
            if item is None:
                continue

            c_id, frame, uid = item
            try:
                res = self.analyzer.analyze_bgr_frame(frame)
                res["camera_id"] = c_id
                if uid is not None:
                    res["user_id"] = uid
                with self._lock:
                    self._latest_by_camera[c_id] = res
                if res.get("analyzed"):
                    self._record_scene_event_if_relevant(c_id, uid, res)
            except Exception as exc:
                logger.warning("[CLIP_SCHEDULER_ERROR] camera_id=%s err=%s", c_id, exc)

    def _record_scene_event_if_relevant(self, camera_id: int, user_id: Optional[int], res: Dict[str, Any]) -> None:
        sec_match = res.get("security_match")
        if not sec_match or not sec_match.get("above_threshold"):
            return

        prompt = str(sec_match.get("description") or "").strip()
        if not prompt:
            return

        cfg = self.analyzer.get_config()
        cooldown = float(cfg.get("alert_cooldown_seconds") or 60.0)
        key = (int(camera_id), prompt.lower())
        now_mono = time.monotonic()

        with self._lock:
            streak = self._streak_by_cam_prompt.get(key, 0) + 1
            self._streak_by_cam_prompt[key] = streak
            last_emit = self._cooldown_by_cam_prompt.get(key)
            if last_emit is not None and (now_mono - last_emit) < cooldown:
                return
            self._cooldown_by_cam_prompt[key] = now_mono

        event_record = {
            "id": f"clip_{int(camera_id)}_{int(time.time() * 1000)}",
            "camera_id": int(camera_id),
            "user_id": int(user_id) if user_id is not None else None,
            "result_kind": "clip_scene_similarity",
            "matched_id": sec_match.get("id"),
            "matched_description": prompt,
            "cosine_similarity": sec_match.get("cosine_similarity"),
            "relative_candidate_score": sec_match.get("relative_candidate_score"),
            "severity": sec_match.get("severity", "medium"),
            "model_name": res.get("model_name"),
            "backend": res.get("backend"),
            "device": res.get("device"),
            "inference_ms": res.get("inference_ms"),
            "timestamp": res.get("analyzed_at") or datetime.now(timezone.utc).isoformat(),
            "top_matches": res.get("top_matches", [])[:3],
        }
        append_scene_event(event_record)

        if cfg.get("create_alerts_from_scene") and user_id is not None:
            self._emit_deduplicated_scene_alert(camera_id, int(user_id), event_record)

    def _emit_deduplicated_scene_alert(self, camera_id: int, user_id: int, ev: Dict[str, Any]) -> None:
        try:
            from datetime import timedelta
            from django.utils import timezone as dj_tz
            from apps.alerts.models import Alert
            from apps.notifications.models import Notification

            now_dt = dj_tz.now()
            cooldown = float(self.analyzer.get_config().get("alert_cooldown_seconds") or 60.0)
            cutoff = now_dt - timedelta(seconds=cooldown)
            desc = str(ev.get("matched_description") or "Scene anomaly").strip()
            title = f"Scene Match (CLIP): {desc}"[:100]
            dup = Alert.objects.filter(
                camera_id=camera_id,
                event_type="clip_scene_match",
                title=title,
                detected_at__gte=cutoff,
            ).exclude(status="resolved").first()
            if dup:
                return

            cos_val = float(ev.get("cosine_similarity") or 0.0)
            sev = str(ev.get("severity") or "medium").lower()
            alert = Alert.objects.create(
                user_id=user_id,
                camera_id=camera_id,
                track_id=None,
                event_type="clip_scene_match",
                title=title,
                message=(
                    f"CLIP scene analysis ({ev.get('model_name')}) matched '{desc}' "
                    f"with cosine similarity {cos_val:.4f} on {ev.get('device', 'cpu')}."
                ),
                severity=sev if sev in ("critical", "high", "medium", "low") else "medium",
                status="new",
                confidence=round(max(0.0, min(1.0, cos_val)), 4),
                detected_at=now_dt,
                created_at=now_dt,
                updated_at=now_dt,
                response_state="NEW",
            )
            Notification.objects.create(user_id=user_id, alert=alert, is_read=False, created_at=now_dt)
        except Exception as exc:
            logger.warning("[CLIP_ALERT_EMIT_WARN] cam=%s err=%s", camera_id, exc)

    def get_camera_scene(self, camera_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            cached = self._latest_by_camera.get(int(camera_id))
            return dict(cached) if cached else None

    def clear_camera(self, camera_id: int) -> None:
        cam_id = int(camera_id)
        with self._lock:
            self._pending.pop(cam_id, None)
            self._latest_by_camera.pop(cam_id, None)
            self._last_submit_mono.pop(cam_id, None)
            for k in [k for k in self._cooldown_by_cam_prompt if k[0] == cam_id]:
                self._cooldown_by_cam_prompt.pop(k, None)
            for k in [k for k in self._streak_by_cam_prompt if k[0] == cam_id]:
                self._streak_by_cam_prompt.pop(k, None)

    def shutdown(self) -> None:
        """Signals pending work clear on scheduler teardown cleanly without blocking."""
        with self._lock:
            self._pending.clear()
            try:
                while not self._notify_q.empty():
                    self._notify_q.get_nowait()
            except Exception:
                pass


_EVENTS_LOCK = threading.Lock()


def _load_scene_events() -> List[Dict[str, Any]]:
    path = _get_clip_events_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data[-_MAX_SCENE_EVENTS:]
        return []
    except Exception:
        return []


def append_scene_event(event: Dict[str, Any]) -> None:
    path = _get_clip_events_path()
    with _EVENTS_LOCK:
        items = _load_scene_events()
        items.append(event)
        items = items[-_MAX_SCENE_EVENTS:]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp.{threading.get_ident()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(items, fh, indent=2)
        os.replace(tmp, path)


def list_scene_events(
    *,
    user_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    with _EVENTS_LOCK:
        items = _load_scene_events()
    out = []
    for item in reversed(items):
        if user_id is not None and item.get("user_id") is not None and int(item["user_id"]) != int(user_id):
            continue
        if camera_id is not None and int(item.get("camera_id", -1)) != int(camera_id):
            continue
        out.append(item)
        if len(out) >= max(1, min(100, int(limit))):
            break
    return out


_SINGLETON_LOCK = threading.RLock()
_ANALYZER: Optional[ClipSceneAnalyzer] = None
_SCHEDULER: Optional[ClipSceneScheduler] = None


def get_clip_analyzer() -> ClipSceneAnalyzer:
    global _ANALYZER
    if _ANALYZER is None:
        with _SINGLETON_LOCK:
            if _ANALYZER is None:
                _ANALYZER = ClipSceneAnalyzer()
    return _ANALYZER


def get_clip_scheduler() -> ClipSceneScheduler:
    global _SCHEDULER
    if _SCHEDULER is None:
        analyzer = get_clip_analyzer()
        with _SINGLETON_LOCK:
            if _SCHEDULER is None:
                _SCHEDULER = ClipSceneScheduler(analyzer)
    return _SCHEDULER


def reset_clip_singletons_for_tests() -> None:
    """Resets CLIP analyzer and scheduler singletons cleanly between unit tests."""
    global _ANALYZER, _SCHEDULER
    import gc

    with _SINGLETON_LOCK:
        if _SCHEDULER is not None:
            try:
                _SCHEDULER.shutdown()
            except Exception:
                pass
        _SCHEDULER = None
        _ANALYZER = None
    gc.collect()
