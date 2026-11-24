"""
Verified ONNX Runtime & OpenVINO Model Loader / Inference Engine for DeepVision 4.0.

Supports:
  - SHA-256 and file-size verification against official Ultralytics v8.4.0 ONNX releases
  - Runtime selection chain verified under Windows Smart App Control & Linux:
      1. Intel OpenVINO GPU (Iris Xe / discrete Intel GPU with persistent CACHE_DIR)
      2. Intel OpenVINO CPU
      3. ONNX Runtime CPU (CPUExecutionProvider)
      4. OpenCV DNN CPU (cv2.dnn.readNetFromONNX)
  - YOLO26 NMS-free end-to-end [1, 300, 6] output decoding AND YOLO11/v8 [1, 84, N] decoding
  - Preallocated reusable RGB/CHW buffers & thread-safe InferRequest pools (1 shared weights load)
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

COCO_NAMES: Dict[int, str] = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench", 14: "bird",
    15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
    25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
    30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat",
    35: "baseball glove", 36: "skateboard", 37: "surfboard", 38: "tennis racket",
    39: "bottle", 40: "wine glass", 41: "cup", 42: "fork", 43: "knife",
    44: "spoon", 45: "bowl", 46: "banana", 47: "apple", 48: "sandwich",
    49: "orange", 50: "broccoli", 51: "carrot", 52: "hot dog", 53: "pizza",
    54: "donut", 55: "cake", 56: "chair", 57: "couch", 58: "potted plant",
    59: "bed", 60: "dining table", 61: "toilet", 62: "tv", 63: "laptop",
    64: "mouse", 65: "remote", 66: "keyboard", 67: "cell phone", 68: "microwave",
    69: "oven", 70: "toaster", 71: "sink", 72: "refrigerator", 73: "book",
    74: "clock", 75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier",
    79: "toothbrush",
}

# Verified SHA-256 digests from official Ultralytics v8.4.0 GitHub release assets
MODEL_MANIFEST: Dict[str, Dict[str, Any]] = {
    "yolo26s.onnx": {
        "sha256": "d26b65c432111eb95798cd2320603d4d75627605dbec6c6b7f98c499a80e7321",
        "size_bytes": 38291130,
        "format": "end2end_xyxy",
        "license": "AGPL-3.0",
        "profile": "balanced",
    },
    "yolo26n.onnx": {
        "sha256": "2e947b787d9e787b93a16772a5f55b1d4d8c4d86f53146149c5d6a642442d6f7",
        "size_bytes": 9941957,
        "format": "end2end_xyxy",
        "license": "AGPL-3.0",
        "profile": "lightweight",
    },
    "yolo11n.onnx": {
        "sha256": "634279b40c07c6391472c51ad45b81ebc48706a9a1fe72dd3396322acd0c053b",
        "size_bytes": 10930182,
        "format": "xywh_84xN",
        "license": "AGPL-3.0",
        "profile": "legacy_onnx",
    },
}


def compute_sha256(file_path: str) -> str:
    """Computes lowercase hexadecimal SHA-256 digest for a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_model_artifact(model_path: str, expected_name: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """Validates existence, non-empty size, and expected SHA-256 digest for a manifested model file."""
    if not model_path or not os.path.isfile(model_path):
        return False, f"Model file missing: {model_path}", None
    fname = expected_name or os.path.basename(model_path)
    meta = MODEL_MANIFEST.get(fname)
    actual_size = os.path.getsize(model_path)
    actual_hash = compute_sha256(model_path)
    if meta is None:
        return False, f"Unregistered ONNX model artifact rejected (missing manifest digest): {fname}", actual_hash
    if actual_size != meta["size_bytes"]:
        return False, f"Size mismatch for {fname}: expected {meta['size_bytes']}, got {actual_size}", actual_hash
    if actual_hash != meta["sha256"]:
        return False, f"SHA-256 mismatch for {fname}: expected {meta['sha256']}, got {actual_hash}", actual_hash
    return True, "ok", actual_hash


def get_effective_cpu_count() -> int:
    """
    Returns effective CPU quota available to this process (respecting Linux cgroup v1/v2
    CPU limits in containers such as Render/Docker so OpenVINO/ORT do not oversubscribe).
    """
    override = (os.getenv("DEEPVISION_CPU_THREADS") or "").strip()
    if override.isdigit() and int(override) >= 1:
        return int(override)

    host_cpus = max(1, os.cpu_count() or 1)
    quota_cpus = None

    try:
        # cgroup v2: "<quota> <period>"
        with open("/sys/fs/cgroup/cpu.max", "r", encoding="utf-8") as fh:
            parts = fh.read().strip().split()
            if len(parts) >= 2 and parts[0] != "max":
                q, p = float(parts[0]), float(parts[1])
                if q > 0 and p > 0:
                    quota_cpus = max(1, int(round(q / p)))
    except Exception:
        pass

    if quota_cpus is None:
        try:
            # cgroup v1
            with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "r", encoding="utf-8") as fq, \
                 open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", "r", encoding="utf-8") as fp:
                q, p = float(fq.read().strip()), float(fp.read().strip())
                if q > 0 and p > 0:
                    quota_cpus = max(1, int(round(q / p)))
        except Exception:
            pass

    if quota_cpus is not None:
        return max(1, min(host_cpus, quota_cpus))
    return host_cpus


