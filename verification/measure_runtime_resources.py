"""
Runtime Resource & Concurrency Profiler
Measures CPU, RAM, threads, VideoCapture, CameraWorker, InferenceWorker, and YOLO instances
during idle baseline and active TRACKING + DETECTION streaming.
"""
import os
import sys
import time
import requests
import psutil

BASE_URL = "http://127.0.0.1:8000"

def profile():
    # Find Django process
    django_proc = None
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(p.info['cmdline'] or [])
            if "manage.py" in cmd and "runserver" in cmd:
                # Pick the actual running worker (memory > 10MB)
                if p.memory_info().rss > 10 * 1024 * 1024:
                    django_proc = p
                    break
                elif not django_proc:
                    django_proc = p
        except Exception:
            pass

    # If children exist, check child
    if django_proc and django_proc.children():
        django_proc = django_proc.children()[0]

    print(f"Tracking Process PID: {django_proc.pid} ({django_proc.name()})")

    # Baseline measurement
    baseline_mem = django_proc.memory_info().rss / (1024 * 1024)
    baseline_cpu = django_proc.cpu_percent(interval=1.0)
    baseline_threads = django_proc.num_threads()
    print(f"BASELINE: CPU={baseline_cpu:.1f}%, RAM={baseline_mem:.1f} MB, Threads={baseline_threads}")

    # Active stream test
    stream_url = f"{BASE_URL}/cameras/3/stream/tracking/"
    print(f"Connecting to live TRACKING + DETECTION stream: {stream_url} ...")
    
    start_time = time.time()
    peak_mem = baseline_mem
    peak_cpu = baseline_cpu
    peak_threads = baseline_threads
    
    h_data = {}
    frames_received = 0

    try:
        with requests.get(stream_url, stream=True, timeout=10) as r:
            if r.status_code == 200:
                for chunk in r.iter_content(chunk_size=4096):
                    frames_received += 1
                    elapsed = time.time() - start_time
                    
                    cur_mem = django_proc.memory_info().rss / (1024 * 1024)
                    cur_threads = django_proc.num_threads()
                    peak_mem = max(peak_mem, cur_mem)
                    peak_threads = max(peak_threads, cur_threads)

                    if frames_received % 10 == 0:
                        cur_cpu = django_proc.cpu_percent(interval=0.2)
                        peak_cpu = max(peak_cpu, cur_cpu)

                    # Poll surveillance health once mid-stream
                    if elapsed > 2.0 and not h_data:
                        try:
                            # Use session cookie for vaibhavwandkar5@gmail.com
                            from django.contrib.sessions.backends.signed_cookies import SessionStore
                            s = SessionStore()
                            s['user_id'] = 2
                            s.save()
                            hr = requests.get(f"{BASE_URL}/api/surveillance/health/", cookies={"deepvision_django_session": s.session_key}, timeout=3)
                            if hr.status_code == 200:
                                h_data = hr.json()
                        except Exception:
                            pass

                    if elapsed >= 8.0:
                        break
    except Exception as e:
        print(f"Stream error: {e}")

    duration = time.time() - start_time
    time.sleep(1.0) # Grace period
    post_mem = django_proc.memory_info().rss / (1024 * 1024)

    print("\n============================================================")
    print("  RUNTIME RESOURCE PROFILE RESULTS")
    print("============================================================")
    print(f"Test Duration:           {duration:.2f} seconds")
    print(f"Stream Frames Sampled:   {frames_received}")
    print(f"Observed Baseline RAM:   {baseline_mem:.1f} MB")
    print(f"Observed Peak RAM:       {peak_mem:.1f} MB")
    print(f"Observed Post-Stream RAM:{post_mem:.1f} MB")
    print(f"Observed Baseline CPU:   {baseline_cpu:.1f}%")
    print(f"Observed Peak CPU:       {peak_cpu:.1f}%")
    print(f"Baseline Threads:        {baseline_threads}")
    print(f"Peak Threads:            {peak_threads}")
    print(f"Active Camera Handles:   {h_data.get('django_camera_handles', 'N/A')}")
    print(f"Active YOLO Loads:       {h_data.get('django_yolo_loads', 'N/A')}")
    print(f"Engine Status:           {h_data.get('status', 'N/A')}")
    print("============================================================")

if __name__ == "__main__":
    profile()
