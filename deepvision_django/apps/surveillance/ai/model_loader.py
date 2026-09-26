"""
YOLO11n Singleton Model Loader for Django Surveillance Architecture.
Guarantees MODEL_LOAD_COUNT=1 from disk and shared nn.Module weights in RAM.
"""
import os
import copy
import threading
from ultralytics import YOLO

_model_lock = threading.Lock()
_shared_yolo_model = None
_model_load_count = 0
_model_instance_count = 0
_instance_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_inference_lock():
    """
    Returns the process-wide lock for PyTorch CPU forward inference.
    Prevents concurrent C-level execution collisions on shared nn.Module weights.
    """
    return _inference_lock


def get_shared_yolo_model():
    """
    Returns the singleton YOLO model instance.
    Loads from disk exactly once per process. Thread-safe.
    """
    global _shared_yolo_model, _model_load_count
    with _model_lock:
        if _shared_yolo_model is None:
            _model_load_count += 1
            from django.conf import settings
            models_dir = os.path.join(settings.BASE_DIR.parent, "models")
            os.makedirs(models_dir, exist_ok=True)
            model_path = os.path.join(models_dir, "yolo11n.pt")
            print(f"[MODEL_LOADER] Loading shared YOLO model from {model_path}...")
            print(f"[MODEL_LOADER] MODEL_LOAD_COUNT={_model_load_count} (should always be 1)")
            model = YOLO(model_path)
            model.to("cpu")
            _shared_yolo_model = model
            print("[MODEL_LOADER] Shared YOLO model successfully loaded on CPU.")
            print(f"[MODEL_LOADER] MODEL_INSTANCE_ID={id(model.model)} (nn.Module weights reference)")
        return _shared_yolo_model


def get_model_load_count():
    """Returns the number of times a model was loaded from disk. Should always be 1 in production."""
    return _model_load_count


def create_camera_model_wrapper():
    """
    Creates a new YOLO wrapper that shares the singleton nn.Module weights
    but has an isolated predictor (and therefore isolated ByteTrack state).

    This is the ONLY correct way to create a per-camera YOLO instance:
    - Zero disk I/O (no torch.load)
    - Zero model weight duplication in RAM
    - Isolated tracker state per camera
    """
    global _model_instance_count
    shared = get_shared_yolo_model()
    wrapper = copy.copy(shared)
    wrapper.predictor = None  # fresh tracker state for this camera instance
    with _instance_lock:
        _model_instance_count += 1
        instance_num = _model_instance_count
    print(f"[MODEL_LOADER] MODEL_INSTANCE_CREATED camera_wrapper #{instance_num} "
          f"id={id(wrapper)} weights_id={id(wrapper.model)} "
          f"(MODEL_LOAD_COUNT={_model_load_count}, shared weights, no disk I/O)")
    return wrapper


def get_model_instance_count():
    """Returns total number of camera model wrappers created."""
    return _model_instance_count
