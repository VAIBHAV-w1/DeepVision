"""
YOLO11n Object Detector Service for Django Surveillance Architecture.
Runs CPU inference on raw OpenCV BGR frames and returns structured predictions.
"""
import torch
from apps.surveillance.ai.model_loader import get_shared_yolo_model, get_inference_lock


class YOLODetector:
    def __init__(self, confidence_threshold=0.50):
        self.confidence_threshold = confidence_threshold
        self.model = get_shared_yolo_model()
        self.phone_class_id = None
        if hasattr(self.model, "names") and self.model.names:
            for cid, name in self.model.names.items():
                if name == "cell phone":
                    self.phone_class_id = cid
                    break

    def detect(self, frame, custom_conf=None):
        if frame is None or not hasattr(frame, "shape"):
            return []

        try:
            conf_thresh = custom_conf if custom_conf is not None else self.confidence_threshold
            yolo_conf = conf_thresh
            if self.phone_class_id is not None:
                yolo_conf = min(conf_thresh, 0.30)

            with get_inference_lock(), torch.inference_mode():
                results = self.model(frame, conf=yolo_conf, imgsz=640, verbose=False)

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

                    if cls_id == self.phone_class_id:
                        if conf < min(conf_thresh, 0.30):
                            continue
                    else:
                        if conf < conf_thresh:
                            continue

                    detections.append({
                        "x1": int(xyxy[0]),
                        "y1": int(xyxy[1]),
                        "x2": int(xyxy[2]),
                        "y2": int(xyxy[3]),
                        "confidence": float(conf),
                        "class_id": int(cls_id),
                        "class_name": str(cls_name)
                    })
            return detections
        except Exception as e:
            print(f"[YOLODetector] Detection exception: {e}")
            return []
