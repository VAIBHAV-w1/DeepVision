# DeepVision AI Smart Surveillance — Docker Distribution Guide (v1.1.0)

This distribution package provides a completely self-contained, one-shot deployment of the **DeepVision AI Smart Surveillance Platform** for Windows 10 and Windows 11.

You do **NOT** need to install Python, Node.js, npm, Django, PyTorch, Ultralytics, OpenCV, or Git on your system. Everything runs inside Docker.

---

## 1. System Requirements

* **Operating System**: Windows 10 (64-bit, Pro/Enterprise/Home 21H2+) or Windows 11.
* **Virtualization**: WSL 2 (Windows Subsystem for Linux 2) or Hyper-V enabled.
* **RAM**: 8 GB minimum (16 GB recommended for multi-stream AI processing).
* **Disk Space**: At least 10 GB free disk space.
* **Docker**: Docker Desktop for Windows (installed and running).

---

## 2. Docker Desktop Installation & Setup

1. **Download Docker Desktop**:
   Visit [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/) and download the Windows installer.
2. **Install**:
   Run `Docker Desktop Installer.exe`. Ensure the option **"Use WSL 2 instead of Hyper-V"** is checked.
3. **Restart**:
   Restart your computer if prompted by the installer.
4. **Start Docker Desktop**:
   Launch Docker Desktop from your Start menu.
5. **Verify Running**:
   Wait 15–30 seconds until the Docker whale icon in the Windows taskbar system tray displays **"Engine running"** (green indicator).

---

## 3. Package Contents

Your distribution folder should contain:
```
DeepVision-1.1.0/
│
├── DeepVision-1.1.0-hardened.tar # Pre-packaged hardened Docker image (deepvision:1.1.0-hardened)
├── setup_deepvision.ps1      # PowerShell one-shot setup script
├── setup_deepvision.bat      # Double-clickable Windows batch launcher
├── docker-compose.yml        # Self-contained image-only Docker Compose file (deepvision:1.1.0-hardened)
├── .env.example              # Configuration template
└── README-DOCKER.md          # This operational guide
```

---

## 4. Setup Methods

### Method A: One-Click Launcher (Recommended for Windows)
1. Double-click **`setup_deepvision.bat`**.
2. The batch launcher runs `setup_deepvision.ps1` via PowerShell with execution policy bypass.
3. The setup script executes the following verified sequence:
   - **Docker Validation**: Verifies Docker CLI is available (`docker --version`) and Docker Engine daemon is reachable (`docker info`).
   - **Hardened Image Import**: Checks if `deepvision:1.1.0-hardened` is already present. If not, automatically loads `DeepVision-1.1.0-hardened.tar` and verifies the hardened tag is present (fails closed if missing).
   - **Preflight & Mount Validation**: Confirms host bind mounts (`instance`, `models`, `recordings`) and validates that `instance/deepvision.db` exists, has 18 tables, and passes SQLite integrity checks before starting. Fails closed if validation fails.
   - **Container & Secret Setup**:
     - Inspects existing container `deepvision-app`. If an existing container uses an older/unhardened image, it recreates the container with `deepvision:1.1.0-hardened` while preserving Windows host bind mounts (`D:\DeepVision\instance`, `models`, `recordings`).
     - If creating a new container, automatically generates a secure, random 50-character `DJANGO_SECRET_KEY` in memory for this computer.
     - Launches `deepvision-app` with the published port bound to localhost loopback (`127.0.0.1:8000:8000`).
   - **Health Verification**: Polls `http://127.0.0.1:8000/api/health/` every second for up to 30 seconds until the service reports `healthy`.
   - **Browser Launch**: Once healthy, automatically launches your default web browser to: **http://localhost:8000** (can be skipped by running `setup_deepvision.ps1 -NoBrowser`).

### Method B: PowerShell Command Line
Open PowerShell in the `DeepVision-1.1.0` folder and run:
```powershell
.\setup_deepvision.ps1
```
*Optional parameters:*
* `-Port 8080`: Bind to an alternate host port if port 8000 is in use.
* `-NoBrowser`: Start the container without automatically opening the web browser.
* `-AllowUpgrade`: Authorize a safe staged upgrade of an existing container with older image.

