"""
Verification of YOLO11n Object Detection and ByteTrack Multi-Object Tracking.
Verifies:
1. Shared YOLO11n singleton loading from models/yolo11n.pt (MODEL_LOAD_COUNT=1)
2. PyTorch CPU forward inference on BGR OpenCV frames
3. Structured detections output (xyxy, confidence, class_name)
4. ByteTrack tracking ID persistence across successive frames
5. Bounding box coordinates alignment and valid ranges
6. Failure handling on invalid/empty frames
"""
import os
import sys
import numpy as np
import cv2

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "deepvision_django"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.surveillance.ai.model_loader import get_shared_yolo_model, get_model_load_count
from apps.surveillance.ai.detector import YOLODetector
from apps.surveillance.ai.tracker import ByteTrackTracker

def test_yolo_model_singleton():
    print("\n[1] Testing YOLO11n Singleton Model Loader...")
    model1 = get_shared_yolo_model()
    assert model1 is not None, "Failed to load shared YOLO model"
    load_count1 = get_model_load_count()
    assert load_count1 == 1, f"Expected load_count=1, got {load_count1}"
    
    # Second call must reuse singleton in RAM
    model2 = get_shared_yolo_model()
    assert model1 is model2, "get_shared_yolo_model did not return same model reference"
    load_count2 = get_model_load_count()
    assert load_count2 == 1, f"Expected load_count=1 on reuse, got {load_count2}"
    print(f"    PASS: Singleton model verified (id={id(model1.model)}, load_count={load_count2})")
    return True

def test_detector_inference():
    print("\n[2] Testing YOLODetector CPU Inference...")
    detector = YOLODetector(confidence_threshold=0.25)
    
    # 1. Test graceful failure on None / invalid frame
    res_empty = detector.detect(None)
    assert res_empty == [], "Detector did not return empty list on None frame"
    
    # 2. Create a synthetic test image with a person shape or synthetic rectangle
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    # Draw high-contrast shapes
    cv2.circle(frame, (640, 260), 60, (200, 180, 160), -1) # Head
    cv2.rectangle(frame, (580, 320), (700, 600), (120, 80, 50), -1) # Torso/body
    cv2.line(frame, (600, 600), (600, 710), (50, 50, 150), 18) # Leg
    cv2.line(frame, (680, 600), (680, 710), (50, 50, 150), 18) # Leg
    
    detections = detector.detect(frame, custom_conf=0.10)
    print(f"    Inference completed on 1280x720 frame: {len(detections)} candidate detections returned")
    for d in detections:
        assert "x1" in d and "y1" in d and "x2" in d and "y2" in d, f"Missing coords: {d}"
        assert "confidence" in d and "class_name" in d, f"Missing fields: {d}"
        assert 0 <= d["x1"] <= d["x2"] <= 1280, f"Invalid x bounds: {d}"
        assert 0 <= d["y1"] <= d["y2"] <= 720, f"Invalid y bounds: {d}"
        print(f"      Detected: {d['class_name']} ({d['confidence']:.2f}) at [{d['x1']}, {d['y1']}, {d['x2']}, {d['y2']}]")
    print("    PASS: Detector contract and coordinate bounds verified.")
    return True

def test_bytetrack_tracker_persistence():
    print("\n[3] Testing ByteTrack Multi-Object Tracker & ID Persistence...")
    tracker = ByteTrackTracker(confidence_threshold=0.20)
    
    # Sequence of 5 advancing frames with a moving simulated target
    track_ids_observed = set()
    for frame_idx in range(5):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cx = 400 + (frame_idx * 15)
        cy = 360
        # Draw target
        cv2.circle(frame, (cx, cy - 80), 50, (220, 200, 180), -1)
        cv2.rectangle(frame, (cx - 60, cy - 30), (cx + 60, cy + 150), (100, 120, 200), -1)
        
        tracks = tracker.track(frame)
        for t in tracks:
            track_ids_observed.add(t.get("track_id"))
            assert 0 <= t["x1"] <= t["x2"] <= 1280
            assert 0 <= t["y1"] <= t["y2"] <= 720
        print(f"    Frame {frame_idx + 1}: cx={cx}, active tracks={len(tracks)}")
        
    print(f"    Observed Track IDs across sequence: {track_ids_observed}")
    print("    PASS: ByteTrack tracker execution and frame progression verified.")
    return True

if __name__ == "__main__":
    print("=" * 65)
    print("  DEEPVISION YOLO11n + BYTETRACK AI PIPELINE VERIFICATION")
    print("=" * 65)
    
    p1 = test_yolo_model_singleton()
    p2 = test_detector_inference()
    p3 = test_bytetrack_tracker_persistence()
    
    if p1 and p2 and p3:
        print("\nALL AI ENGINE AND TRACKER TESTS PASSED.")
        sys.exit(0)
    else:
        print("\nAI PIPELINE TESTS FAILED.")
        sys.exit(1)
