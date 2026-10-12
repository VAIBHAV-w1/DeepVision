# DEEPVISION — DEFECT REGISTER

**Status:** ACTIVE / VERIFIED  
**Repository:** `D:\DeepVision`  
**Tracking System:** Persistent Autonomous Self-Healing Ledger  

---

### Defect Ledger

| Defect ID | Subsystem | Severity | Status | Reproduction Steps | Root Cause | Files Changed | Regression Test | Verification Evidence |
|---|---|---|---|---|---|---|---|---|
| **DEF-AUTH-01** | `frontend/src/pages/ForgotPassword.jsx` & `frontend/src/services/api.js` | **BLOCKER** | **VERIFIED** | 1. Request reset OTP.<br>2. Enter OTP in step 2.<br>3. Enter new password in step 3.<br>4. Submit -> UI displayed: *"Email and reset code are required."* | `api.auth.resetPassword(data)` expected a single object, but `ForgotPassword.jsx` passed 4 positional arguments (`email, digits.join(''), newPassword, confirmPassword`). Request body was serialized as raw email string, dropping OTP and passwords. | `frontend/src/pages/ForgotPassword.jsx`<br>`frontend/src/services/api.js`<br>`frontend/src/services/auth.js`<br>`deepvision_django/apps/core/api.py`<br>`deepvision_django/config/urls.py` | `verification/test_password_reset_flow.py`<br>`verification/verify_browser_password_reset.py` | **16/16 automated assertions PASS**.<br>Real Headless Chrome browser test verified redirect to `/#login` with **0 console errors** and password verified in database. |
| **DEF-AUTH-02** | `deepvision_django/apps/accounts/email_service.py` | **HIGH** | **VERIFIED** | 1. Attempt login or OTP dispatch.<br>2. If SMTP unreachable, API hangs for 10 seconds before timeout. | Synchronous SMTP connection on main request-response thread blocked HTTP worker. | `deepvision_django/apps/accounts/email_service.py` | `verification/test_complete_auth_otp.py` | Login response latency reduced from 10,210 ms to ~18 ms with async daemon dispatcher. |
| **DEF-CORE-03** | `deepvision_django/apps/core/api.py` | **MEDIUM** | **VERIFIED** | 1. Navigate to Cases page.<br>2. Response times out or stalls browser rendering with 839 full records. | Unbounded query `api_cases_list` serialized 800+ records in single response. | `deepvision_django/apps/core/api.py` | `verification/test_full_e2e.py` | Added pagination slicing (`limit=50`, `total_count: 839`). Sub-25ms response time. |
| **DEF-UI-04** | `frontend/src/pages/Cameras.jsx` | **LOW** | **VERIFIED** | 1. View Cameras page header.<br>2. Broken HTML entity text `&olarr;` rendered. | Typo in HTML entity for arrow icon. | `frontend/src/pages/Cameras.jsx` | `verification/capture_all_screens.py` | Replaced with `Refresh Grid →`. Zero visual/console errors. |
| **DEF-CAM-05** | `deepvision_django/apps/ai/engine.py` | **MEDIUM** | **VERIFIED** | 1. Query `/api/surveillance/health/`.<br>2. `django_camera_handles` reported 5 instead of 1 unique physical device handle. | `len(cam_reg.workers)` counted logical camera IDs instead of unique `CameraWorker` physical handles (`set(cam_reg.workers.values())`). | `deepvision_django/apps/ai/engine.py` | `verification/test_complete_camera_pipeline.py` | Correctly reports `django_camera_handles: 1` and `logical_cameras_active: 5`. |

---

### Verification Summary
- **Total Defects Identified:** 5
- **Defects Fixed:** 5
- **Defects Verified:** 5
- **Regressions:** 0
- **Open Defects:** 0