#### Safe Staged Upgrade & Rollback Behavior
If an existing `deepvision-app` container is detected with an older image:
1. **Safety Gate (Default)**: Setup halts with `[UPGRADE BLOCKED]` to protect live production operations and prevent unprompted replacements.
2. **Staged Upgrade (`-AllowUpgrade`)**:
   - **Quiescent State Establishment**: Stops the running container (`docker stop deepvision-app`) so no transactions, dirty buffers, or write locks are active.
   - **Consistent SQLite Backup**: Creates a consistent backup at `instance/deepvision.db.pre-upgrade.bak` using SQLite's native backup API (supporting both WAL and rollback-journal modes) and validates SQLite integrity, 18 tables, baseline signature `cc2d13f77b681107`, and 11 secondary indexes. If backup or validation fails, the old container is immediately restarted and the upgrade aborts before the candidate is launched.
   - **Container Preservation**: Renames the verified old container to `deepvision-app-backup`, preserving all environment variables, images, and inspect metadata.
   - **Candidate Launch & Health Gate**: Launches the candidate container with `deepvision:1.1.0-hardened` and probes `http://127.0.0.1:8000/api/health/` (strictly requiring `status: healthy`, `database: connected`, and `django_app: online`). If the candidate exits early, the health check loop terminates immediately.
   - **Automated Rollback on Failure**: If the candidate fails to start or fails healthcheck:
     1. Candidate container is stopped and removed (`docker rm -f deepvision-app`).
     2. Pre-upgrade database snapshot is restored over `instance/deepvision.db` (reverting any partial writes made by the candidate during its trial window).
     3. Previous container is renamed back (`deepvision-app-backup` -> `deepvision-app`) and restarted.
   - **Operational Limitations & Disclosures**:
     - *Downtime*: Unavoidable brief downtime occurs while host port 8000 is transferred between containers.
     - *Trial Writes*: Restoring the pre-upgrade snapshot eliminates candidate schema mutations, but any external client writes committed during the candidate's failed 30-second trial window are reverted. Zero data loss during a failed trial cannot be guaranteed if live traffic was accepted.
     - *Abrupt Power Loss*: In-flight host power failure or kernel panics cannot be automatically recovered in code. In such an event, manual recovery is supported:
       ```powershell
       # If candidate failed during power loss:
       docker rm -f deepvision-app
       Copy-Item instance\deepvision.db.pre-upgrade.bak instance\deepvision.db -Force
       docker rename deepvision-app-backup deepvision-app
       docker start deepvision-app
       ```

### Method C: Docker Compose (Manual Multi-Step)
If you prefer managing the container directly with Docker Compose:

1. **Open PowerShell in the distribution directory**:
   ```powershell
   cd D:\DeepVision\DeepVision-1.1.0
   ```

2. **Load the hardened Docker image archive**:
   ```powershell
   docker load -i DeepVision-1.1.0-hardened.tar
   ```
   *Verify the hardened image tag is loaded:*
   ```powershell
   docker images deepvision:1.1.0-hardened
   ```

3. **Configure Environment (`.env`)**:
   `docker-compose.yml` strictly enforces `${DJANGO_SECRET_KEY:?...}` and fails closed if it is missing.

   * **If `.env` does not yet exist:**
     Copy the template and generate a fresh random key:
     ```powershell
     Copy-Item .env.example .env
     $secret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 50 | ForEach-Object { [char]$_ })
     (Get-Content .env) -replace 'your_django_secret_key_here', $secret | Set-Content .env
     ```
   * **If `.env` already exists:**
     Preserve your existing configuration (custom ports, SMTP credentials, etc.). Ensure `DJANGO_SECRET_KEY` is defined with a secure key of at least 32 characters:
     ```powershell
     Get-Content .env | Select-String "DJANGO_SECRET_KEY"
     ```

4. **Start the container in the background**:
   ```powershell
   docker compose up -d
   ```

5. **Verify health status**:
   ```powershell
   docker compose ps
   ```

---

## 5. Accessing the Application

Once setup finishes, open your browser to:
```
http://localhost:8000
```

* **First Time User**: Click **Sign Up** to create an administrative or operator user. A fresh, clean database schema is automatically initialized on first run.
* **Two-Factor Authentication (2FA)**: Every signup and login generates a secure 6-digit OTP code to protect operational surveillance integrity.

---

## 6. Daily Management Commands

All standard management commands are run from PowerShell or Command Prompt:

