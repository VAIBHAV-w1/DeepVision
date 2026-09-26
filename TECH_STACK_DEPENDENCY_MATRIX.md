# DeepVision Technology Stack — Dependency Matrix

**Date:** 2026-09-26  
**Environment:** Python 3.14.7 AMD64 (Windows 11)  
**Total Installed Distributions:** 49  

---

## 1. Complete Package Classification Matrix

| # | Package Name | Installed Version | Classification | Direct Importer / Parent | Purpose in DeepVision | Action Recommendation |
|---|---|---|---|---|---|---|
| 1 | **Django** | 5.2.17 | **REQUIRED** | Root / `manage.py`, all `apps.*` | Core web application framework, ORM, routing, templates, sessions, CSRF, StreamingHttpResponse | **CORE REQUIRED** |
| 2 | **asgiref** | 3.12.1 | **REQUIRED** | `Django` | Asynchronous server gateway interface dependency for Django | **CORE REQUIRED** (Transitive) |
| 3 | **sqlparse** | 0.6.0 | **REQUIRED** | `Django` | SQL parser and formatter for Django ORM query compilation | **CORE REQUIRED** (Transitive) |
| 4 | **tzdata** | 2026.4 | **REQUIRED** | `Django` | IANA time zone database for Django timezone support | **CORE REQUIRED** (Transitive) |
| 5 | **opencv-python** | 5.0.0.93 | **REQUIRED** | `apps.ai.engine`, `apps.surveillance.*` | Hardware camera acquisition (`CAP_DSHOW`), frame decoding, MJPEG compression, MP4 recording (`VideoWriter`) | **CORE REQUIRED** |
| 6 | **numpy** | 2.5.2 | **REQUIRED** | `opencv-python`, `torch`, `ultralytics`, `reid.py` | Multidimensional pixel arrays, ROI bounding box coordinates, color histogram math | **CORE REQUIRED** |
| 7 | **ultralytics** | 8.4.117 | **REQUIRED** | `apps.surveillance.ai.model_loader`, `tracker.py` | YOLO11n model loader, inference pipeline, ByteTrack tracker coordination | **CORE REQUIRED** |
| 8 | **torch** | 2.13.0+cpu | **REQUIRED** | `ultralytics`, `detector.py`, `tracker.py` | PyTorch deep learning framework for YOLO11 neural network forward pass inference | **CORE REQUIRED** |
| 9 | **torchvision** | 0.28.0 | **REQUIRED** | `ultralytics` | Computer vision operators and transforms for PyTorch | **CORE REQUIRED** (Transitive) |
| 10 | **PyYAML** | 6.0.3 | **REQUIRED** | `ultralytics`, `tracker.py` | YAML parser for `bytetrack.yaml` tracker configuration file | **CORE REQUIRED** |
| 11 | **Werkzeug** | 3.1.8 | **REQUIRED** | `apps.accounts.models` | Werkzeug `scrypt` password hashing compatibility (`check_password_hash`, `generate_password_hash`) | **CORE REQUIRED** |
| 12 | **python-dotenv** | 1.2.2 | **REQUIRED** | `start_deepvision.py`, `config.settings` | Loads environment variables from `.env` | **CORE REQUIRED** |
| 13 | **psutil** | 7.2.2 | **REQUIRED** | `ultralytics`, `verify_phase15_health.py` | System and process CPU, RAM, and thread monitoring | **CORE REQUIRED** |
| 14 | **requests** | 2.34.2 | **REQUIRED** | `ultralytics`, test suites | HTTP client library required by ultralytics | **CORE REQUIRED** (Transitive) |
| 15 | **certifi** | 2026.7.22 | **REQUIRED** | `requests` | Mozilla CA bundle for SSL verification | **CORE REQUIRED** (Transitive) |
| 16 | **charset-normalizer** | 3.4.9 | **REQUIRED** | `requests` | Character encoding detector for HTTP requests | **CORE REQUIRED** (Transitive) |
| 17 | **idna** | 3.18 | **REQUIRED** | `requests` | Internationalized Domain Names in Applications | **CORE REQUIRED** (Transitive) |
| 18 | **urllib3** | 2.7.0 | **REQUIRED** | `requests` | HTTP connection pooling library | **CORE REQUIRED** (Transitive) |
| 19 | **pillow** | 12.3.0 | **REQUIRED** | `ultralytics`, `torchvision` | Image processing library for YOLO input tensor resizing | **CORE REQUIRED** (Transitive) |
| 20 | **matplotlib** | 3.11.1 | **REQUIRED** | `ultralytics` | Plotting and visualization tools required by ultralytics | **CORE REQUIRED** (Transitive) |
| 21 | **contourpy** | 1.3.3 | **REQUIRED** | `matplotlib` | Calculation of contours in 2D image arrays | **CORE REQUIRED** (Transitive) |
| 22 | **cycler** | 0.12.1 | **REQUIRED** | `matplotlib` | Composable style cycles for matplotlib | **CORE REQUIRED** (Transitive) |
| 23 | **fonttools** | 4.63.0 | **REQUIRED** | `matplotlib` | Font manipulation library for text overlay | **CORE REQUIRED** (Transitive) |
| 24 | **kiwisolver** | 1.5.0 | **REQUIRED** | `matplotlib` | Fast implementation of Cassowary constraint solving algorithm | **CORE REQUIRED** (Transitive) |
| 25 | **packaging** | 26.3 | **REQUIRED** | `matplotlib` | Core utilities for Python packages | **CORE REQUIRED** (Transitive) |
| 26 | **pyparsing** | 3.3.2 | **REQUIRED** | `matplotlib` | Parsing library used by matplotlib | **CORE REQUIRED** (Transitive) |
| 27 | **python-dateutil** | 2.9.0.post0 | **REQUIRED** | `matplotlib` | Extensions to standard Python datetime | **CORE REQUIRED** (Transitive) |
| 28 | **six** | 1.17.0 | **REQUIRED** | `python-dateutil` | Python 2 and 3 compatibility library | **CORE REQUIRED** (Transitive) |
| 29 | **filelock** | 3.32.2 | **REQUIRED** | `ultralytics`, `torch` | Platform-independent file lock for multi-threaded cache access | **CORE REQUIRED** (Transitive) |
| 30 | **fsspec** | 2026.7.0 | **REQUIRED** | `torch` | File-system specification for PyTorch weights loading | **CORE REQUIRED** (Transitive) |
| 31 | **networkx** | 3.6.1 | **REQUIRED** | `torch` | Network analysis graphs for PyTorch computations | **CORE REQUIRED** (Transitive) |
| 32 | **sympy** | 1.14.0 | **REQUIRED** | `torch` | Symbolic mathematics library for PyTorch compiler | **CORE REQUIRED** (Transitive) |
| 33 | **mpmath** | 1.3.0 | **REQUIRED** | `sympy` | Arbitrary-precision floating-point arithmetic | **CORE REQUIRED** (Transitive) |
| 34 | **typing_extensions** | 4.16.0 | **REQUIRED** | `asgiref` | Backported type hints | **CORE REQUIRED** (Transitive) |
| 35 | **setuptools** | 84.0.0 | **REQUIRED** | `torch` | Python package installation and compilation utilities | **CORE REQUIRED** (Transitive) |
| 36 | **ultralytics-thop** | 2.1.6 | **REQUIRED** | `ultralytics` | Model FLOPs and computational cost profiler | **CORE REQUIRED** (Transitive) |
| 37 | **nvidia-ml-py** | 13.610.43 | **REQUIRED** | `ultralytics` | NVIDIA Management Library bindings for GPU telemetry | **CORE REQUIRED** (Transitive) |
| 38 | **polars** | 1.43.2 | **REQUIRED** | `ultralytics` | Fast DataFrame library required by ultralytics | **CORE REQUIRED** (Transitive) |
| 39 | **polars-runtime-32** | 1.43.2 | **REQUIRED** | `polars` | Binary runtime engine for polars | **CORE REQUIRED** (Transitive) |
| 40 | **Jinja2** | 3.1.6 | **REQUIRED** | `torch` | Template engine required by PyTorch Inductor | **CORE REQUIRED** (Transitive) |
| 41 | **MarkupSafe** | 3.0.3 | **REQUIRED** | `Werkzeug`, `Jinja2` | String safety escaping for Werkzeug and Jinja2 | **CORE REQUIRED** (Transitive) |
| 42 | **pip** | 25.2 | **DEV ONLY** | Python environment | Python standard package installer | **DEV ONLY** |
| 43 | **lap** | 0.5.13 | **OPTIONAL** | ByteTrack | Linear Assignment Problem solver (C-accelerated Hungarian algorithm) | **OPTIONAL / KEEP** |
| 44 | **SQLAlchemy** | 2.0.51 | **LEGACY / UNUSED** | None (Flask remnant) | Legacy ORM from retired Flask architecture; 0 imports in active code | **SAFE_TO_REMOVE** |
| 45 | **greenlet** | 3.5.5 | **LEGACY / UNUSED** | `SQLAlchemy` | C-extension coroutine dependency for SQLAlchemy async | **SAFE_TO_REMOVE** |
| 46 | **itsdangerous** | 2.2.0 | **LEGACY / UNUSED** | None (Flask remnant) | Legacy Flask session cookie serializer; 0 imports in active code | **SAFE_TO_REMOVE** |
| 47 | **blinker** | 1.9.0 | **LEGACY / UNUSED** | None (Flask remnant) | Legacy Flask signal dispatcher; 0 imports in active code | **SAFE_TO_REMOVE** |
| 48 | **click** | 8.4.2 | **LEGACY / UNUSED** | None (Flask remnant) | Legacy Flask CLI parser; 0 imports in active code | **SAFE_TO_REMOVE** |
| 49 | **colorama** | 0.4.6 | **LEGACY / UNUSED** | `click` | Cross-platform colored terminal output for click | **SAFE_TO_REMOVE** |

