"""
Measures live HTTP MJPEG stream freshness, chunk arrival cadence, and header latency.
"""
import os
import sys
import time
import urllib.request
import statistics
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deepvision_django")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.sessions.backends.signed_cookies import SessionStore

def get_auth_cookie(user_id=1):
    s = SessionStore()
    s["user_id"] = user_id
    s.save()
    return s.session_key

def test_stream(mode="tracking", duration_sec=4):
    url = f"http://127.0.0.1:8000/api/cameras/4/stream/?mode={mode}"
    session_key = get_auth_cookie(1)
    print(f"\nTesting stream {url} for {duration_sec}s with session cookie...")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DeepVision-Latency-Probe/1.0",
            "Cookie": f"deepvision_django_session={session_key}"
        }
    )

    try:
        resp = urllib.request.urlopen(req, timeout=5.0)
    except Exception as e:
        print(f"Failed to connect to stream: {e}")
        return None

    frames = []
    buffer = bytearray()
    start_time = time.time()
    last_frame_recv_time = time.perf_counter()

    while time.time() - start_time < duration_sec:
        chunk = resp.read(8192)
        if not chunk:
            break
        buffer.extend(chunk)

        while True:
            header_end = buffer.find(b"\r\n\r\n")
            if header_end == -1:
                break
            header_bytes = bytes(buffer[:header_end])
            soi = buffer.find(b"\xff\xd8", header_end)
            if soi == -1:
                break
            eoi = buffer.find(b"\xff\xd9", soi)
            if eoi == -1:
                break

            now_perf = time.perf_counter()
            frame_interval = (now_perf - last_frame_recv_time) * 1000.0
            last_frame_recv_time = now_perf

            header_str = header_bytes.decode("ascii", errors="ignore")
            cap_ts = None
            frame_id = None
            inf_age = None

            for line in header_str.split("\r\n"):
                if "X-Capture-Timestamp:" in line:
                    try:
                        cap_ts = float(line.split(":", 1)[1].strip())
                    except Exception:
                        pass
                elif "X-Frame-ID:" in line:
                    try:
                        frame_id = int(line.split(":", 1)[1].strip())
                    except Exception:
                        pass
                elif "X-Inference-Age:" in line:
                    try:
                        inf_age = float(line.split(":", 1)[1].strip())
                    except Exception:
                        pass

            frames.append({
                "recv_time": now_perf,
                "interval_ms": frame_interval,
                "cap_ts": cap_ts,
                "frame_id": frame_id,
                "inf_age_ms": inf_age,
                "frame_bytes": (eoi + 2) - soi
            })

            # Advance buffer
            buffer = buffer[eoi + 2:]

    resp.close()

    if not frames:
        print("No frames received.")
        return None

    # Filter first 2 frames for interval settling
    valid_intervals = [f["interval_ms"] for f in frames[2:]] if len(frames) > 2 else [f["interval_ms"] for f in frames]
    mean_interval = statistics.mean(valid_intervals) if valid_intervals else 0.0
    measured_stream_fps = 1000.0 / mean_interval if mean_interval > 0 else 0.0

    inf_ages = [f["inf_age_ms"] for f in frames if f["inf_age_ms"] is not None]

    results = {
        "mode": mode,
        "total_frames_received": len(frames),
        "mean_frame_interval_ms": round(mean_interval, 2),
        "stream_fps": round(measured_stream_fps, 1),
        "mean_frame_size_kb": round(statistics.mean([f["frame_bytes"] for f in frames]) / 1024.0, 1),
        "mean_inference_age_ms": round(statistics.mean(inf_ages), 1) if inf_ages else None,
        "p95_inference_age_ms": round(statistics.quantiles(inf_ages, n=20)[18], 1) if len(inf_ages) >= 20 else (round(max(inf_ages), 1) if inf_ages else None),
    }

    print(f"Results for {mode} stream:")
    for k, v in results.items():
        print(f"  {k}: {v}")

    return results

if __name__ == "__main__":
    raw_res = test_stream("raw", duration_sec=3)
    trk_res = test_stream("tracking", duration_sec=4)

    out = {
        "raw_stream": raw_res,
        "tracking_stream": trk_res
    }
    with open("reports/phase1_http_stream_benchmarks.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nStream benchmarks written to reports/phase1_http_stream_benchmarks.json")
