"""
Real Browser End-to-End Password Reset Verification using Headless Chrome
"""
import os
import sys
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "deepvision_django"))
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.accounts.models import User
from django.contrib.auth.hashers import make_password

BASE_URL = "http://127.0.0.1:8000"
SCREENSHOTS_DIR = "D:/DeepVision/verification/screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

test_email = "pwreset_audit_user@deepvision.test"
user = User.objects.get(email=test_email)
user.set_password("OldPassword2026!")
user.clear_reset_otp()
user.save()

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

CHROMEDRIVER_PATH = r"C:\Users\vaibh\.cache\selenium\chromedriver\win64\154.0.8037.92\chromedriver.exe"
if os.path.exists(CHROMEDRIVER_PATH):
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
else:
    driver = webdriver.Chrome(options=chrome_options)

driver.set_page_load_timeout(30)

try:
    print("[1] Navigating to Forgot Password page...")
    driver.get(f"{BASE_URL}/#forgot-password")
    time.sleep(2)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "pwreset_step1_email.png"))

    # Step 1: Submit Email
    print("[2] Entering email address and requesting reset code...")
    email_input = driver.find_element(By.ID, "email")
    email_input.clear()
    email_input.send_keys(test_email)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    time.sleep(3)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "pwreset_step2_otp_prompt.png"))

    # Obtain OTP generated in DB
    user.refresh_from_db()
    # For deterministic verification, set a known OTP
    test_otp = "739215"
    user.password_reset_otp_hash = make_password(test_otp)
    user.save()

    # Step 2: Enter 6-digit OTP
    print(f"[3] Entering 6-digit OTP into digit boxes...")
    otp_boxes = driver.find_elements(By.CSS_SELECTOR, ".otp-box-digit")
    for i, digit in enumerate(test_otp):
        otp_boxes[i].send_keys(digit)
    time.sleep(1)

    print("[4] Submitting OTP verification...")
    driver.find_element(By.ID, "btn-verify").click()
    time.sleep(3)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "pwreset_step3_set_new_pw.png"))

    # Step 3: Enter new password and confirmation
    print("[5] Submitting new password and confirmation...")
    new_pw = "BrandNewSecure2026!"
    pw_input = driver.find_element(By.ID, "password")
    pw_input.clear()
    pw_input.send_keys(new_pw)

    confirm_input = driver.find_element(By.ID, "confirm_password")
    confirm_input.clear()
    confirm_input.send_keys(new_pw)
    time.sleep(1)

    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    time.sleep(4)
    driver.save_screenshot(os.path.join(SCREENSHOTS_DIR, "pwreset_step4_login_redirect.png"))

    # Verify user password in DB
    user.refresh_from_db()
    assert user.check_password(new_pw), "Database password hash does not match new password!"
    print("  [SUCCESS] Database password successfully verified with new password!")

    # Verify current URL is login
    current_url = driver.current_url
    print(f"  Current URL after password reset: {current_url}")
    assert "login" in current_url or "#login" in current_url, f"Expected redirect to login, got {current_url}"

    # Verify console errors
    logs = driver.get_log("browser")
    severe_errors = [l for l in logs if l.get("level") == "SEVERE" and "favicon" not in l.get("message", "").lower()]
    print(f"  Browser severe console errors: {len(severe_errors)}")
    for err in severe_errors:
        print("    ", err.get("message"))
    assert len(severe_errors) == 0, f"Found severe console errors: {severe_errors}"

    print("\nREAL BROWSER PASSWORD RESET WORKFLOW VERIFIED SUCCESSFULLY!")

finally:
    driver.quit()
