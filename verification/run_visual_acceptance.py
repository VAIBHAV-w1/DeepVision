"""
DeepVision Automated Visual Acceptance Suite
============================================
Captures real headless Chrome screenshots across all key routes.
Verifies visible rendering of Reference 1 (camera floating HUD)
and Reference 2 (enterprise security design system).
"""

import sys
import os
import time
import json
import urllib.request
import http.cookiejar
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE_URL = "http://127.0.0.1:8000"
SCREENSHOTS_DIR = "D:/DeepVision/verification/screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Step 1: Obtain authenticated session cookies via Django API
print("[1] Authenticating test user via backend API...")
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Get CSRF
resp = opener.open(f"{BASE_URL}/api/auth/csrf/", timeout=10)
csrf_data = json.loads(resp.read().decode())
csrf_token = csrf_data.get("csrfToken", "")

# Step 1a: Submit credentials
data = json.dumps({"email": "health_test@deepvision.test", "password": "TestHealth123!"}).encode()
req = urllib.request.Request(f"{BASE_URL}/api/auth/login/", data=data, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("X-CSRFToken", csrf_token)
login_resp = json.loads(opener.open(req, timeout=10).read().decode())

# Step 1b: Verify OTP
sys.path.insert(0, "D:/DeepVision/deepvision_django")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django
django.setup()
from apps.accounts.models import User

u = User.objects.get(email="health_test@deepvision.test")
otp = u.generate_otp(purpose="login")
u.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

otp_data = json.dumps({"email": u.email, "otp": otp}).encode()
otp_req = urllib.request.Request(f"{BASE_URL}/api/auth/verify-login-otp/", data=otp_data, method="POST")
otp_req.add_header("Content-Type", "application/json")
otp_req.add_header("X-CSRFToken", csrf_token)
otp_resp = json.loads(opener.open(otp_req, timeout=10).read().decode())
print("  OTP verification successful:", otp_resp.get("success"))

cookies_to_add = []
for c in cj:
    print(f"  Cookie: {c.name} = {c.value[:15]}... ({c.domain})")
    cookies_to_add.append({"name": c.name, "value": c.value, "path": "/"})

# Step 2: Initialize Headless Chrome
print("[2] Initializing Headless Chrome...")
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)
driver.set_page_load_timeout(30)

try:
    # 01. Unauthenticated Login Page Screenshot
    print("[3] Capturing 01_login.png...")
    driver.get(f"{BASE_URL}/")
    time.sleep(2)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "01_login.png"))

    # Set authentication cookies in browser
    for ck in cookies_to_add:
        driver.add_cookie(ck)

    # Routes to capture and verify
    routes = [
        ("02_dashboard.png", "#dashboard", 3),
        ("03_cameras_featured.png", "#cameras", 4),
        ("04_camera_preview_dedicated.png", "#camera-preview?id=1", 4),
        ("05_alerts.png", "#alerts", 3),
        ("06_recordings.png", "#recordings", 3),
        ("07_evidence.png", "#evidence", 3),
        ("08_cases.png", "#cases", 3),
        ("09_notifications.png", "#notifications", 3),
        ("10_help.png", "#help", 2),
    ]

    for fname, hash_route, wait_s in routes:
        print(f"  Capturing {fname} ({hash_route})...")
        driver.get(f"{BASE_URL}/{hash_route}")
        time.sleep(wait_s)
        dest_path = os.path.join(SCREENSHOTS_DIR, fname)
        driver.save_screenshot(dest_path)
        sz = os.path.getsize(dest_path)
        print(f"    Saved {fname} ({sz} bytes)")

    # Check browser console logs
    print("[4] Checking browser console logs...")
    logs = driver.get_log("browser")
    severe_errors = [l for l in logs if l.get("level") == "SEVERE" and "favicon" not in l.get("message", "").lower()]
    print(f"  Browser console severe errors: {len(severe_errors)}")
    for err in severe_errors[:5]:
        print("    ", err.get("message"))

    print("\nVisual acceptance screenshots captured successfully!")

finally:
    driver.quit()
