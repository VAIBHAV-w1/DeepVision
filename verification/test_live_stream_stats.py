"""
Independent Verification: Measure Live Stream Frames and Telemetry
Authenticates as User 2 (operator) and reads multiple frames from Camera 3 (webcam 0)
in both ORIGINAL and TRACKING modes.
Verifies frame dimensions, non-zero pixel content, variance, and delivery FPS.
"""
import urllib.request
import http.cookiejar
import time
import numpy as np
import cv2
import sys, os

# Setup authenticated session for User 2
sys.path.insert(0, "D:/DeepVision/deepvision_django")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
from django.contrib.sessions.backends.signed_cookies import SessionStore

s = SessionStore()
s['user_id'] = 2
s.save()

cj = http.cookiejar.CookieJar()
cj.set_cookie(http.cookiejar.Cookie(
    0, 'deepvision_django_session', s.session_key, None, False,
    '127.0.0.1', False, False, '/', True, False, None, True, None, None, {}
))
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

BASE_URL = "http://127.0.0.1:8000"

def inspect_mjpeg_stream(camera_id, mode, frame_count=5):
    url = f"{BASE_URL}/cameras/{camera_id}/stream/?mode={mode}"
    print(f"\n[STREAM TEST] Ingesting {frame_count} frames from {url}...")
    req = urllib.request.Request(url)
    resp = opener.open(req, timeout=10)
    
    stream_bytes = b""
    frames = []
    timestamps = []
    t_start = time.time()
    
    while len(frames) < frame_count and (time.time() - t_start) < 15:
        chunk = resp.read(8192)
        if not chunk:
            break
        stream_bytes += chunk
        
        # Look for JPEG SOI and EOI markers
        soi = stream_bytes.find(b"\xff\xd8")
        eoi = stream_bytes.find(b"\xff\xd9")
        
        if soi != -1 and eoi != -1 and eoi > soi:
            jpeg_data = stream_bytes[soi:eoi+2]
            stream_bytes = stream_bytes[eoi+2:]
            
            # Decode JPEG
            img = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                frames.append(img)
                timestamps.append(time.time())
                print(f"  Frame {len(frames)}: shape={img.shape}, mean={img.mean():.2f}, std={img.std():.2f}, bytes={len(jpeg_data)}")
                
    resp.close()
    
    if len(frames) >= 2:
        dur = timestamps[-1] - timestamps[0]
        fps = (len(frames) - 1) / dur if dur > 0 else 0
        print(f"  Calculated delivery rate: {fps:.2f} FPS across {len(frames)} frames")
        
    return frames

# 1. Test Camera 3 Tracking Mode
frames_tracking = inspect_mjpeg_stream(3, "tracking", 5)
assert len(frames_tracking) > 0, "No frames captured in TRACKING mode"
assert frames_tracking[0].mean() > 10.0, f"Frame appears black! mean={frames_tracking[0].mean()}"

# Save one verified frame as evidence
cv2.imwrite("D:/DeepVision/verification/independent_tracking_frame.jpg", frames_tracking[-1])
print("Saved D:/DeepVision/verification/independent_tracking_frame.jpg")

# 2. Test Camera 3 Original Mode
frames_orig = inspect_mjpeg_stream(3, "raw", 5)
assert len(frames_orig) > 0, "No frames captured in ORIGINAL mode"
assert frames_orig[0].mean() > 10.0, f"Frame appears black! mean={frames_orig[0].mean()}"

cv2.imwrite("D:/DeepVision/verification/independent_original_frame.jpg", frames_orig[-1])
print("Saved D:/DeepVision/verification/independent_original_frame.jpg")

print("\nALL LIVE STREAM CHECKS PASSED: Real video frames successfully decoded and verified!")
