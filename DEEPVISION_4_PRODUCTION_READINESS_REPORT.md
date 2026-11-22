# DeepVision 4.0 — Production Readiness Report

**Report Date:** 2026-11-21  
**Project Root:** `D:\DeepVision`  
**Final Release Classification:** **`RELEASE CANDIDATE — EXTERNAL GATES REMAIN`**

---

## 1. Executive Release Verdict

DeepVision 4.0 passes **all locally verifiable architecture, security, dependency CVE, Vite 8.3.8 / Rolldown WASI frontend build, persistent storage, Restricted-Entry, YOLO26s ONNX + BoT-SORT ReID AI, bounded multi-camera soak, and SQLite baseline checks**.

It is classified as **`RELEASE CANDIDATE — EXTERNAL GATES REMAIN`** (rather than `VERIFIED PRODUCTION-DEPLOYMENT READY`) because deployment and external environment verification gates require explicit user authorization or external infrastructure:
1. **Live Production Redeploy Parity (`BLOCKED`):** Live `https://deepvision-6ie7.onrender.com` and `https://vsw-deepvision.vercel.app` still serve an earlier commit until user-approved deploy runs.
2. **Live External Email OTP & Notifications (`BLOCKED`):** No authorized test email inbox supplied for live SMTP/Resend dispatch.
3. **Live Cloud Storage Bucket (`NOT TESTED`):** `SupabaseStorageBackend` / `S3CompatibleStorageBackend` passed unit/mocked checks, but real bucket credentials do not exist in the local environment.
4. **Linux Container Build, `gunicorn` & `oxlint` CI (`NOT TESTED`):** Local Windows `venv` runs Django/Waitress without Linux `gunicorn`, and `oxlint` native optional bindings are intentionally absent from Windows `node_modules`; Linux `.github/workflows/ci.yml` executes both cleanly on push/PR.
5. **Physical Webcam (`dshow://0`), Authorized LAN RTSP & 30-Minute Soak (`BLOCKED` / `NOT TESTED`):** `verify_dshow0_live.py` failed inside Windows sandbox (`DirectShow failed to open camera index`), no external LAN RTSP camera URL was provided, and endurance testing used the bounded `900`-frame (`17.17s`) multi-camera soak rather than an un-authorized `1800s` run.

---

## 2. Verified Subsystem Summary

| Subsystem | Verification Result | Status |
|---|---|---|
| **Django Unit & Security Suites** | `manage.py check` (`0` issues), `manage.py check --deploy` (`0` issues with 50-char key), `26/26` tests in `apps.accounts.tests` + `apps.surveillance.tests` (incl. `test_mjpeg_redirect_ssrf.py` & `test_security_hardening.py`) | **PASS** |
| **Security & Acceptance Suites** | `verify_release_certification.py` (`6/6`), `verify_blindspot_fixes.py` (`8/8`), `verify_continuous_loop_acceptance.py`, `test_csp_and_startup_loader.py` (`4/4`), isolated `test_login_timeout_and_auth_matrix.py` (`15/15`) | **PASS** |
| **AI Detection, Tracking & Soak** | `test_yolo_and_tracker.py`, `verify_camera_ai_restricted_notifications.py` (`6/6`), `phase_3_4_tracker_motion_benchmark.py` (`BoT-SORT+ReID MOTA=1.0`, `IDF1=1.0`, `HOTA=1.0`), `verify_phase4_5_6_acceptance.py` (`900` frames, `450/450` MP4 decoded per camera, `MODEL_LOAD_COUNT=1`, `0` dangling threads) | **PASS** |
| **Frontend Vite 8.3.8 / Rolldown WASI** | Clean builds to `deepvision_django/static/dist/` (`921ms`) and `frontend/dist/` (`1.34s`, `53` modules, `15` JS chunks, `0` leaked secrets); `Modal.jsx` keyboard focus trap + `useAuth.jsx` cleanup verified | **PASS** |
| **Dependencies & CVEs** | `pip check` (`0` broken), OSV batch audit (`63` Python packages -> `0` CVEs), `npm audit` (`0` vulnerabilities); `requirements-surveillance.txt` & `requirements.txt` floors aligned | **PASS** |
| **Database Integrity & Storage** | Canonical `instance/deepvision.db` intact (`Integrity: ok`, `18` tables, `cc2d13f77b681107`); isolated backup/restore + `verify_storage_persistence.py` passed (`PersistentDirectoryStorageBackend` + mocked Supabase/S3) | **PASS** |
| **Database Schema Signature Note** | `check_db_baseline.py` computes raw `sqlite_master` DDL SHA-256 (`cc2d13f77b681107`); `verify_release_certification.py` computes normalized `PRAGMA table_info` SHA-256 (`591d3f29af800a45`) on the identical 18-table isolated clone — confirmed algorithm difference, zero schema drift | **PASS** |