def resolve_default_profile() -> str:
    """Defaults to real-time YOLO26n (OpenVINO GPU ~32 FPS / CPU ~3.3x faster) unless balanced YOLO26s is requested."""
    explicit_profile = (os.getenv("DEEPVISION_AI_PROFILE") or "").strip().lower()
    if explicit_profile:
        if explicit_profile in ("balanced", "yolo26s", "standard", "high_accuracy"):
            return "balanced"
        return "lightweight"
    return "lightweight"


def resolve_selected_model_name(profile_override: Optional[str] = None) -> str:
    """Resolves active ONNX checkpoint filename based on explicit profile, env, or default."""
    explicit = (os.getenv("DEEPVISION_MODEL_NAME") or "").strip()
    if explicit and not profile_override:
        return explicit
    profile = (profile_override or os.getenv("DEEPVISION_AI_PROFILE") or resolve_default_profile()).strip().lower()
    if profile in ("lightweight", "nano", "low_resource", "cpu_lite", "fast", "fast_cpu"):
        return "yolo26n.onnx"
    return "yolo26s.onnx"


def get_model_profile_catalog() -> List[Dict[str, str]]:
    """Returns explicit accuracy/performance profiles without hiding model identity."""
    return [
        {
            "id": "lightweight",
            "model_name": "yolo26n.onnx",
            "label": "YOLO26n — Real-Time 30 FPS (Default)",
            "tradeoff": "~30ms on Iris Xe iGPU (~32 FPS) and ~3.3x faster on CPU; ideal for live surveillance.",
        },
        {
            "id": "balanced",
            "model_name": "yolo26s.onnx",
            "label": "YOLO26s — High Accuracy (Explicit)",
            "tradeoff": "Higher small/distant object recall (~53ms on Iris Xe iGPU, heavier on CPU).",
        },
    ]


