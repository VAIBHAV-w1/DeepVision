"""
DeepVision One-Shot Docker Portable Distribution Verification Script
Simulates a clean target Windows machine running only the Docker image:
1. Healthcheck verification on isolated port (8005)
2. Static assets & React SPA HTML delivery
3. CSRF token acquisition
4. Clean DB schema auto-initialization verification
5. Fresh user signup in clean database
6. 2FA OTP generation and verification
7. Login flow with mandatory OTP
8. Authenticated access to dashboard, cameras, and alerts
9. Container restart test
10. Data persistence across container lifecycle
"""

import sys
import time
import requests
import subprocess

BASE = "http://127.0.0.1:8005"
CONTAINER_NAME = "deepvision-sim-target"
client = requests.Session()

def run_tests():
    print("=" * 65)
    print("  DEEPVISION PORTABLE DOCKER DISTRIBUTION VERIFICATION")
    print("=" * 65)

    # 1. Healthcheck
    print("[TEST 1] Verifying /api/health/...")
    r = client.get(f"{BASE}/api/health/", timeout=5.0)
    print("         Status:", r.status_code, r.json())
    assert r.status_code == 200
    assert r.json().get("status") == "healthy"

    # 2. React SPA
    print("[TEST 2] Verifying React SPA delivery on root /...")
    r_root = client.get(f"{BASE}/", timeout=5.0)
    print("         Status:", r_root.status_code, "Length:", len(r_root.text))
    assert r_root.status_code == 200
    assert "assets/index" in r_root.text

    # 3. CSRF & Signup
    print("[TEST 3] Fetching CSRF and registering new operator account...")
    csrf = client.get(f"{BASE}/api/auth/csrf/").json().get("csrfToken", "")
    headers = {"X-CSRFToken": csrf}
    
    signup_data = {
        "full_name": "Target Operator",
        "email": "operator@targetmachine.test",
        "password": "TargetPassword2026!",
        "confirm_password": "TargetPassword2026!"
    }
    r_sign = client.post(f"{BASE}/api/auth/signup/", json=signup_data, headers=headers)
    print("         Signup response:", r_sign.status_code, r_sign.json())
    assert r_sign.status_code == 200
    assert r_sign.json().get("success") is True

    # 4. Verify Signup OTP
    print("[TEST 4] Verifying signup OTP...")
    py_code = """
import sys
sys.path.insert(0, '/app/deepvision_django')
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import User
u = User.objects.get(email='operator@targetmachine.test')
otp = u.generate_otp(purpose='signup')
u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts'])
print(otp)
"""
    otp = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", py_code]).decode().strip()
    r_ver = client.post(f"{BASE}/api/auth/verify-otp/", json={"email": "operator@targetmachine.test", "otp": otp}, headers=headers)
    print("         OTP verification:", r_ver.status_code, r_ver.json())
    assert r_ver.status_code == 200
    assert r_ver.json().get("success") is True

    # 5. Login Flow (Step 1 + Step 2)
    print("[TEST 5] Testing Login with mandatory 2FA...")
    r_log1 = client.post(f"{BASE}/api/auth/login/", json={"email": "operator@targetmachine.test", "password": "TargetPassword2026!"}, headers=headers)
    print("         Step 1 response:", r_log1.status_code, r_log1.json())
    assert r_log1.status_code == 200
    assert r_log1.json().get("requires_otp") is True

    py_code_login = """
import sys
sys.path.insert(0, '/app/deepvision_django')
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import User
u = User.objects.get(email='operator@targetmachine.test')
otp = u.generate_otp(purpose='login')
u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts'])
print(otp)
"""
    login_otp = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", py_code_login]).decode().strip()
    r_log2 = client.post(f"{BASE}/api/auth/verify-login-otp/", json={"email": "operator@targetmachine.test", "otp": login_otp}, headers=headers)
    print("         Step 2 response:", r_log2.status_code, r_log2.json())
    assert r_log2.status_code == 200
    assert r_log2.json().get("success") is True

    # 6. Authenticated REST Endpoints
    print("[TEST 6] Accessing protected APIs (Dashboard, Cameras, Alerts)...")
    r_dash = client.get(f"{BASE}/api/dashboard/stats/")
    print("         Dashboard:", r_dash.status_code, r_dash.json().get("system_status"))
    assert r_dash.status_code == 200

    r_cam = client.get(f"{BASE}/api/cameras/")
    print("         Cameras:", r_cam.status_code, "Count:", len(r_cam.json().get("cameras", [])))
    assert r_cam.status_code == 200

    r_alt = client.get(f"{BASE}/api/alerts/")
    print("         Alerts:", r_alt.status_code, "Count:", len(r_alt.json().get("alerts", [])))
    assert r_alt.status_code == 200

    # 7. YOLO Model Weights inside container
    print("[TEST 7] Verifying YOLO11n weights inside container...")
    model_ls = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "ls", "-l", "/app/models/yolo11n.pt"]).decode().strip()
    print("         YOLO11n model file:", model_ls)
    assert "yolo11n.pt" in model_ls

    # 8. Container Restart & Persistence Test
    print("[TEST 8] Restarting container to test volume persistence...")
    subprocess.check_call(["docker", "restart", CONTAINER_NAME])
    time.sleep(4)

    # Wait for restart
    healthy = False
    for i in range(20):
        try:
            hr = requests.get(f"{BASE}/api/health/", timeout=2.0)
            if hr.status_code == 200 and hr.json().get("status") == "healthy":
                healthy = True
                break
        except Exception:
            time.sleep(1)
    assert healthy is True
    print("         Container successfully restarted and healthy.")

    # Check user persistence
    py_check = """
import sys
sys.path.insert(0, '/app/deepvision_django')
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import User
print(User.objects.filter(email='operator@targetmachine.test').exists())
"""
    persisted = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", py_check]).decode().strip()
    print("         User persisted after restart:", persisted)
    assert "True" in persisted

    print("=" * 65)
    print("  ALL 8 PORTABLE CONTAINER CHECKS PASSED PERFECTLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
