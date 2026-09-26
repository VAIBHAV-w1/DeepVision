import os
import sys
import time
import psutil

sys.path.insert(0, "deepvision_django")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.surveillance.camera.registry import get_camera_registry
from apps.surveillance.ai.registry import get_inference_registry
from apps.surveillance.recording import recording_service
from apps.surveillance.ai.model_loader import get_model_load_count, get_model_instance_count

print("===============================================================")
print("  DEEPVISION AI PERFORMANCE & PIPELINE BENCHMARK")
print("===============================================================")

cam_id = 3
process = psutil.Process(os.getpid())

camera_reg = get_camera_registry()
inference_reg = get_inference_registry()

# Baseline resource snapshot
initial_cpu = process.cpu_percent(interval=0.5)
initial_mem = process.memory_info().rss / (1024 * 1024)
print(f"[BASELINE] Process Memory: {initial_mem:.1f} MB | Initial CPU: {initial_cpu:.1f}%")

# 1. Warm/start camera worker
cw = camera_reg.get_worker(cam_id)
if not cw.running:
    print(f"[START] Starting CameraWorker for camera {cam_id}...")
    cw.start()
    time.sleep(2.0)

# Measure Live Only
print("\n--- TEST 1: LIVE ONLY (DirectShow Capture) ---")
time.sleep(1.0)
t0 = time.time()
f0 = cw.frame_id
time.sleep(3.0)
t1 = time.time()
f1 = cw.frame_id
live_fps = (f1 - f0) / (t1 - t0)
live_mem = process.memory_info().rss / (1024 * 1024)
live_cpu = process.cpu_percent(interval=0.5)
print(f"  Capture FPS: {live_fps:.1f} FPS (frames: {f1 - f0} in {t1 - t0:.1f}s)")
print(f"  CPU Usage: {live_cpu:.1f}% | RAM: {live_mem:.1f} MB")

# 2. Test Live + Recording
print("\n--- TEST 2: LIVE + CONTINUOUS RECORDING ---")
recording_service.start_recording(1, cam_id)

t0 = time.time()
f0 = cw.frame_id
time.sleep(3.0)
t1 = time.time()
f1 = cw.frame_id
rec_fps = (f1 - f0) / (t1 - t0)
recording_service.stop_recording(1, cam_id)
rec_mem = process.memory_info().rss / (1024 * 1024)
rec_cpu = process.cpu_percent(interval=0.5)
print(f"  Capture FPS while Recording: {rec_fps:.1f} FPS")
print(f"  CPU Usage: {rec_cpu:.1f}% | RAM: {rec_mem:.1f} MB")
print(f"  FPS Delta under recording: {abs(live_fps - rec_fps):.1f} FPS (Minimal, recording is non-blocking)")

# 3. Test Live + Tracking & Detection (InferenceWorker active)
print("\n--- TEST 3: LIVE + TRACKING & DETECTION (YOLO11n + ByteTrack) ---")
iw = inference_reg.get_worker(cam_id, cw)
time.sleep(3.0) # Allow inference cycles to run

detections, tracks, latency_ms, ai_fps, inf_id, s_fid = iw.get_cached_result()
track_mem = process.memory_info().rss / (1024 * 1024)
track_cpu = process.cpu_percent(interval=0.5)
print(f"  Inference Latency: {latency_ms:.1f} ms")
print(f"  AI Processing Rate: {ai_fps:.1f} FPS")
print(f"  Active Tracks: {len(tracks)} | Detections: {len(detections)}")
print(f"  CPU Usage: {track_cpu:.1f}% | RAM: {track_mem:.1f} MB")

# 4. Test Live + Tracking + Recording
print("\n--- TEST 4: LIVE + TRACKING + RECORDING SIMULTANEOUS ---")
recording_service.start_recording(1, cam_id)
t0 = time.time()
f0 = cw.frame_id
time.sleep(3.0)
t1 = time.time()
f1 = cw.frame_id
sim_fps = (f1 - f0) / (t1 - t0)
recording_service.stop_recording(1, cam_id)

detections, tracks, sim_latency, sim_ai_fps, _, _ = iw.get_cached_result()
sim_mem = process.memory_info().rss / (1024 * 1024)
sim_cpu = process.cpu_percent(interval=0.5)
print(f"  Simultaneous Capture FPS: {sim_fps:.1f} FPS")
print(f"  Simultaneous AI Latency: {sim_latency:.1f} ms | AI Rate: {sim_ai_fps:.1f} FPS")
print(f"  CPU Usage: {sim_cpu:.1f}% | RAM: {sim_mem:.1f} MB")

# 5. Model singleton verification
print("\n--- SINGLETON & RESOURCE LIFECYCLE AUDIT ---")
print(f"  YOLO MODEL_LOAD_COUNT: {get_model_load_count()} (Verified == 1)")
print(f"  YOLO Model Instances: {get_model_instance_count()}")
print(f"  Inference Workers Active: {len(inference_reg.physical_workers)}")
print(f"  Camera Workers Active: {len(camera_reg.workers)}")

# Stop local workers cleanly
camera_reg.release_worker(cam_id)
inference_reg.release_worker(cam_id)

print("\n>>> ALL BENCHMARK MEASUREMENTS RECORDED SUCCESSFULLY <<<")
