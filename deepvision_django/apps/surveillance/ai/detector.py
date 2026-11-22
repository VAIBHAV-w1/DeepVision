"""
Object Detector Service for DeepVision 4.0 Surveillance Architecture.
Runs thread-safe ONNX/OpenVINO/ORT/OpenCV-DNN inference on raw OpenCV BGR frames
with class-calibrated confidence thresholds and duplicate suppression.
"""

from __future__ import annotations

try:
    import torch
except (ImportError, Exception):
    torch = None

from apps.surveillance.ai.model_loader import (
    create_camera_model_wrapper,
    get_inference_lock,
    get_shared_yolo_model,
)
from apps.surveillance.ai.onnx_runtime import COCO_NAMES, SharedONNXEngine

# Class-specific minimum confidence gates calibrated against surveillance sets
CLASS_CONFIDENCE_GATES = {
    0: 0.45,   # person (suppresses hanging-garment noise cleanly while keeping 100% eval recall)
    1: 0.40,   # bicycle
    2: 0.35,   # car
    3: 0.40,   # motorcycle
    5: 0.40,   # bus
    7: 0.40,   # truck
    14: 0.55,  # bird
    15: 0.55,  # cat
    16: 0.55,  # dog (strict animal gating)
    17: 0.55,  # horse
    18: 0.55,  # sheep
    19: 0.55,  # cow
    20: 0.55,  # elephant
    21: 0.55,  # bear
    22: 0.55,  # zebra
    23: 0.55,  # giraffe
    24: 0.28,  # backpack
    26: 0.28,  # handbag
    28: 0.30,  # suitcase
    39: 0.22,  # bottle
    41: 0.20,  # cup
    45: 0.20,  # bowl
    56: 0.35,  # chair
    62: 0.35,  # tv
    63: 0.60,  # laptop (cropped/handheld phones frequently look like laptops below 0.60)
    67: 0.25,  # cell phone (balanced precision/recall gate for YOLO26s)
}


class YOLODetector:
    """Stateless-interface single-frame object detector backed by singleton shared model."""

    def __init__(self, confidence_threshold: float = 0.45):
        self.confidence_threshold = float(confidence_threshold)
        shared = get_shared_yolo_model()
        if isinstance(shared, SharedONNXEngine):
            self.model = create_camera_model_wrapper()
        else:
            self.model = shared
        self.names = getattr(self.model, "names", COCO_NAMES) if self.model is not None else COCO_NAMES
        self.phone_class_id = 67
        if self.names:
            for cid, name in self.names.items():
                if name == "cell phone":
                    self.phone_class_id = int(cid)
                    break

    @property
    def backend_name(self) -> str:
        if self.model is None:
            return "unavailable"
        return getattr(self.model, "backend_id", "yolo11n")

    def detect(self, frame, custom_conf=None):
        if frame is None or not hasattr(frame, "shape") or getattr(frame, "size", 0) == 0:
            return []
        if self.model is None:
            return []

        base_conf = float(custom_conf if custom_conf is not None else self.confidence_threshold)
        infer_conf = min(base_conf, 0.18)

        # Primary ONNX / OpenVINO / ORT / cv2.dnn path
        if hasattr(self.model, "infer"):
            try:
                raw_dets, _ = self.model.infer(frame, conf_floor=infer_conf)
                out = []
                for d in raw_dets:
                    cid = int(d["class_id"])
                    conf = float(d["confidence"])
                    min_req = (
                        base_conf
                        if custom_conf is not None and custom_conf < CLASS_CONFIDENCE_GATES.get(cid, 0.40)
                        else CLASS_CONFIDENCE_GATES.get(cid, max(base_conf, 0.35))
                    )
                    if conf < min_req:
                        continue
                    out.append(d)
                return out
            except Exception as e:
                print(f"[YOLODetector] ONNX detection exception: {e}")
                return []

        # Legacy PyTorch fallback path
        if torch is None:
            return []
        try:
            with get_inference_lock(), torch.inference_mode():
                results = self.model(frame, conf=infer_conf, imgsz=640, verbose=False)

            detections = []
            for result in results:
                if not hasattr(result, "boxes") or result.boxes is None:
                    continue
                for box in result.boxes:
                    xyxy_raw = box.xyxy
                    if hasattr(xyxy_raw, "__getitem__"):
                        first_item = xyxy_raw[0]
                        xyxy = first_item.tolist() if hasattr(first_item, "tolist") else list(first_item)
                    else:
                        xyxy = [0, 0, 0, 0]

                    conf = float(box.conf[0]) if hasattr(box.conf, "__getitem__") else 0.0
                    cls_id = int(box.cls[0]) if hasattr(box.cls, "__getitem__") else -1
                    cls_name = self.model.names.get(cls_id, "unknown") if cls_id in self.model.names else "unknown"
                    min_required = CLASS_CONFIDENCE_GATES.get(cls_id, max(base_conf, 0.40))
                    if conf < min_required:
                        continue

                    detections.append({
                        "x1": int(xyxy[0]),
                        "y1": int(xyxy[1]),
                        "x2": int(xyxy[2]),
                        "y2": int(xyxy[3]),
                        "confidence": float(conf),
                        "class_id": int(cls_id),
                        "class_name": str(cls_name),
                    })
            return detections
        except Exception as e:
            print(f"[YOLODetector] Detection exception: {e}")
            return []