### View Status
```powershell
docker ps
```
The status column will display `Up X minutes (healthy)`.

### View Live Logs
```powershell
docker logs -f deepvision-app
```

### Stop DeepVision
```powershell
docker stop deepvision-app
```
*(Or if using compose: `docker compose stop`)*

### Restart DeepVision
```powershell
docker start deepvision-app
```
*(Or if using compose: `docker compose start`)*

### Remove Container (Preserving Data)
```powershell
docker rm -f deepvision-app
```
*(Your database, AI models, and video recordings remain safely stored in your Windows host directories: `instance`, `models`, and `recordings`).*

---

## 7. Data Persistence & Host Bind Mounts

DeepVision directly mounts persistent Windows host directories into the container:
* **`instance/` (`D:\DeepVision\instance`) → `/app/instance`**: Stores the SQLite database (`deepvision.db`), accounts, alert logs, and system settings.
* **`models/` (`D:\DeepVision\models`) → `/app/models`**: Stores YOLO AI model weights (`yolo11n.pt`).
* **`recordings/` (`D:\DeepVision\recordings`) → `/app/recordings`**: Stores continuous recordings, event clips, and forensic exports.

Because host bind mounts map directly to your local drive, **stopping, restarting, or upgrading the container never deletes your surveillance records, incidents, or user accounts**.
Before starting the container, DeepVision executes strict preflight validation on `instance/deepvision.db`:
* **Integrity Check**: Runs `PRAGMA integrity_check` to verify database file consistency.
* **Table Schema Signature (`cc2d13f77b681107`)**: Verifies all 18 core application tables, column types, and constraints match the canonical baseline schema.
* **Secondary Index Validation**: Validates the 11 performance and uniqueness B-tree indexes (`ix_*`) independently from table DDL.
* **Fail-Closed Mode**: Any missing, corrupt, incomplete, or signature-mismatched database causes startup to halt immediately, preventing silent data overwrite or empty database initialization.

---


## 8. Physical DirectShow Webcam Note

* **Inside Docker**: The Linux container natively processes IP cameras, RTSP streams, pre-recorded test video files, forensic evidence review, and all AI detection/tracking models.
* **Physical USB / DirectShow Webcam**: Linux Docker containers running on Windows cannot directly access physical DirectShow hardware devices (`dshow://0`) due to Windows OS kernel isolation.
* If you need to stream directly from a built-in laptop webcam or USB webcam plugged into the Windows host, the lightweight Python host camera bridge (`scripts/host_camera_bridge.py`) can be run on the Windows host to bridge the physical DirectShow camera to Docker via `http://host.docker.internal:8554`.
* For standard networked CCTV / RTSP cameras, no host bridge is required; Docker connects directly over the network.

---

## 9. Security & Secret Configuration

* **Never share or commit `.env`**: If you customize `.env`, do not publish or distribute your private keys or SMTP credentials.
* **Fail-Closed Secret Enforcement**: When `DJANGO_DEBUG=False`, DeepVision strictly requires a unique, high-entropy `DJANGO_SECRET_KEY` (minimum 32 characters). Hardcoded fallback keys are blocked at startup.
* **Automatic Key Generation**: `setup_deepvision.ps1` dynamically generates a high-entropy 50-character cryptographically secure key (`DJANGO_SECRET_KEY`) unique to each deployment machine.
* **Localhost Loopback Isolation**: Container ports are bound strictly to `127.0.0.1` by default to prevent unwanted exposure to adjacent physical LAN devices.
* **Allowed Hosts & CSRF Protection**: Wildcard `0.0.0.0` is strictly excluded from `DJANGO_ALLOWED_HOSTS` and CSRF trusted origins to prevent host header manipulation.

---

## 10. Troubleshooting

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `Docker daemon not reachable` | Docker Desktop is stopped | Open Docker Desktop from the Start menu and wait until the status displays "Engine running". |
| `Port 8000 already in use` | Another service is using port 8000 | Run `setup_deepvision.ps1 -Port 8080` to bind to port 8080 instead. |
| `Container reports (unhealthy)` | Startup delay or port blockage | Run `docker logs deepvision-app` to inspect Django launcher output. |
| `Cannot connect to physical webcam` | Windows hardware DirectShow webcam isolation | Verify camera index or use RTSP / network stream. |