---

## 2. Summary by Status

- **Core Required (Directly Imported):** 8 packages (`Django`, `opencv-python`, `numpy`, `ultralytics`, `torch`, `PyYAML`, `Werkzeug`, `python-dotenv`)
- **Core Required (Transitive Dependencies):** 33 packages (`asgiref`, `sqlparse`, `tzdata`, `torchvision`, `pillow`, `matplotlib`, `contourpy`, `cycler`, `fonttools`, `kiwisolver`, `packaging`, `pyparsing`, `python-dateutil`, `six`, `filelock`, `fsspec`, `networkx`, `sympy`, `mpmath`, `typing_extensions`, `setuptools`, `ultralytics-thop`, `nvidia-ml-py`, `polars`, `polars-runtime-32`, `requests`, `certifi`, `charset-normalizer`, `idna`, `urllib3`, `psutil`, `Jinja2`, `MarkupSafe`)
- **Optional Acceleration:** 1 package (`lap` — Linear Assignment Problem acceleration for ByteTrack)
- **Development Tool:** 1 package (`pip`)
- **Genuinely Unused / Legacy Remnants:** 6 packages (`SQLAlchemy`, `greenlet`, `itsdangerous`, `blinker`, `click`, `colorama`)

---

## 3. Safe-To-Remove Candidates vs Requires Review

### Safe to Remove (Orphaned Flask Dependencies):
The following 6 packages have 0 active imports in `deepvision_django`, are not required by any active dependency (`pip check` will continue to pass), and are remnants of the retired Flask architecture:
1. `SQLAlchemy` (and `greenlet`)
2. `itsdangerous`
3. `blinker`
4. `click` (and `colorama`)

*Note: Per the strict Safety Protocol ("Do NOT add/upgrade/downgrade technologies without explicit confirmation"), these packages are documented as candidates and will NOT be silently uninstalled.*

### Requires Review:
- `Werkzeug`: Currently required by `apps/accounts/models.py` (`generate_password_hash`, `check_password_hash`) to verify user passwords stored during previous phases in `users.password_hash` (`scrypt:32768:8:1$...`). Can only be removed if user password hashing is migrated to Django's native `PBKDF2PasswordHasher` or Django's `make_password`/`check_password`.
- `lap`: Used by ByteTrack for fast Hungarian algorithm matrix assignment. Keep installed to prevent fallbacks to slower pure-Python assignment loops.
