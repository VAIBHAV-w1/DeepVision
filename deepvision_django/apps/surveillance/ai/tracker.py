"""
ByteTrack Multi-Object Tracker for Django Surveillance Architecture.
Uses shared YOLO11n weights with an isolated camera predictor state.
"""
import os
import torch
from apps.surveillance.ai.model_loader import (
    create_camera_model_wrapper,
    get_inference_lock,
)


class ByteTrackTracker:
    def __init__(self, confidence_threshold=0.50):
        self.confidence_threshold = confidence_threshold
        self.model = create_camera_model_wrapper()
        self.tracker_yaml = os.path.abspath(os.path.join(os.path.dirname(__file__), "bytetrack.yaml"))
        if not os.path.exists(self.tracker_yaml):
            self.tracker_yaml = "bytetrack.yaml"

        self.phone_class_id = None
        if hasattr(self.model, "names") and self.model.names:
            for cid, name in self.model.names.items():
                if name == "cell phone":
                    self.phone_class_id = cid
                    break

        self.last_detections = []

    def track(self, frame, custom_conf=None):
        if frame is None or not hasattr(frame, "shape"):
            return []

        try:
            conf_thresh = custom_conf if custom_conf is not None else self.confidence_threshold

            with get_inference_lock(), torch.inference_mode():
                results = self.model.track(
                    frame,
                    persist=True,
                    conf=0.10,
                    imgsz=640,
                    tracker=self.tracker_yaml,
                    verbose=False
                )

            tracked_objects = []
            all_detections = []
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
                        if conf < min(conf_thresh, 0.15):
                            continue
                    else:
                        if conf < conf_thresh:
                            continue

                    det_dict = {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": conf,
                        "x1": int(xyxy[0]),
                        "y1": int(xyxy[1]),
                        "x2": int(xyxy[2]),
                        "y2": int(xyxy[3])
                    }
                    all_detections.append(det_dict)

                    if box.id is not None:
                        try:
                            track_id = int(box.id[0].item())
                            trk_dict = dict(det_dict)
                            trk_dict["track_id"] = track_id
                            tracked_objects.append(trk_dict)
                        except Exception:
                            pass

            self.last_detections = all_detections
            return tracked_objects

        except Exception as e:
            print(f"[ByteTrackTracker] Tracking error: {e}")
            self.last_detections = []
            return []
