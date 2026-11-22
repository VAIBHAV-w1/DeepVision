# DeepVision 4.0 — Release Verification Matrix

**Verification Date:** 2026-11-21  
**Policy:** Every check uses strict statuses only: `PASS`, `FAIL`, `BLOCKED`, `NOT TESTED`, `ACCEPTED RISK`. Canonical SQLite DB (`instance/deepvision.db`) never modified by tests.

---

## 1. Master Production Verification Matrix

| Area | Check / Command | Status | Observed Evidence |
|---|---|---|---|
| **Dependencies** | `npm --prefix frontend audit --audit-level=moderate` | **PASS** | `found 0 vulnerabilities` |
| **Dependencies** | `pip check` & requirements sync (`requirements.txt` vs `requirements-surveillance.txt`) | **PASS** | `No broken requirements found.`; CVE minimum floors synchronized (`werkzeug>=3.1.9`, `certifi>=2026.10.18`, `urllib3>=2.8.0`, `pillow>=13.0.0`, `filelock>=4.2.1`) |
| **Dependencies** | Online PyPI OSV (`https://api.osv.dev/v1/querybatch`) | **PASS** | `PYPI_PKGS_AUDITED: 63`, `VULN_COUNT: 0` |
| **Frontend Build & Lint** | Vite 8.3.8 / Rolldown WASI builds (`static/dist` & `frontend/dist`) | **PASS** | Built `53` modules (`921ms` Django, `1.34s` Vercel); `15` JS bundles each; `0` secret/demo leaks |
| **Frontend Lint (Windows)** | `npm --prefix frontend run lint` (`oxlint`) | **NOT TESTED** | Optional native `@oxlint/binding-win32-x64-msvc` absent in Windows `node_modules` (Linux CI installs ELF binding on `ubuntu-latest`) |
| **Django Checks** | `manage.py check` & `manage.py check --deploy` (`DEBUG=False`, `RENDER=true`, 50-char key) | **PASS** | `0 issues (0 silenced)` |
| **Unit & Security Suites** | `manage.py test apps.accounts.tests apps.surveillance.tests --verbosity=2` | **PASS** | `26/26` tests OK (`test_email_service.py`, `test_security_hardening.py`, `test_mjpeg_redirect_ssrf.py`, `test_reid.py`) |
| **Release Certification** | `verification/verify_release_certification.py` (isolated DB clone) | **PASS** | `6/6` checks PASS; normalized schema signature `591d3f29af800a45` |
| **Blind-Spot & CSP Suites** | `verify_blindspot_fixes.py`, `test_csp_and_startup_loader.py`, `verify_continuous_loop_acceptance.py` | **PASS** | All checks PASS (RBAC, BOLA, bounded pagination, CSP header, isolated backup `cc2d13f77b681107`) |
| **Auth Matrix (Isolated)** | `test_login_timeout_and_auth_matrix.py` (cloned temp SQLite) | **PASS** | `15/15` auth scenarios passed (`zero_data_mutation: True`) |
| **Deployment Hardening** | `test_deployment_hardening.py` | **ACCEPTED RISK** | First `14` Windows/settings/static checks PASS; `LINUX_STARTUP_SELECTION_GUNICORN` exited on Windows due to Linux `gunicorn` absence in Windows `venv` |
| **Persistent Storage (Local)** | `verify_storage_persistence.py` | **PASS** | `PersistentDirectoryStorageBackend` SHA-256, `206` Range playback, sanitized downloads, restart persistence & mocked Supabase/S3 PASS |
| **AI & Restricted-Entry** | `test_yolo_and_tracker.py` (`DEEPVISION_STRICT_NATIVE_AI=1`), `verify_camera_ai_restricted_notifications.py`, `phase_3_4_tracker_motion_benchmark.py` | **PASS** | `yolo26s_openvino_gpu`, `MODEL_LOAD_COUNT=1`, `BoT-SORT+ReID MOTA=1.0`, `IDF1=1.0`, `HOTA=1.0`, Hungarian `<1e-9`, `6/6` restricted-entry/notification checks |
| **Multi-Camera Soak** | `verify_phase4_5_6_acceptance.py` (isolated temp DB) | **PASS** | `900` frames across 2 cameras (`17.17s`), `450/450` MP4 decoded per camera, `0` dangling threads, `rss_steady_delta_mb=-92.6` |
| **Database Baseline** | `verification/check_db_baseline.py` | **PASS** | `Integrity: ok`, `Table count: 18`, raw DDL signature `cc2d13f77b681107` |
| **Physical Webcam (`dshow://0`)** | `verification/verify_dshow0_live.py` (Windows sandbox) | **BLOCKED** | Sandbox failed opening `CAP_DSHOW` index `0` (`DirectShow failed to open camera index`) |
| **Live External Deploy** | Live Render & Vercel redeploy, health/HSTS parity, Linux CI run | **BLOCKED** | Requires user-approved commit, push, and deploy trigger |
| **Live External Email / Bucket / RTSP / 30m Soak** | Live SMTP/Resend inbox, real Supabase/S3 bucket, external LAN RTSP, `1800s` soak | **NOT TESTED** | Awaiting external credentials/targets and deploy authorization |
