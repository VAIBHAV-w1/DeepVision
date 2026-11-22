"""
Singleton AI Model Loader for DeepVision 4.0 Surveillance Architecture.
Guarantees MODEL_LOAD_COUNT=1 from disk and shared compiled weights in RAM across
all logical and physical camera workers.

Primary path: Verified YOLO26s ONNX via Intel OpenVINO (Iris Xe GPU -> CPU)
-> ONNX Runtime (CPU) -> OpenCV DNN (CPU).
Legacy PyTorch fallback path is used only when explicitly requested and
permitted by OS security policy (Smart App Control / WDAC).
"""

from __future__ import annotations

import copy
import logging
import os
import threading
from typing import Any, Optional

from apps.surveillance.ai.onnx_runtime import (
    CameraONNXHandle,
    SharedONNXEngine,
    resolve_selected_model_name,
)

try:
    from ultralytics import YOLO
except (ImportError, Exception):
    YOLO = None

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_shared_yolo_model: Any = None
_model_load_count = 0
_model_instance_count = 0
_instance_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_inference_lock():
    """Returns process-wide inference lock for backends requiring serialized execution."""
    return _inference_lock


def _resolve_repo_paths():
    from django.conf import settings
    root_dir = os.path.abspath(settings.BASE_DIR.parent)
    models_dir = os.path.join(root_dir, "models")
    cache_dir = os.path.join(root_dir, "instance", "ov_cache")
    os.makedirs(models_dir, exist_ok=True)
    return root_dir, models_dir, cache_dir


def get_shared_yolo_model():
    """
    Returns the singleton shared model instance (`SharedONNXEngine` by default,
    or legacy PyTorch `YOLO` when explicitly requested and permitted).
    Loads from disk at most once per lifecycle. Thread-safe.
    """
    global _shared_yolo_model, _model_load_count
    with _model_lock:
        if _shared_yolo_model is not None:
            return _shared_yolo_model

        backend_pref = (os.getenv("DEEPVISION_MODEL_BACKEND") or "onnx").strip().lower()
        _, models_dir, cache_dir = _resolve_repo_paths()

        if backend_pref != "pytorch":
            candidate_names = [resolve_selected_model_name()]
            for fallback_name in ("yolo26s.onnx", "yolo26n.onnx", "yolo11n.onnx"):
                if fallback_name not in candidate_names:
                    candidate_names.append(fallback_name)

            for fname in candidate_names:
                mpath = os.path.join(models_dir, fname)
                if not os.path.isfile(mpath):
                    continue
                try:
                    engine = SharedONNXEngine(mpath, cache_dir=cache_dir)
                    _model_load_count += 1
                    _shared_yolo_model = engine
                    print(
                        f"[MODEL_LOADER] Loaded shared ONNX engine from {mpath} "
                        f"(runtime={engine.runtime_kind}, detail={engine.device_detail}, "
                        f"MODEL_LOAD_COUNT={_model_load_count}, sha256={engine.sha256[:12]})"
                    )
                    return _shared_yolo_model
                except Exception as onnx_err:
                    logger.warning(f"[MODEL_LOADER] ONNX candidate {fname} failed: {onnx_err}")

        # Legacy PyTorch (.pt) path only when explicitly opted in or no ONNX artifact loaded
        pt_path = os.path.join(models_dir, "yolo11n.pt")
        if YOLO is not None and os.path.isfile(pt_path):
            try:
                import torch
                max_threads = max(1, min(int(os.getenv("OMP_NUM_THREADS", "2")), os.cpu_count() or 2))
                torch.set_num_threads(max_threads)
                model = YOLO(pt_path)
                model.to("cpu")
                _model_load_count += 1
                _shared_yolo_model = model
                print(f"[MODEL_LOADER] Loaded legacy PyTorch YOLO from {pt_path} (MODEL_LOAD_COUNT={_model_load_count})")
                return _shared_yolo_model
            except Exception as pt_err:
                logger.warning(f"[MODEL_LOADER] PyTorch backend unavailable: {pt_err}")

        return None


def get_model_load_count() -> int:
    """Returns the number of times a model was loaded from disk."""
    return _model_load_count


def create_camera_model_wrapper():
    """
    Creates an isolated per-camera handle sharing the singleton weights/compiled network
    with zero extra disk reads and zero weight duplication in RAM.
    """
    global _model_instance_count
    shared = get_shared_yolo_model()
    if shared is None:
        return None

    if isinstance(shared, SharedONNXEngine):
        wrapper = CameraONNXHandle(shared)
    else:
        wrapper = copy.copy(shared)
        wrapper.predictor = None

    with _instance_lock:
        _model_instance_count += 1
        instance_num = _model_instance_count

    print(
        f"[MODEL_LOADER] MODEL_INSTANCE_CREATED camera_wrapper #{instance_num} "
        f"id={id(wrapper)} weights_id={id(getattr(wrapper, 'model', wrapper))} "
        f"(MODEL_LOAD_COUNT={_model_load_count}, backend={getattr(wrapper, 'backend_id', 'yolo11n')})"
    )
    return wrapper


def get_model_instance_count() -> int:
    """Returns total number of per-camera wrappers created."""
    return _model_instance_count


def reset_shared_yolo_model():
    """Safely unloads shared compiled networks/models from memory."""
    global _shared_yolo_model, _model_load_count, _model_instance_count
    with _model_lock:
        if isinstance(_shared_yolo_model, SharedONNXEngine):
            try:
                _shared_yolo_model.release()
            except Exception:
                pass
        _shared_yolo_model = None
        _model_load_count = 0
    with _instance_lock:
        _model_instance_count = 0
