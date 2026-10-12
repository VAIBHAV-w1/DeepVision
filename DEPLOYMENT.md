# DeepVision Production & Local Deployment Guide

## 1. System Overview & Deployment Topology

DeepVision runs as a unified Django 5.2.17 surveillance core serving a compiled React 18 / Vite 6 single-page application.
The system supports two primary runtime environments:
1. **Native Host Environment (Windows / Linux / macOS)**:
   - Full support for direct host hardware capture devices (such as Windows DirectShow webcams `dshow://0` and Linux Video4Linux `/dev/video0`).
   - In-process native OpenCV video ingestion and PyTorch/YOLO11n object tracking pipeline.
2. **Containerized Environment (Docker & Docker Compose)**:
   - Isolated multi-stage container deployment running under a non-root user (`deepvision`).
   - Designed for server-grade RTSP IP cameras and networked video management systems (VMS).

---

## 2. Environment Prerequisites

### Backend Dependencies
- **Python**: 3.11 or 3.12 (Host runs Python 3.11/3.14 with verified virtual environment).
- **Native Libraries**:
  - `libgl1`, `libglib2.0-0`, `libgomp1` (Linux container requirements for OpenCV and PyTorch).
- **AI Engine**: PyTorch CPU build (`torch`, `torchvision`) and `ultralytics` YOLO11n weights.
- **Database**:
  - Default: Embedded SQLite at `instance/deepvision.db` (18 tables, zero external server dependency).
  - Optional: MySQL 8.0+ via `mysqlclient` (supported via environment toggles).

### Frontend Dependencies
- **Node.js**: v20.x or v22.x LTS.
- **Package Manager**: `npm` v10+.
- **Build Output**: Compiled Vite static assets placed at `deepvision_django/static/dist/`.

---

## 3. Local Host Deployment (Native Windows / DirectShow Support)

This is the recommended deployment for workstations with built-in or USB webcams.

### Step 1: Environment Setup
```powershell
# Clone or navigate to repository root
cd D:\DeepVision

# Activate Python virtual environment
.\venv\Scripts\Activate.ps1

# Verify installed packages
pip check
```

### Step 2: Build Frontend Assets
```powershell
cd frontend
npm install
npm run build
cd ..
```
*Note: Vite outputs `index.html`, `assets/index-*.js`, and `assets/index-*.css` directly into `deepvision_django/static/dist/`.*

### Step 3: Run Database Migrations (Zero Destructive Reset)
```powershell
python manage.py migrate --check
```
The application checks existing SQLite database tables at `instance/deepvision.db` without wiping existing recordings or operator cases.

### Step 4: Start the Surveillance Engine
```powershell
python start_deepvision.py
```
Or start directly with Django:
```powershell
python manage.py runserver 127.0.0.1:8000
```
- Open browser at `http://127.0.0.1:8000/`.
- Default login: Existing security operator account.

---

## 4. Docker Multi-Stage Deployment

### Docker Architecture
- **Stage 1 (`frontend-builder`)**: Uses `node:20-slim` to perform `npm ci` and compile production React SPA assets.
- **Stage 2 (`runtime`)**: Uses `python:3.11-slim`, installs system libraries (`libgl1`, `libglib2.0-0`), installs PyTorch CPU wheels and requirements, sets up non-root user `deepvision:deepvision`, and defines an automated Docker HEALTHCHECK against `/api/health/`.

### Docker Configuration Files
- `Dockerfile`: Multi-stage build definition.
- `docker-compose.yml`: Service definitions with volume mounts for persistence.
- `.dockerignore`: Excludes host virtual environments, logs, and build caches.

### Step 1: Configure Environment Variables
Create or verify `.env` file in the root:
```env
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,0.0.0.0,deepvision-app
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
DJANGO_SECRET_KEY=generate-a-strong-random-key-here
USE_MYSQL=0
```

### Step 2: Build and Run with Docker Compose
```bash
# Build the production image
docker compose build

# Start the container in detached mode
docker compose up -d

# Verify container health
docker compose ps
docker compose logs -f deepvision
```

### Step 3: Volume Persistence
Docker mounts host directories to preserve all application state across container restarts:
- `./instance`: SQLite database and configuration.
- `./recordings`: Stored MP4 video footage.
- `./evidence`: Captured incident snapshot images.
- `./models`: YOLO weights (`yolo11n.pt`).

---

## 5. Critical Hardware & Container Limitations (Honest Disclosure)

### Native Windows Webcam Ingestion in Docker
> [!IMPORTANT]
> Linux-based Docker containers running on Windows (via Docker Desktop WSL2) **cannot directly access Windows DirectShow USB webcams (`dshow://0`)** without specialized device pass-through configurations or network streaming bridges.

- **DirectShow Camera (`dshow://0`)**: Works exclusively when running DeepVision natively on the Windows host.
- **Network IP Cameras (RTSP/HTTP)**: Fully operational in both native Windows and Docker environments (e.g., `rtsp://192.168.1.100:554/live`).
- **Host Bridge Workaround**: If running the backend inside Docker while capturing from a host webcam, use `scripts/host_camera_bridge.py` on the Windows host to relay the webcam as an RTSP/MJPEG feed to the container.

---

## 6. Production Reverse Proxy Configuration (Nginx)

For public or enterprise network deployment, place DeepVision behind Nginx with SSL termination.

```nginx
server {
    listen 80;
    server_name surveillance.deepvision.local;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name surveillance.deepvision.local;

    ssl_certificate /etc/ssl/certs/deepvision.crt;
    ssl_certificate_key /etc/ssl/private/deepvision.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Static file serving directly through Nginx
    location /static/ {
        alias /app/deepvision_django/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    # CRITICAL: Disable buffering for multipart MJPEG live camera streams
    location ~ ^/cameras/\d+/stream/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # General application API and SPA routing
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

---

## 7. Database Backup & Non-Destructive Maintenance

To safely back up the SQLite database without interrupting active surveillance recording:

```powershell
# Execute verified non-destructive backup utility
python scripts/backup_sqlite_db.py
```
This produces a timestamped atomic copy in `backups/deepvision_backup_YYYYMMDD_HHMMSS.db`.
