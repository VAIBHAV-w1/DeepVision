# DEEPVISION 4.0 — API CONTRACTS SPECIFICATION

**Base URL:** `http://127.0.0.1:8000/api/`  
**Authentication:** Signed Cookie Session (`deepvision_django_session`)  
**CSRF Header:** `X-CSRFToken: <token>` (Required on `POST`, `PUT`, `DELETE`)  

---

## 1. AUTHENTICATION APIS

### 1.1 `GET /api/auth/csrf/`
- **Description:** Generates and returns a fresh CSRF token.
- **Response (200):**
  ```json
  { "csrfToken": "KYXcRUFMTRYi..." }
  ```

### 1.2 `GET /api/auth/me/`
- **Description:** Retrieves current authenticated user session.
- **Response (200 Authenticated):**
  ```json
  { "authenticated": true, "user": { "id": 1, "email": "operator@deepvision.test", "role": "operator", "full_name": "SOC Operator" } }
  ```
- **Response (401 Unauthenticated):**
  ```json
  { "authenticated": false, "user": null }
  ```

### 1.3 `POST /api/auth/login/`
- **Request:**
  ```json
  { "email": "user@deepvision.test", "password": "SecurePassword123!" }
  ```
- **Response (Step 1 - OTP Required):**
  ```json
  { "success": true, "requires_otp": true, "email": "user@deepvision.test" }
  ```

### 1.4 `POST /api/auth/verify-login-otp/`
- **Request:**
  ```json
  { "email": "user@deepvision.test", "otp": "123456" }
  ```
- **Response (200):**
  ```json
  { "success": true, "user": { "id": 1, "email": "user@deepvision.test", "role": "operator" } }
  ```

### 1.5 `POST /api/auth/demo-session/`
- **Description:** Instantly provisions a developer/operator session for localhost evaluation.
- **Response (200):**
  ```json
  { "success": true, "user": { "id": 1, "role": "operator" } }
  ```

---

## 2. DASHBOARD & SYSTEM METRICS

### 2.1 `GET /api/dashboard/stats/`
- **Description:** Returns high-level metrics for the Overview workspace.
- **Response (200):**
  ```json
  {
    "total_cameras": 10,
    "online_cameras": 7,
    "new_alerts_count": 5425,
    "high_critical_count": 124,
    "total_recordings": 3637,
    "total_evidence": 7316,
    "total_cases": 1024,
    "unread_notifications_count": 12
  }
  ```

---

## 3. CAMERA MANAGEMENT & STREAMING

### 3.1 `GET /api/cameras/`
- **Description:** Retrieves all registered camera sources.
- **Response (200):**
  ```json
  {
    "cameras": [
      { "id": 4, "name": "Webcam 0", "source_type": "webcam", "source": "0", "status": "online", "is_active": true }
    ]
  }
  ```

### 3.2 `GET /api/cameras/<id>/`
- **Description:** Detailed configuration for camera `<id>`.

### 3.3 `POST /api/cameras/`
- **Description:** Register a new camera.
- **Request:**
  ```json
  { "name": "Entrance Gate", "source_type": "rtsp", "source": "rtsp://192.168.1.100:554/live", "location": "Building A" }
  ```

### 3.4 `GET /cameras/<id>/stream/?mode=tracking`
- **Protocol:** HTTP Multipart MJPEG (`Content-Type: multipart/x-mixed-replace; boundary=frame`)
- **Modes:** `original` (clean raw video), `tracking` (bounding boxes, track IDs, perimeter boundaries).

### 3.5 `GET /api/cameras/<id>/zones/`
- **Description:** List configured restricted zones for camera.
- **Response (200):**
  ```json
  {
    "zones": [
      { "id": 4, "camera_id": 4, "name": "Webcam 0 Front Perimeter", "x1": 360, "y1": 100, "x2": 920, "y2": 640, "enabled": true }
    ]
  }
  ```

### 3.6 `POST /api/cameras/<id>/zones/`
- **Description:** Create or update a restricted zone. Immediately invalidates in-memory inference zone cache.
- **Request:**
  ```json
  { "name": "Front Perimeter", "x1": 360, "y1": 100, "x2": 920, "y2": 640 }
  ```

---

## 4. SECURITY ALERTS & INCIDENT WORKSPACE

### 4.1 `GET /api/alerts/?page=1&per_page=15`
- **Query Params:** `status`, `severity`, `camera_id`, `has_video`, `search`.
- **Response (200):**
  ```json
  {
    "alerts": [
      { "id": 5500, "camera_id": 4, "event_type": "restricted_area_entry", "severity": "high", "status": "new", "created_at": "2026-10-31T13:25:55Z" }
    ],
    "total_count": 5425,
    "num_pages": 362
  }
  ```

### 4.2 `POST /alerts/<id>/acknowledge/`
- **Description:** Moves alert state from `new` to `acknowledged`.

### 4.3 `POST /alerts/<id>/resolve/`
- **Description:** Moves alert state to `resolved`.

---

## 5. RECORDINGS & EVIDENCE

### 5.1 `GET /api/recordings/?page=1`
- **Response (200):**
  ```json
  {
    "recordings": [
      { "id": 3447, "camera_id": 4, "file_size": 2101608, "duration": 60.0, "created_at": "2026-10-31T13:00:00Z" }
    ]
  }
  ```

### 5.2 `GET /recordings/<id>/view/`
- **Protocol:** HTTP 206 Partial Content (supports `Range: bytes=0-1024`).

### 5.3 `GET /api/evidence/?page=1`
- **Response (200):**
  ```json
  {
    "evidence": [
      { "id": 6940, "alert_id": 5500, "camera_id": 4, "evidence_type": "snapshot", "file_size": 169155, "sha256_hash": "a8f9c1..." }
    ]
  }
  ```