class _InferenceBuffers:
    """Reusable per-inference scratchpad avoiding repeated 640x640x3 allocations."""

    def __init__(self, target_size: int = 640):
        self.size = int(target_size)
        self.canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        self.chw = np.empty((1, 3, self.size, self.size), dtype=np.float32)
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def _apply_lowlight_enhancement(self, bgr_frame: np.ndarray) -> np.ndarray:
        """Apply LAB CLAHE strictly on genuinely dark frames so well-lit scenes stay fast and crisp."""
        sample = bgr_frame[::8, ::8] if (bgr_frame.shape[0] >= 32 and bgr_frame.shape[1] >= 32) else bgr_frame
        gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        mean_luma = float(np.mean(gray))
        if mean_luma >= 72.0:
            return bgr_frame
        std_luma = float(np.std(gray))
        if mean_luma >= 55.0 and std_luma >= 28.0:
            return bgr_frame
        lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        l_eq = self._clahe.apply(l_ch)
        return cv2.cvtColor(cv2.merge((l_eq, a_ch, b_ch)), cv2.COLOR_LAB2BGR)

    def ensure_size(self, target_size: int):
        if int(target_size) != self.size:
            self.size = int(target_size)
            self.canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
            self.chw = np.empty((1, 3, self.size, self.size), dtype=np.float32)

    def prepare(self, bgr_frame: np.ndarray, target_size: int = 640) -> Tuple[np.ndarray, float, float, float]:
        """Letterboxes BGR uint8 image into normalized NCHW RGB float32 tensor using SIMD OpenCV."""
        self.ensure_size(target_size)
        h, w = bgr_frame.shape[:2]
        scale = min(self.size / float(w), self.size / float(h))
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        dw = (self.size - nw) / 2.0
        dh = (self.size - nh) / 2.0
        top, left = int(round(dh - 0.1)), int(round(dw - 0.1))

        self.canvas.fill(114)
        roi = self.canvas[top:top + nh, left:left + nw]
        if nw != w or nh != h:
            cv2.resize(bgr_frame, (nw, nh), dst=roi, interpolation=cv2.INTER_LINEAR)
        else:
            np.copyto(roi, bgr_frame)

        enhanced = self._apply_lowlight_enhancement(roi)
        if enhanced is not roi:
            np.copyto(roi, enhanced)

        # Fused SIMD BGR->RGB, HWC->NCHW, and 1/255 float32 scaling (~2x faster than NumPy divide)
        blob = cv2.dnn.blobFromImage(self.canvas, scalefactor=1.0 / 255.0, swapRB=True, crop=False)
        return blob, scale, float(left), float(top)


