# DEEPVISION CODE CLEANUP & CONSOLIDATION INVENTORY

**Date:** 2026-10-22  
**Target Architecture:** Django + React 18 / Vite Single-Origin Delivery  
**Deployment Gate:** STRICTLY BLOCKED  

---

## 1. Cleanup Principles Enforced

1. **Evidence-Based Deletions Only:** No files deleted without verifying zero imports, zero dynamic imports, zero Django URL registrations, and zero test dependencies.
2. **Strict Preservation of Core Assets:**
   - Database files (`deepvision_django/db.sqlite3` and Docker volumes) preserved intact.
   - All 2,742 archived recordings and 5,558 forensic evidence snapshot assets preserved.
   - Neural model weights (`yolo11n.pt`) and inference singleton preserved.
   - User credentials, test operator accounts, and PBKDF2 hashes preserved.
   - All 15 OTP security invariants (hashes, expiry, lockout, cooldowns) preserved.
3. **No Parallel Competing Architectures:**
   - Single authoritative API client (`frontend/src/services/api.js`).
   - Single dual-mode route registry in `App.jsx`.
   - Single authoritative CSS token system in `frontend/src/styles/globals.css`.

---

## 2. Deletions & Consolidations Inventory

| Item / File | Category | Action | Evidence & Rationale |
| :--- | :--- | :---: | :--- |
| `frontend/src/pages/Cameras.jsx` (`sirenActive`, `spotlightActive`, `micActive`, `audioActive`) | Component State | Removed | Unused mock states from early UI prototype. Webcams lack mechanical sirens/spotlights; removing prevents confusion with real surveillance capabilities. |
| `deepvision_django/apps/core/api.py` (`recent_alerts_qs` NameError & `alert_type` AttributeError) | Backend API | Repaired & Consolidated | Restored proper serialization of `recent_alerts` using canonical `event_type` attribute on the `Alert` model. |
| `deepvision_django/apps/core/api.py` (`api_recordings_list` `user_id` NameError) | Backend API | Repaired & Scoped | Replaced undefined `user_id` reference with `get_accessible_cameras_qs(request.user)` to allow operator roles to query the recordings library without 500 errors. |
| `deepvision_django/apps/accounts/views.py` (`login_view`, `signup_view`) | Auth Views | Hardened | Added `is_authenticated` guard to redirect already-authenticated sessions directly to `/dashboard/`, preventing desynchronization on page reload. |
| `frontend/src/App.jsx` (`parseRoute`) | Router | Upgraded | Consolidated hash-only routing into dual pathname/hash routing listening to both `popstate` and `hashchange` events, eliminating content leaks on direct URL navigations. |
| `docker-compose.yml` (SMTP environment configuration) | Container Config | Updated | Added `env_file: - .env` so container runtime inherits live Gmail SMTP credentials for reliable OTP email delivery. |

---

## 3. Retained Core Modules & Dependencies

| Module | Location | Status | Rationale |
| :--- | :--- | :---: | :--- |
| `react` & `react-dom` (v19) | `frontend/package.json` | Retained | Core UI rendering library. |
| `vite` (v8) | `frontend/package.json` | Retained | High-performance build tool generating static distribution in `< 600ms`. |
| `CameraLivePlayer.jsx` | `frontend/src/components/common/` | Retained | Live surveillance video canvas with DirectShow stream, YOLO11n boxes, and ByteTrack telemetry HUD. |
| `api.js` | `frontend/src/services/` | Retained | Centralized API client with relative endpoints, CSRF token attachment, timeout handling, and session authentication. |
| `incident_service.py` | `deepvision_django/apps/alerts/` | Retained | Incident context aggregator scoping evidence, notes, and cases to alert IDs. |
| `engine.py` | `deepvision_django/apps/ai/` | Retained | Surveillance engine singleton managing frame capture, YOLO11n inference, and ByteTrack tracking. |
| `db.sqlite3` | `deepvision_django/` | Retained | SQLite database housing 16 users, 10 cameras, 4,487 alerts, 841 cases, 2,742 recordings, 5,558 evidence items. |
