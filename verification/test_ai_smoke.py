"""
DeepVision AI Smoke Test Helper
Runs inside the container environment to verify YOLO11n singleton and ByteTrack tracker.
"""

import sys
import os
import time
import json
import numpy as np

REPO_ROOT = "/app"
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "deepvision_django"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    import django
    django.setup()

    from apps.surveillance.ai.model_loader import get_shared_yolo_model, get_model_load_count
    from apps.surveillance.ai.detector import YOLODetector
    from apps.surveillance.ai.tracker import ByteTrackTracker

    t0 = time.time()
    model = get_shared_yolo_model()
    load_count = get_model_load_count()
    det = YOLODetector(confidence_threshold=0.05)
    dummy_frame = np.full((720, 1280, 3), 128, dtype=np.uint8)
    cv_frame = np.ascontiguousarray(dummy_frame)
    detections = det.detect(cv_frame)
    t_infer = (time.time() - t0) * 1000

    tracker = ByteTrackTracker(confidence_threshold=0.05)
    tracks_seen = []
    for _ in range(3):
        res = tracker.track(cv_frame)
        tracks_seen.append(len(res))

    out = {
        "success": True,
        "infer_time_ms": t_infer,
        "model_id": id(model.model if hasattr(model, 'model') else model),
        "load_count": load_count,
        "detections_count": len(detections),
        "tracks_count_sequence": tracks_seen
    }
except Exception as e:
    out = {
        "success": False,
        "error": str(e)
    }

print(json.dumps(out))