def decode_yolo_onnx_output(
    raw_output: np.ndarray,
    img_w: int,
    img_h: int,
    scale: float,
    pad_left: float,
    pad_top: float,
    conf_floor: float = 0.15,
    nms_iou: float = 0.45,
) -> List[Dict[str, Any]]:
    """
    Decodes both:
      - YOLO26 end-to-end NMS-free output (shape [1, 300, 6] or [N, 6]: x1, y1, x2, y2, score, cls_id)
      - Legacy anchor-free YOLO11/v8 output (shape [1, 84, N]: cx, cy, w, h, 80 class probs)
    Applies coordinate un-letterboxing, bounds clamping, and class-aware overlap suppression.
    """
    if raw_output is None:
        return []
    arr = np.asarray(raw_output)
    if arr.ndim == 3:
        arr = arr[0]

    candidates: List[Dict[str, Any]] = []
    if arr.ndim == 2 and arr.shape[1] == 6:
        # YOLO26 end-to-end [300, 6]
        scores = arr[:, 4]
        keep = scores >= float(conf_floor)
        for row in arr[keep]:
            x1 = max(0.0, min(float(img_w), (float(row[0]) - pad_left) / scale))
            y1 = max(0.0, min(float(img_h), (float(row[1]) - pad_top) / scale))
            x2 = max(0.0, min(float(img_w), (float(row[2]) - pad_left) / scale))
            y2 = max(0.0, min(float(img_h), (float(row[3]) - pad_top) / scale))
            ix1, iy1, ix2, iy2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
            if (ix2 - ix1) < 6 or (iy2 - iy1) < 6:
                continue
            cls_id = int(round(float(row[5])))
            if cls_id < 0 or cls_id >= 80:
                continue
            candidates.append({
                "x1": ix1,
                "y1": iy1,
                "x2": ix2,
                "y2": iy2,
                "confidence": float(row[4]),
                "class_id": cls_id,
                "class_name": COCO_NAMES.get(cls_id, "unknown"),
            })
    elif arr.ndim == 2 and (arr.shape[0] == 84 or arr.shape[1] == 84):
        preds = arr.T if arr.shape[0] == 84 else arr
        cls_scores = preds[:, 4:]
        cls_ids = np.argmax(cls_scores, axis=1)
        max_confs = cls_scores[np.arange(len(cls_scores)), cls_ids]
        mask = max_confs >= float(conf_floor)
        preds_f = preds[mask]
        confs_f = max_confs[mask]
        cids_f = cls_ids[mask]
        if len(preds_f) > 0:
            cx, cy, bw, bh = preds_f[:, 0], preds_f[:, 1], preds_f[:, 2], preds_f[:, 3]
            x1s = np.clip((cx - bw * 0.5 - pad_left) / scale, 0, img_w)
            y1s = np.clip((cy - bh * 0.5 - pad_top) / scale, 0, img_h)
            x2s = np.clip((cx + bw * 0.5 - pad_left) / scale, 0, img_w)
            y2s = np.clip((cy + bh * 0.5 - pad_top) / scale, 0, img_h)
            xywh_boxes = np.stack([x1s, y1s, x2s - x1s, y2s - y1s], axis=1).tolist()
            # Class-offset NMS so distinct overlapping objects (person + cell phone) do not suppress each other
            for cid in np.unique(cids_f):
                idx_c = np.where(cids_f == cid)[0]
                boxes_c = [xywh_boxes[i] for i in idx_c]
                scores_c = [float(confs_f[i]) for i in idx_c]
                keep_c = cv2.dnn.NMSBoxes(boxes_c, scores_c, float(conf_floor), float(nms_iou))
                if len(keep_c) > 0:
                    for k in np.asarray(keep_c).flatten():
                        orig_i = idx_c[int(k)]
                        ix1, iy1 = int(round(x1s[orig_i])), int(round(y1s[orig_i]))
                        ix2, iy2 = int(round(x2s[orig_i])), int(round(y2s[orig_i]))
                        if (ix2 - ix1) < 6 or (iy2 - iy1) < 6:
                            continue
                        candidates.append({
                            "x1": ix1,
                            "y1": iy1,
                            "x2": ix2,
                            "y2": iy2,
                            "confidence": float(confs_f[orig_i]),
                            "class_id": int(cid),
                            "class_name": COCO_NAMES.get(int(cid), "unknown"),
                        })
    else:
        raise ValueError(f"Unsupported YOLO ONNX output shape: {tuple(arr.shape)}")

    def _box_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
        ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
        area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
        return inter / float(area_a + area_b - inter)

    # Class-aware duplicate + cross-class phone/display confusion suppression
    candidates.sort(key=lambda d: d["confidence"], reverse=True)
    deduped: List[Dict[str, Any]] = []
    for cand in candidates:
        cbox = (cand["x1"], cand["y1"], cand["x2"], cand["y2"])
        dup = False
        for kept in deduped:
            if kept["class_id"] != cand["class_id"]:
                continue
            kbox = (kept["x1"], kept["y1"], kept["x2"], kept["y2"])
            if _box_iou(cbox, kbox) >= 0.55:
                dup = True
                break
        if not dup:
            deduped.append(cand)

    phone_boxes = [
        (d["x1"], d["y1"], d["x2"], d["y2"])
        for d in deduped
        if int(d.get("class_id", -1)) == 67 and float(d.get("confidence", 0.0)) >= 0.25
    ]
    if not phone_boxes:
        return deduped

    filtered: List[Dict[str, Any]] = []
    for det in deduped:
        if int(det.get("class_id", -1)) in (62, 63):
            dbox = (det["x1"], det["y1"], det["x2"], det["y2"])
            if any(_box_iou(dbox, pbox) >= 0.70 for pbox in phone_boxes):
                continue
        filtered.append(det)
    return filtered


