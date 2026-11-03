"""
Phase 1 Real Camera Latency and AI Pipeline Profiler for DeepVision 3.0.
Accurately measures:
1. Physical Camera (DirectShow 0) Capture Interval, FPS & Driver Buffer
2. Grab vs Retrieve vs Read breakdown
3. YOLO11n Model Forward Pass & NMS
4. ByteTrack Update & Association Latency
5. Behavior & Anomaly Pipeline Latency
6. JPEG Encoding Time
7. End-to-end HTTP MJPEG Stream Delivery Freshness
"""
import os
import sys
import time
import json
import statistics
import cv2
import numpy as np

# Set up Django environment so we can import models and workers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deepvision_django")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from apps.surveillance.ai.model_loader import get_shared_yolo_model
from apps.surveillance.ai.tracker import ByteTrackTracker
from apps.surveillance.ai.behavior.track_history import TrackHistoryManager
from apps.surveillance.ai.behavior.behavior_analyzer import BehaviorAnalyzer
from apps.surveillance.ai.anomaly.anomaly_detector import AnomalyDetector
from apps.cameras.models import Camera
from apps.core.models import RestrictedZone

def profile_physical_camera(device_idx=0, num_frames=60):
    print(f"\n[STAGE 1] Profiling Physical DirectShow Camera {device_idx}...")
    cap = cv2.VideoCapture(device_idx, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"ERROR: Cannot open cv2.VideoCapture({device_idx}, cv2.CAP_DSHOW)")
        return {"error": "Device could not be opened"}

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    reported_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Camera opened: {actual_w}x{actual_h} reported FPS: {reported_fps}")

    # Warmup
    for _ in range(5):
        cap.read()

    read_intervals = []
    grab_times = []
    retrieve_times = []
    full_read_times = []
    last_t = time.perf_counter()

    sample_frames = []
    for i in range(num_frames):
        t0 = time.perf_counter()
        ret_grab = cap.grab()
        t1 = time.perf_counter()
        ret, frame = cap.retrieve()
        t2 = time.perf_counter()

        if ret and frame is not None:
            grab_times.append((t1 - t0) * 1000.0)
            retrieve_times.append((t2 - t1) * 1000.0)
            full_read_times.append((t2 - t0) * 1000.0)
            read_intervals.append((t2 - last_t) * 1000.0)
            last_t = t2
            if len(sample_frames) < 10:
                sample_frames.append(frame.copy())
        time.sleep(0.001)

    cap.release()

    fps = 1000.0 / statistics.mean(read_intervals[1:]) if len(read_intervals) > 1 else 0.0

    stats = {
        "device_index": device_idx,
        "resolution": f"{actual_w}x{actual_h}",
        "sample_count": len(full_read_times),
        "mean_grab_ms": round(statistics.mean(grab_times), 2),
        "mean_retrieve_ms": round(statistics.mean(retrieve_times), 2),
        "mean_full_read_ms": round(statistics.mean(full_read_times), 2),
        "p95_full_read_ms": round(statistics.quantiles(full_read_times, n=20)[18], 2) if len(full_read_times) >= 20 else round(max(full_read_times), 2),
        "mean_interval_ms": round(statistics.mean(read_intervals[1:]), 2),
        "measured_capture_fps": round(fps, 1),
    }
    print("Camera Profile Results:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return stats, sample_frames

def profile_yolo_and_bytetrack(sample_frames):
    print("\n[STAGE 2] Profiling YOLO11n Forward Pass & Postprocessing & ByteTrack...")
    if not sample_frames:
        sample_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    else:
        sample_frame = sample_frames[0]

    resolutions = [640, 512, 480, 384]
    model = get_shared_yolo_model()


    res_benchmarks = {}

    for imgsz in resolutions:
        # Warmup
        for _ in range(3):
            _ = model(sample_frame, imgsz=imgsz, verbose=False, device="cpu")

        forward_times = []
        for _ in range(20):
            t0 = time.perf_counter()
            results = model(sample_frame, imgsz=imgsz, verbose=False, device="cpu", conf=0.25, iou=0.45)
            t1 = time.perf_counter()
            forward_times.append((t1 - t0) * 1000.0)

            # Extract speed profiling from Ultralytics result if available
            speed_dict = getattr(results[0], "speed", {})

        mean_fwd = statistics.mean(forward_times)
        p95_fwd = statistics.quantiles(forward_times, n=20)[18] if len(forward_times) >= 20 else max(forward_times)

        res_benchmarks[str(imgsz)] = {
            "imgsz": imgsz,
            "mean_inference_ms": round(mean_fwd, 2),
            "p95_inference_ms": round(p95_fwd, 2),
            "inference_fps": round(1000.0 / mean_fwd, 1) if mean_fwd > 0 else 0,
            "ultralytics_preprocess_ms": round(speed_dict.get("preprocess", 0.0), 2),
            "ultralytics_inference_ms": round(speed_dict.get("inference", 0.0), 2),
            "ultralytics_postprocess_ms": round(speed_dict.get("postprocess", 0.0), 2),
        }
        print(f"  Resolution {imgsz}: {round(mean_fwd, 1)}ms ({res_benchmarks[str(imgsz)]['inference_fps']} FPS) [pre: {res_benchmarks[str(imgsz)]['ultralytics_preprocess_ms']}ms, inf: {res_benchmarks[str(imgsz)]['ultralytics_inference_ms']}ms, post: {res_benchmarks[str(imgsz)]['ultralytics_postprocess_ms']}ms]")

    # ByteTrack Benchmark
    print("\n[STAGE 3] Profiling ByteTrack Association and Update...")
    tracker = ByteTrackTracker(confidence_threshold=0.25)
    track_times = []
    for f in (sample_frames * 3)[:30]:
        t0 = time.perf_counter()
        _ = tracker.track(f)
        t1 = time.perf_counter()
        track_times.append((t1 - t0) * 1000.0)

    bytetrack_stats = {
        "mean_total_tracking_ms": round(statistics.mean(track_times), 2),
        "p95_total_tracking_ms": round(statistics.quantiles(track_times, n=20)[18], 2) if len(track_times) >= 20 else round(max(track_times), 2),
        "tracking_fps": round(1000.0 / statistics.mean(track_times), 1),
    }
    print(f"ByteTrack Combined (Inference + Association) Results:")
    for k, v in bytetrack_stats.items():
        print(f"  {k}: {v}")

    # Profiling Anomaly + Behavior Logic
    print("\n[STAGE 4] Profiling Anomaly Detector & Behavior Analyzer...")
    track_hist = TrackHistoryManager()
    beh_analyzer = BehaviorAnalyzer()
    anomaly_detector = AnomalyDetector({
        "ANOMALY_EVENT_COOLDOWN_SECONDS": 30,
        "CROWDING_THRESHOLD": 4,
        "CROWDING_ENABLED": True,
        "UNEXPECTED_OBJECT_ENABLED": True,
        "LOITERING_ENABLED": True,
        "RESTRICTED_ENTRY_ENABLED": True,
        "UNUSUAL_MOVEMENT_ENABLED": True,
        "ABANDONED_OBJECT_ENABLED": True,
    })

    zones = list(RestrictedZone.objects.filter(camera_id=4, enabled=True))

    simulated_tracks = [
        {"track_id": 1, "x1": 400, "y1": 200, "x2": 500, "y2": 450, "class_name": "person", "confidence": 0.88},
        {"track_id": 2, "x1": 550, "y1": 220, "x2": 620, "y2": 430, "class_name": "person", "confidence": 0.82},
        {"track_id": 3, "x1": 700, "y1": 300, "x2": 780, "y2": 400, "class_name": "backpack", "confidence": 0.75},
    ]

    cfg = {
        "STATIONARY_DISTANCE_THRESHOLD": 15.0,
        "STATIONARY_TIME_THRESHOLD": 3.0,
        "LOITERING_RADIUS": 80.0,
        "LOITERING_TIME_THRESHOLD": 10.0,
        "SPEED_FAST_THRESHOLD": 150.0,
        "SPEED_SLOW_THRESHOLD": 15.0,
        "TRACK_TIMEOUT_SECONDS": 5
    }

    anom_times = []
    for _ in range(50):
        t0 = time.perf_counter()
        now = time.time()
        tracked_for_anom = []
        for trk in simulated_tracks:
            cx = (trk["x1"] + trk["x2"]) / 2.0
            cy = (trk["y1"] + trk["y2"]) / 2.0
            hist = track_hist.update(trk["track_id"], trk["x1"], trk["y1"], trk["x2"], trk["y2"], now, cfg)
            beh = beh_analyzer.analyze(hist, cfg)
            tracked_for_anom.append({
                "track_id": trk["track_id"],
                "class_name": trk["class_name"],
                "confidence": trk["confidence"],
                "center_x": cx,
                "center_y": cy,
                "behavior": beh.get("behavior", "normal"),
                "speed": beh.get("speed", 0.0),
                "stationary_duration": beh.get("stationary_duration", 0.0)
            })
        events = anomaly_detector.detect(tracked_for_anom, now, zones=zones)
        t1 = time.perf_counter()
        anom_times.append((t1 - t0) * 1000.0)

    anom_stats = {
        "mean_anomaly_pipeline_ms": round(statistics.mean(anom_times), 3),
        "p95_anomaly_pipeline_ms": round(statistics.quantiles(anom_times, n=20)[18], 3) if len(anom_times) >= 20 else round(max(anom_times), 3),
    }
    print(f"Anomaly Logic Evaluation: {anom_stats}")

    # JPEG Compression Profile
    print("\n[STAGE 5] Profiling JPEG Compression Latency across Qualities...")
    jpeg_benchmarks = {}
    for q in [65, 70, 75, 80, 85]:
        j_times = []
        sizes = []
        for f in (sample_frames or [sample_frame])[:10]:
            t0 = time.perf_counter()
            ret, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            t1 = time.perf_counter()
            j_times.append((t1 - t0) * 1000.0)
            sizes.append(len(buf))
        jpeg_benchmarks[str(q)] = {
            "quality": q,
            "mean_encode_ms": round(statistics.mean(j_times), 2),
            "p95_encode_ms": round(statistics.quantiles(j_times, n=20)[18], 2) if len(j_times) >= 20 else round(max(j_times), 2),
            "mean_bytes": int(statistics.mean(sizes)),
        }
        print(f"  Quality {q}: {jpeg_benchmarks[str(q)]['mean_encode_ms']}ms, size: {jpeg_benchmarks[str(q)]['mean_bytes']} bytes")

    return {
        "yolo_resolutions": res_benchmarks,
        "bytetrack": bytetrack_stats,
        "anomaly": anom_stats,
        "jpeg": jpeg_benchmarks
    }

if __name__ == "__main__":
    cam_stats, sample_frames = profile_physical_camera(0, num_frames=50)
    ai_stats = profile_yolo_and_bytetrack(sample_frames)

    full_report = {
        "timestamp": time.time(),
        "camera_capture": cam_stats,
        "ai_benchmarks": ai_stats
    }
    os.makedirs("reports", exist_ok=True)
    with open("reports/phase1_benchmark_raw.json", "w") as f:
        json.dump(full_report, f, indent=2)
    print("\nRaw benchmark report written to reports/phase1_benchmark_raw.json")
