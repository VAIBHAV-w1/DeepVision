"""
DeepVision Automated Visual Acceptance Suite (Full Real Browser Capture)
Captures desktop (1440x900) and mobile (390x844) views across all routes.
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

# 1. Obtain authenticated session for real operator (User ID 2)
print("[1] Setting up authenticated operator session (User 2: vaibhavwandkar5@gmail.com)...")
sys.path.insert(0, "D:/DeepVision/deepvision_django")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django
django.setup()
from apps.accounts.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore

s = SessionStore()
s['user_id'] = 2
s.save()
session_cookie_val = s.session_key
print("  Generated authenticated session key:", session_cookie_val[:25] + "...")

cookies_to_add = [
    {"name": "deepvision_django_session", "value": session_cookie_val, "path": "/"}
]

# 2. Chrome
print("[2] Initializing Chrome headless (1440x900)...")
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

from selenium.webdriver.chrome.service import Service

CHROMEDRIVER_PATH = r"C:\Users\vaibh\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"
if os.path.exists(CHROMEDRIVER_PATH):
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
else:
    driver = webdriver.Chrome(options=chrome_options)
driver.set_page_load_timeout(30)

try:
    # 01. Login screen (unauthenticated state)
    print("[3] Capturing 01_login.png...")
    driver.get(f"{BASE_URL}/#login")
    time.sleep(2)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "01_login.png"))

    # Add cookies & navigate to hydrate session
    for ck in cookies_to_add:
        driver.add_cookie(ck)

    
    # 02. Dashboard
    print("[4] Capturing 02_dashboard.png...")
    driver.get(f"{BASE_URL}/#dashboard")
    driver.refresh()
    time.sleep(3)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "02_dashboard.png"))
    print("  Dashboard size:", os.path.getsize(os.path.join(SCREENSHOTS_DIR, "02_dashboard.png")))

    # Desktop Routes to capture
    routes = [
        ("03_cameras_featured.png", "#cameras", 4),
        ("04_camera_preview_dedicated.png", "#camera-preview?id=3", 4),
        ("05_alerts.png", "#alerts", 3),
        ("06_recordings.png", "#recordings", 3),
        ("07_evidence.png", "#evidence", 3),
        ("08_cases.png", "#cases", 5),
        ("09_notifications.png", "#notifications", 3),
        ("10_help.png", "#help", 2),
    ]

    for fname, hash_route, wait_s in routes:
        print(f"  Capturing {fname} ({hash_route})...")
        driver.execute_script(f"window.location.hash = '{hash_route}';")
        time.sleep(wait_s)
        dest_path = os.path.join(SCREENSHOTS_DIR, fname)
        driver.save_screenshot(dest_path)
        print(f"    Saved {fname} ({os.path.getsize(dest_path)} bytes)")

    # Mobile Viewports (390x844)
    print("[5] Resizing to Mobile (390x844) and capturing responsive layouts...")
    driver.set_window_size(390, 844)
    time.sleep(1)

    mobile_routes = [
        ("11_mobile_dashboard.png", "#dashboard", 3),
        ("12_mobile_cameras.png", "#cameras", 4),
        ("13_mobile_alerts.png", "#alerts", 3),
    ]

    for fname, hash_route, wait_s in mobile_routes:
        print(f"  Capturing {fname} ({hash_route})...")
        driver.execute_script(f"window.location.hash = '{hash_route}';")
        time.sleep(wait_s)
        dest_path = os.path.join(SCREENSHOTS_DIR, fname)
        driver.save_screenshot(dest_path)
        print(f"    Saved {fname} ({os.path.getsize(dest_path)} bytes)")

    print("[6] Checking browser console logs...")
    logs = driver.get_log("browser")
    severe_errors = [l for l in logs if l.get("level") == "SEVERE" and "favicon" not in l.get("message", "").lower()]
    print(f"  Browser console severe errors: {len(severe_errors)}")
    for err in severe_errors[:5]:
        print("    ", err.get("message"))

    print("\nVisual acceptance screenshots captured successfully!")

finally:
    driver.quit()