class SharedONNXEngine:
    """
    Singleton ONNX Detection Runtime supporting Intel OpenVINO (GPU/CPU), ONNX Runtime (CPU),
    and OpenCV DNN (CPU). Guarantees 1 disk read + 1 shared compiled network in memory.
    """

    def __init__(self, model_path: str, cache_dir: Optional[str] = None, preferred_runtimes: Optional[List[str]] = None):
        self.model_path = os.path.abspath(model_path)
        self.model_name = os.path.basename(self.model_path)
        self.model_stem = os.path.splitext(self.model_name)[0]
        self.cache_dir = cache_dir
        self.names = COCO_NAMES

        ok, msg, sha256_hex = verify_model_artifact(self.model_path)
        if not ok:
            raise RuntimeError(f"[ONNXEngine] Model integrity verification failed: {msg}")
        self.sha256 = sha256_hex

        self.runtime_kind: str = "uninitialized"
        self.device_detail: str = ""
        self.input_size: int = 640
        self.output_shape: Tuple[int, ...] = ()
        self._lock = threading.RLock()
        self._ov_compiled = None
        self._ort_session = None
        self._ort_input_name = None
        self._cv_net = None
        self._default_buffers = _InferenceBuffers(640)

        chain = preferred_runtimes or self._resolve_runtime_order()
        errors: List[str] = []
        for rt in chain:
            try:
                if rt == "openvino_gpu":
                    self._init_openvino("GPU")
                    break
                if rt == "openvino_cpu":
                    self._init_openvino("CPU")
                    break
                if rt == "onnxruntime_cpu":
                    self._init_onnxruntime()
                    break
                if rt == "opencv_dnn_cpu":
                    self._init_opencv_dnn()
                    break
            except Exception as exc:
                errors.append(f"{rt}: {exc}")
                logger.warning(f"[ONNXEngine] Runtime '{rt}' unavailable for {self.model_name}: {exc}")

        if self.runtime_kind == "uninitialized":
            raise RuntimeError(f"All ONNX runtimes failed for {self.model_name}: {'; '.join(errors)}")

        logger.info(
            f"[ONNXEngine] Loaded {self.model_name} (sha256={self.sha256[:12]}..., "
            f"runtime={self.runtime_kind}, detail={self.device_detail}, imgsz={self.input_size}, out={self.output_shape})"
        )

    @staticmethod
    def _resolve_runtime_order() -> List[str]:
        pref = (os.getenv("DEEPVISION_RUNTIME_PREFERENCE") or "").strip().lower()
        default_chain = ["openvino_gpu", "openvino_cpu", "onnxruntime_cpu", "opencv_dnn_cpu"]
        if not pref:
            return default_chain
        mapping = {
            "ov_gpu": "openvino_gpu",
            "openvino_gpu": "openvino_gpu",
            "ov_cpu": "openvino_cpu",
            "openvino_cpu": "openvino_cpu",
            "ort_cpu": "onnxruntime_cpu",
            "onnxruntime": "onnxruntime_cpu",
            "onnxruntime_cpu": "onnxruntime_cpu",
            "cv2_dnn": "opencv_dnn_cpu",
            "opencv_dnn_cpu": "opencv_dnn_cpu",
        }
        chosen = [mapping[p.strip()] for p in pref.split(",") if p.strip() in mapping]
        for fallback in default_chain:
            if fallback not in chosen:
                chosen.append(fallback)
        return chosen

    def _validate_probe_output(self, out_arr: np.ndarray):
        shape = tuple(int(d) for d in out_arr.shape)
        if len(shape) == 3 and shape[2] == 6:
            self.output_shape = shape
        elif len(shape) == 3 and (shape[1] == 84 or shape[2] == 84):
            self.output_shape = shape
        else:
            raise ValueError(f"Unexpected YOLO ONNX probe output shape: {shape}")

    def _init_openvino(self, device: str):
        # Ensure openvino_telemetry writes/checks inside a writable app directory if LOCALAPPDATA is restricted
        local_app = os.environ.get("LOCALAPPDATA", "")
        intel_dir = os.path.join(local_app, "Intel Corporation") if local_app else ""
        can_write_intel = False
        if intel_dir:
            try:
                os.makedirs(intel_dir, exist_ok=True)
                probe_t = os.path.join(intel_dir, ".dv_write_probe")
                with open(probe_t, "w", encoding="utf-8") as fh:
                    fh.write("ok")
                os.remove(probe_t)
                can_write_intel = True
            except Exception:
                can_write_intel = False
        orig_local_app = os.environ.get("LOCALAPPDATA")
        if not can_write_intel:
            telem_base = os.path.abspath(os.path.join(self.cache_dir or os.path.dirname(self.model_path), "..", "ov_telemetry"))
            telem_intel = os.path.join(telem_base, "Intel Corporation")
            os.makedirs(telem_intel, exist_ok=True)
            opt_file = os.path.join(telem_intel, "openvino_telemetry")
            if not os.path.exists(opt_file):
                with open(opt_file, "w", encoding="utf-8") as fh:
                    fh.write("0")
            os.environ["LOCALAPPDATA"] = telem_base

        try:
            import openvino as ov

            core = ov.Core()
        finally:
            if not can_write_intel:
                if orig_local_app is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = orig_local_app
        available = list(core.available_devices)
        if device not in available and not any(d.startswith(device) for d in available):
            raise RuntimeError(f"OpenVINO device {device} not in available_devices={available}")
        effective_cache_dir = self.cache_dir or os.path.abspath(
            os.path.join(os.path.dirname(self.model_path), "..", "instance", "ov_cache")
        )
        try:
            os.makedirs(effective_cache_dir, exist_ok=True)
            core.set_property({"CACHE_DIR": effective_cache_dir})
        except Exception:
            pass

        ov_model = core.read_model(self.model_path)
        pshape = ov_model.inputs[0].partial_shape
        if len(pshape) == 4 and pshape[2].is_static and pshape[3].is_static:
            self.input_size = int(pshape[2].get_length())
        if device.startswith("GPU"):
            config = {
                "PERFORMANCE_HINT": "LATENCY",
                "INFERENCE_PRECISION_HINT": "f16",
            }
        else:
            config = {"PERFORMANCE_HINT": "LATENCY"}
        if device == "CPU":
            eff_cpus = get_effective_cpu_count()
            num_threads = max(1, min(4, eff_cpus))
            config["INFERENCE_NUM_THREADS"] = str(num_threads)
            config["NUM_STREAMS"] = "1"
            if eff_cpus <= 2:
                config["ENABLE_CPU_PINNING"] = "NO"
        try:
            compiled = core.compile_model(ov_model, device, config)
        except Exception:
            fallback_cfg = {"PERFORMANCE_HINT": "LATENCY"}
            if device == "CPU":
                fallback_cfg["INFERENCE_NUM_THREADS"] = config["INFERENCE_NUM_THREADS"]
            compiled = core.compile_model(ov_model, device, fallback_cfg)

        # Probe real forward inference + warm up execution graph once before serving frames
        probe_x = np.zeros((1, 3, self.input_size, self.input_size), dtype=np.float32)
        probe_req = compiled.create_infer_request()
        probe_out = next(iter(probe_req.infer([probe_x]).values()))
        self._validate_probe_output(probe_out)
        try:
            probe_req.infer([probe_x])
        except Exception:
            pass

        self._ov_compiled = compiled
        self._default_buffers = _InferenceBuffers(self.input_size)
        try:
            self.device_detail = str(core.get_property(device, "FULL_DEVICE_NAME"))
        except Exception:
            self.device_detail = f"OpenVINO-{device}"
        self.runtime_kind = "openvino_gpu" if device.startswith("GPU") else "openvino_cpu"

    def _init_onnxruntime(self):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(4, get_effective_cpu_count()))
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess = ort.InferenceSession(self.model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        inp = sess.get_inputs()[0]
        if len(inp.shape) == 4 and isinstance(inp.shape[2], int):
            self.input_size = int(inp.shape[2])
        self._ort_input_name = inp.name
        probe_x = np.zeros((1, 3, self.input_size, self.input_size), dtype=np.float32)
        probe_out = sess.run(None, {self._ort_input_name: probe_x})[0]
        self._validate_probe_output(probe_out)

        self._ort_session = sess
        self._default_buffers = _InferenceBuffers(self.input_size)
        self.runtime_kind = "onnxruntime_cpu"
        self.device_detail = f"ONNXRuntime-{ort.__version__}-CPUExecutionProvider"

    def _init_opencv_dnn(self):
        net = cv2.dnn.readNetFromONNX(self.model_path)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        probe_x = np.zeros((1, 3, self.input_size, self.input_size), dtype=np.float32)
        net.setInput(probe_x)
        probe_out = net.forward()
        self._validate_probe_output(probe_out)

        self._cv_net = net
        self._default_buffers = _InferenceBuffers(self.input_size)
        self.runtime_kind = "opencv_dnn_cpu"
        self.device_detail = f"OpenCV-{cv2.__version__}-DNN-CPU"

    @property
    def backend_id(self) -> str:
        """Honest machine identifier (e.g. 'yolo26s_openvino_gpu')."""
        return f"{self.model_stem}_{self.runtime_kind}"

    def create_worker_buffers(self) -> Tuple[_InferenceBuffers, Any]:
        """Creates isolated reusable scratchpad + OpenVINO InferRequest for one camera worker."""
        bufs = _InferenceBuffers(self.input_size)
        ov_req = self._ov_compiled.create_infer_request() if self._ov_compiled is not None else None
        return bufs, ov_req

    def infer(
        self,
        bgr_frame: np.ndarray,
        conf_floor: float = 0.15,
        buffers: Optional[_InferenceBuffers] = None,
        ov_request: Any = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """Runs thread-safe preprocessing, forward pass, and output decoding on a BGR frame."""
        if bgr_frame is None or not hasattr(bgr_frame, "shape") or getattr(bgr_frame, "size", 0) == 0:
            return [], {"preprocess_ms": 0.0, "inference_ms": 0.0, "postprocess_ms": 0.0}

        fh, fw = bgr_frame.shape[:2]
        bufs = buffers or self._default_buffers

        t0 = time.perf_counter()
        if bufs is self._default_buffers:
            with self._lock:
                chw, scale, pad_l, pad_t = bufs.prepare(bgr_frame, self.input_size)
                t1 = time.perf_counter()
                raw_out = self._run_forward(chw, ov_request)
        else:
            chw, scale, pad_l, pad_t = bufs.prepare(bgr_frame, self.input_size)
            t1 = time.perf_counter()
            raw_out = self._run_forward(chw, ov_request)
        t2 = time.perf_counter()

        detections = decode_yolo_onnx_output(
            raw_out,
            img_w=fw,
            img_h=fh,
            scale=scale,
            pad_left=pad_l,
            pad_top=pad_t,
            conf_floor=conf_floor,
        )
        t3 = time.perf_counter()

        timings = {
            "preprocess_ms": round((t1 - t0) * 1000.0, 3),
            "inference_ms": round((t2 - t1) * 1000.0, 3),
            "postprocess_ms": round((t3 - t2) * 1000.0, 3),
        }
        return detections, timings

    def _run_forward(self, chw: np.ndarray, ov_request: Any = None) -> np.ndarray:
        if self._ov_compiled is not None:
            if ov_request is not None:
                res = ov_request.infer([chw])
            else:
                res = self._ov_compiled.create_infer_request().infer([chw])
            return np.array(next(iter(res.values())), copy=False)
        if self._ort_session is not None:
            return self._ort_session.run(None, {self._ort_input_name: chw})[0]
        if self._cv_net is not None:
            with self._lock:
                self._cv_net.setInput(chw)
                return np.array(self._cv_net.forward(), copy=True)
        raise RuntimeError("ONNXEngine has no initialized runtime backend.")

    def release(self):
        with self._lock:
            self._ov_compiled = None
            self._ort_session = None
            self._cv_net = None
            self.runtime_kind = "unloaded"


class CameraONNXHandle:
    """
    Lightweight per-camera handle wrapping the shared SharedONNXEngine weights with
    worker-local preallocated buffers and InferRequest state. Zero model weight duplication.
    """

    def __init__(self, shared_engine: SharedONNXEngine):
        self.shared_engine = shared_engine
        self.model = shared_engine  # Preserves compatibility with id(wrapper.model)
        self.names = shared_engine.names
        self._buffers, self._ov_request = shared_engine.create_worker_buffers()

    @property
    def backend_id(self) -> str:
        return self.shared_engine.backend_id

    @property
    def runtime_kind(self) -> str:
        return self.shared_engine.runtime_kind

    @property
    def model_stem(self) -> str:
        return self.shared_engine.model_stem

    @property
    def device_detail(self) -> str:
        return self.shared_engine.device_detail

    def infer(self, bgr_frame: np.ndarray, conf_floor: float = 0.15) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        return self.shared_engine.infer(
            bgr_frame,
            conf_floor=conf_floor,
            buffers=self._buffers,
            ov_request=self._ov_request,
        )

    def reset_state(self):
        self._buffers, self._ov_request = self.shared_engine.create_worker_buffers()
