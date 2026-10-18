# ==============================================================================
# DeepVision AI Smart Surveillance - One-Shot Docker Setup Script
# Targets: Windows 10 / Windows 11 with Docker Desktop
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$NoBrowser,
    [string]$Port = "8000",
    [switch]$AllowUpgrade
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DeepVision Docker Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ImageArchive = Join-Path $ScriptDir "DeepVision-1.1.0-hardened.tar"
if (-not (Test-Path $ImageArchive)) {
    $ImageArchive = Join-Path $ScriptDir "DeepVision-1.1.0.tar"
}
$ImageName = "deepvision:1.1.0-hardened"
$ContainerName = "deepvision-app"
$HealthUrl = "http://127.0.0.1:$Port/api/health/"
$AppUrl = "http://localhost:$Port"

# [1/5] Verify Docker CLI is installed
Write-Host "[1/5] Checking Docker installation..." -NoNewline
try {
    $dockerVersion = docker --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker CLI exited with code $LASTEXITCODE"
    }
    Write-Host " [OK] ($dockerVersion)" -ForegroundColor Green
} catch {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "ERROR: Docker CLI is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Docker Desktop for Windows from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    exit 1
}

# [2/5] Verify Docker Engine is running
Write-Host "[2/5] Checking Docker Engine daemon..." -NoNewline
try {
    $dockerPing = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon not reachable"
    }
    Write-Host " [OK] (Docker Engine is running)" -ForegroundColor Green
} catch {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "ERROR: Docker Desktop is installed but the Docker daemon/engine is not running." -ForegroundColor Red
    Write-Host "Please start Docker Desktop, wait until the whale icon shows 'Engine running', and run this script again." -ForegroundColor Yellow
    exit 1
}

# [3/5] Check image archive and load image
Write-Host "[3/5] Checking DeepVision image..." -NoNewline
$hasImage = (docker images -q $ImageName)
if (-not $hasImage) {
    if (-not (Test-Path $ImageArchive)) {
        Write-Host " [FAILED]" -ForegroundColor Red
        Write-Host ""
        Write-Host "ERROR: Image archive '$ImageArchive' not found and '$ImageName' is not in local Docker." -ForegroundColor Red
        Write-Host "Ensure '$ImageArchive' is located in the same directory as this script." -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""
    Write-Host "      Loading image archive ($ImageArchive)..." -ForegroundColor Yellow
    docker load -i $ImageArchive
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to load Docker image archive." -ForegroundColor Red
        exit 1
    }
    $hasImage = (docker images -q $ImageName)
    if (-not $hasImage) {
        Write-Host " [FAILED]" -ForegroundColor Red
        Write-Host ""
        Write-Host "ERROR: Loaded archive '$ImageArchive' did not provide image '$ImageName'." -ForegroundColor Red
        Write-Host "Cannot fall back to unhardened baseline image. Please verify the distribution package." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "      Docker image '$ImageName' loaded successfully." -ForegroundColor Green
} else {
    Write-Host " [OK] (Image '$ImageName' is already present)" -ForegroundColor Green
}

# Locate host bind mount directories
$RootDir = $null
if ($env:DEEPVISION_ROOT_DIR -and (Test-Path (Join-Path $env:DEEPVISION_ROOT_DIR "instance"))) {
    $RootDir = $env:DEEPVISION_ROOT_DIR
} elseif (Test-Path (Join-Path $ScriptDir "instance")) {
    $RootDir = $ScriptDir
} else {
    $ParentDir = Split-Path -Parent $ScriptDir
    if (Test-Path (Join-Path $ParentDir "instance")) {
        $RootDir = $ParentDir
    }
}

if (-not $RootDir) {
    Write-Host "ERROR: Could not locate DeepVision root directory containing 'instance'." -ForegroundColor Red
    Write-Host "Searched: '$ScriptDir' and '$ParentDir'." -ForegroundColor Yellow
    Write-Host "Set DEEPVISION_ROOT_DIR environment variable or run from repository root." -ForegroundColor Yellow
    exit 1
}

# Resolve canonical absolute paths
$RootDir = (Resolve-Path $RootDir).Path
$InstanceDir = Join-Path $RootDir "instance"
$ModelsDir = Join-Path $RootDir "models"
$RecordingsDir = Join-Path $RootDir "recordings"

if (-not (Test-Path $InstanceDir)) {
    Write-Host "ERROR: Required host directory '$InstanceDir' not found." -ForegroundColor Red
    Write-Host "DeepVision requires Windows bind mount 'instance' -> '/app/instance'." -ForegroundColor Yellow
    exit 1
}
$InstanceDir = (Resolve-Path $InstanceDir).Path

if (-not (Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Path $ModelsDir -Force | Out-Null
}
$ModelsDir = (Resolve-Path $ModelsDir).Path

if (-not (Test-Path $RecordingsDir)) {
    New-Item -ItemType Directory -Path $RecordingsDir -Force | Out-Null
}
$RecordingsDir = (Resolve-Path $RecordingsDir).Path

$DbFile = Join-Path $InstanceDir "deepvision.db"

# [4/6] Preflight database and host mount validation (Fail-Closed)
Write-Host "[4/6] Validating database and host mounts..." -NoNewline

if (-not (Test-Path $DbFile)) {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "ERROR: Production SQLite database not found at '$DbFile'." -ForegroundColor Red
    Write-Host "Fail-closed: Container will NOT be started to prevent silent data loss or blank database creation." -ForegroundColor Red
    Write-Host "Please ensure your existing 'deepvision.db' is located in '$InstanceDir'." -ForegroundColor Yellow
    exit 1
}

if ((Get-Item $DbFile).Length -eq 0) {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "ERROR: Production database file '$DbFile' is empty (0 bytes)." -ForegroundColor Red
    Write-Host "Fail-closed: Container launch halted to prevent running with an empty database." -ForegroundColor Yellow
    exit 1
}

# Run SQLite integrity, schema tables, and SHA-256 signature validation against baseline cc2d13f77b681107
$pyCheck = @'
import sqlite3, hashlib, sys
try:
    p = sys.argv[1]
    conn = sqlite3.connect('file:' + p + '?mode=ro', uri=True)
    c = conn.cursor()
    c.execute('PRAGMA integrity_check;')
    r = c.fetchone()[0]
    if r != 'ok':
        sys.stderr.write(f'INTEGRITY_FAIL: {r}\n')
        sys.exit(1)
    c.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name NOT LIKE \'sqlite_%\';')
    tables = {row[0] for row in c.fetchall()}
    req = {'alerts','audit_logs','camera_groups','cameras','detection_profiles','devices','evidence','incident_cases','incident_notes','incident_playbooks','incident_policies','notification_preferences','notifications','products','recordings','restricted_zones','surveillance_presets','users'}
    missing = req - tables
    if missing:
        sys.stderr.write(f'SCHEMA_FAIL: missing {sorted(missing)}\n')
        sys.exit(2)
    if len(tables) < 18:
        sys.stderr.write(f'TABLE_COUNT_FAIL: {len(tables)}\n')
        sys.exit(3)
    c.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' ORDER BY name;')
    schema_sql = ''.join(str(r[0]) for r in c.fetchall())
    sig = hashlib.sha256(schema_sql.encode('utf-8')).hexdigest()[:16]
    if sig != 'cc2d13f77b681107':
        sys.stderr.write(f'SIGNATURE_MISMATCH: got {sig}, expected cc2d13f77b681107\n')
        sys.exit(4)
    c.execute('SELECT name FROM sqlite_master WHERE type=\'index\' AND name NOT LIKE \'sqlite_%\';')
    indexes = {row[0] for row in c.fetchall()}
    req_idx = {'ix_audit_logs_action','ix_audit_logs_created_at','ix_audit_logs_user_id','ix_incident_cases_alert_id','ix_incident_cases_case_number','ix_incident_cases_user_id','ix_incident_notes_alert_id','ix_incident_notes_user_id','ix_recordings_camera_id','ix_recordings_user_id','ix_users_email'}
    missing_idx = req_idx - indexes
    if missing_idx:
        sys.stdout.write(f'INDEX_NOTICE: missing {sorted(missing_idx)}\n')
    sys.stdout.write('VALIDATION_OK\n')
    sys.exit(0)
except Exception as e:
    sys.stderr.write(f'VALIDATION_ERROR: {e}\n')
    sys.exit(5)
finally:
    if 'conn' in locals() and conn:
        conn.close()
'@

$pyCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pyCmd = "py"
}

$validated = $false
$validationOutput = ""

if ($pyCmd) {
    $validationOutput = & $pyCmd -c $pyCheck "$DbFile" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $validated = $true
    }
} else {
    # Host Python unavailable: execute containerized validation using the verified hardened Docker image
    $pyContainerScript = @'
import sqlite3, hashlib, sys
try:
    p = '/app/instance/deepvision.db'
    conn = sqlite3.connect('file:' + p + '?mode=ro', uri=True)
    c = conn.cursor()
    c.execute('PRAGMA integrity_check;')
    r = c.fetchone()[0]
    if r != 'ok':
        sys.stderr.write(f'INTEGRITY_FAIL: {r}\n')
        sys.exit(1)
    c.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name NOT LIKE \'sqlite_%\';')
    tables = {row[0] for row in c.fetchall()}
    req = {'alerts','audit_logs','camera_groups','cameras','detection_profiles','devices','evidence','incident_cases','incident_notes','incident_playbooks','incident_policies','notification_preferences','notifications','products','recordings','restricted_zones','surveillance_presets','users'}
    missing = req - tables
    if missing:
        sys.stderr.write(f'SCHEMA_FAIL: missing {sorted(missing)}\n')
        sys.exit(2)
    if len(tables) < 18:
        sys.stderr.write(f'TABLE_COUNT_FAIL: {len(tables)}\n')
        sys.exit(3)
    c.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' ORDER BY name;')
    schema_sql = ''.join(str(r[0]) for r in c.fetchall())
    sig = hashlib.sha256(schema_sql.encode('utf-8')).hexdigest()[:16]
    if sig != 'cc2d13f77b681107':
        sys.stderr.write(f'SIGNATURE_MISMATCH: got {sig}, expected cc2d13f77b681107\n')
        sys.exit(4)
    c.execute('SELECT name FROM sqlite_master WHERE type=\'index\' AND name NOT LIKE \'sqlite_%\';')
    indexes = {row[0] for row in c.fetchall()}
    req_idx = {'ix_audit_logs_action','ix_audit_logs_created_at','ix_audit_logs_user_id','ix_incident_cases_alert_id','ix_incident_cases_case_number','ix_incident_cases_user_id','ix_incident_notes_alert_id','ix_incident_notes_user_id','ix_recordings_camera_id','ix_recordings_user_id','ix_users_email'}
    missing_idx = req_idx - indexes
    if missing_idx:
        sys.stdout.write(f'INDEX_NOTICE: missing {sorted(missing_idx)}\n')
    sys.stdout.write('VALIDATION_OK\n')
    sys.exit(0)
except Exception as e:
    sys.stderr.write(f'VALIDATION_ERROR: {e}\n')
    sys.exit(5)
finally:
    if 'conn' in locals() and conn:
        conn.close()
'@

    $dockerCheck = docker run --rm --entrypoint python -v "${InstanceDir}:/app/instance:ro" $ImageName -c $pyContainerScript 2>&1
    if ($LASTEXITCODE -eq 0) {
        $validated = $true
    } else {
        $validationOutput = $dockerCheck
    }
}

if (-not $validated) {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "ERROR: SQLite integrity and schema preflight validation failed for '$DbFile'." -ForegroundColor Red
    if ($validationOutput) {
        Write-Host "Detail: $validationOutput" -ForegroundColor Red
    } else {
        Write-Host "Neither Python on host nor Docker containerized Python could validate the database." -ForegroundColor Red
    }
    Write-Host "Fail-closed: Container launch halted to prevent data loss or silent re-initialization." -ForegroundColor Yellow
    Write-Host "Please ensure Python 3 is installed on host, or verify Docker image '$ImageName' is functional." -ForegroundColor Yellow
    exit 1
}

Write-Host " [OK] (18 tables, signature cc2d13f77b681107, integrity ok)" -ForegroundColor Green

# [5/6] Start DeepVision container
Write-Host "[5/6] Starting DeepVision container..." -NoNewline

$existingImage = docker inspect --format '{{.Config.Image}}' $ContainerName 2>$null
$existingStatus = docker inspect --format '{{.State.Status}}' $ContainerName 2>$null
$backupContainerName = "${ContainerName}-backup"
$dbSnapshot = "$DbFile.pre-upgrade.bak"

function Invoke-Rollback {
    param (
        [string]$Reason,
        [bool]$CandidateRan = $false,
        [bool]$OldWasRenamed = $false,
        [bool]$OldWasStopped = $false
    )
    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Red
    Write-Host " UPGRADE ABORTED / FAILED: $Reason" -ForegroundColor Red
    Write-Host " Initiating safe rollback of original container and database..." -ForegroundColor Yellow
    Write-Host "================================================================================" -ForegroundColor Red

    # 1. Stop and remove candidate container if it was launched or created
    if ($CandidateRan -or (docker inspect $ContainerName 2>$null)) {
        Write-Host "  [1/4] Stopping and removing candidate container '$ContainerName'..." -ForegroundColor Yellow
        docker stop $ContainerName 2>$null | Out-Null
        docker rm -f $ContainerName 2>$null | Out-Null
        $cStillExists = docker inspect --format '{{.State.Status}}' $ContainerName 2>$null
        if ($cStillExists) {
            Write-Host "CRITICAL ERROR: Candidate container '$ContainerName' could not be removed (status: $cStillExists)!" -ForegroundColor Red
            Write-Host "ABORTING AUTOMATIC DATABASE RESTORATION to prevent concurrent writes or corruption." -ForegroundColor Red
            Write-Host "MANUAL RECOVERY REQUIRED:" -ForegroundColor Yellow
            Write-Host "  1. Run 'docker rm -f $ContainerName' manually." -ForegroundColor Yellow
            Write-Host "  2. Run 'Copy-Item -Path $dbSnapshot -Destination $DbFile -Force'." -ForegroundColor Yellow
            if ($OldWasRenamed) {
                Write-Host "  3. Run 'docker rename $backupContainerName $ContainerName'." -ForegroundColor Yellow
            }
            if ($OldWasStopped) {
                Write-Host "  4. Run 'docker start $ContainerName'." -ForegroundColor Yellow
            }
            return
        }
        Write-Host "        Candidate container successfully removed." -ForegroundColor Green
    } else {
        Write-Host "  [1/4] Candidate container was not launched; skipping container removal." -ForegroundColor Cyan
    }

    # 2. Restore database snapshot ONLY IF candidate was launched (which may have written to the DB)
    if ($CandidateRan -and (Test-Path $dbSnapshot)) {
        Write-Host "  [2/4] Restoring pre-upgrade database snapshot from '$dbSnapshot'..." -ForegroundColor Yellow
        try {
            Copy-Item -Path $dbSnapshot -Destination $DbFile -Force
            Write-Host "        Database snapshot restored successfully to '$DbFile'." -ForegroundColor Green
            Write-Host "        Note: Any trial writes from the failed candidate have been reverted." -ForegroundColor Yellow
        } catch {
            Write-Host "CRITICAL ERROR: Failed to automatically restore database snapshot: $_" -ForegroundColor Red
            Write-Host "ABORTING AUTOMATIC OLD-CONTAINER RESTART to protect against running on a corrupted or partial database." -ForegroundColor Red
            Write-Host "MANUAL RECOVERY REQUIRED:" -ForegroundColor Yellow
            Write-Host "  1. Manually copy '$dbSnapshot' over '$DbFile': Copy-Item '$dbSnapshot' '$DbFile' -Force" -ForegroundColor Yellow
            if ($OldWasRenamed) {
                Write-Host "  2. Run 'docker rename $backupContainerName $ContainerName'." -ForegroundColor Yellow
            }
            Write-Host "  3. Run 'docker start $ContainerName' (or start $backupContainerName)." -ForegroundColor Yellow
            return
        }
    } else {
        Write-Host "  [2/4] Live database was not modified by candidate; preservation intact." -ForegroundColor Green
    }

    # 3. Rename old container back if it was renamed
    if ($OldWasRenamed) {
        Write-Host "  [3/4] Renaming '$backupContainerName' back to '$ContainerName'..." -ForegroundColor Yellow
        docker rename $backupContainerName $ContainerName 2>$null | Out-Null
        $verifyRenamed = docker inspect --format '{{.Name}}' $ContainerName 2>$null
        if ($LASTEXITCODE -ne 0 -or $verifyRenamed -notmatch "/?$ContainerName$") {
            Write-Host "CRITICAL ERROR: Failed to rename '$backupContainerName' back to '$ContainerName'!" -ForegroundColor Red
            Write-Host "MANUAL RECOVERY REQUIRED:" -ForegroundColor Yellow
            Write-Host "  1. Verify container status: docker ps -a" -ForegroundColor Yellow
            Write-Host "  2. Run 'docker rename $backupContainerName $ContainerName'." -ForegroundColor Yellow
            Write-Host "  3. Run 'docker start $ContainerName'." -ForegroundColor Yellow
            return
        }
        Write-Host "        Container successfully restored to name '$ContainerName'." -ForegroundColor Green
    } else {
        Write-Host "  [3/4] Container name was not altered; skipping rename." -ForegroundColor Cyan
    }

    # 4. Restart original container if it was stopped
    if ($OldWasStopped) {
        Write-Host "  [4/4] Restarting original container '$ContainerName'..." -ForegroundColor Yellow
        docker start $ContainerName 2>$null | Out-Null
        $curStatus = docker inspect --format '{{.State.Status}}' $ContainerName 2>$null
        if ($curStatus -eq "running") {
            Write-Host "        Original container '$ContainerName' is running and healthy." -ForegroundColor Green
        } else {
            Write-Host "WARNING: Could not automatically confirm original container is running (status: $curStatus)." -ForegroundColor Red
            Write-Host "MANUAL RECOVERY REQUIRED: Run 'docker start $ContainerName'." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [4/4] Original container was not stopped." -ForegroundColor Cyan
    }

    Write-Host ""
    Write-Host "Rollback sequence completed. Deployment remains blocked." -ForegroundColor Yellow
    Write-Host "================================================================================" -ForegroundColor Red
}

if ($existingImage) {
    if ($existingImage -eq $ImageName) {
        if ($existingStatus -eq "running") {
            Write-Host " [OK] (Already running with '$ImageName')" -ForegroundColor Green
        } else {
            Write-Host " [Starting existing stopped container]..." -ForegroundColor Yellow
            docker start $ContainerName | Out-Null
        }
    } else {
        # An existing container is using an older/different image
        if (-not $AllowUpgrade) {
            Write-Host " [UPGRADE BLOCKED]" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "================================================================================" -ForegroundColor Yellow
            Write-Host " SAFETY GATE: Existing container '$ContainerName' uses image '$existingImage'." -ForegroundColor Yellow
            Write-Host " Target release image is '$ImageName'." -ForegroundColor Cyan
            Write-Host ""
            Write-Host " In-place upgrade carries critical operational considerations:" -ForegroundColor Yellow
            Write-Host "  1. Host port 127.0.0.1:$Port conflict requires stopping the old container." -ForegroundColor Yellow
            Write-Host "  2. The new container accesses the live shared database at '$DbFile'." -ForegroundColor Yellow
            Write-Host "     If the new container makes database changes before failing healthcheck," -ForegroundColor Yellow
            Write-Host "     zero data loss cannot be guaranteed without restoring a pre-upgrade snapshot." -ForegroundColor Yellow
            Write-Host "  3. Deployment is blocked by default to protect production continuity." -ForegroundColor Yellow
            Write-Host ""
            Write-Host " To execute a staged upgrade with automated database snapshot and rollback:" -ForegroundColor White
            Write-Host "   .\setup_deepvision.ps1 -AllowUpgrade" -ForegroundColor Cyan
            Write-Host "================================================================================" -ForegroundColor Yellow
            exit 1
        }

        # Staged upgrade requested via -AllowUpgrade
        Write-Host " [STAGED UPGRADE]" -ForegroundColor Yellow
        Write-Host "      Existing container '$ContainerName' uses '$existingImage'." -ForegroundColor Yellow
        Write-Host "      Target release image: '$ImageName'." -ForegroundColor Yellow

        $oldStopped = $false
        $oldRenamed = $false
        $candidateStarted = $false
        $candidateId = $null

        try {
            # Step 1: Quiescent state establishment - stop old container first
            Write-Host "      [1/4] Stopping existing container '$ContainerName' to establish quiescent database state..." -ForegroundColor Cyan
            docker stop $ContainerName | Out-Null
            $oldStopped = $true

            # Step 2: Consistent pre-upgrade database backup using SQLite native backup API
            Write-Host "      [2/4] Creating consistent pre-upgrade database backup at '$dbSnapshot'..." -ForegroundColor Cyan
            $backupOk = $false
            $backupOutput = ""

            $startPy = Join-Path $RootDir "start_deepvision.py"
            if ($pyCmd -and (Test-Path $startPy)) {
                $backupOutput = & $pyCmd $startPy --create-backup "$DbFile" "$dbSnapshot" 2>&1
                if ($LASTEXITCODE -eq 0 -and (Test-Path $dbSnapshot)) {
                    $backupOk = $true
                }
            } elseif ($pyCmd) {
                $pyBackupScript = @'
import sqlite3, hashlib, sys
from pathlib import Path

src_p = Path(sys.argv[1])
dst_p = Path(sys.argv[2])
if not src_p.exists() or src_p.stat().st_size == 0:
    sys.stderr.write(f'Source DB invalid: {src_p}\n')
    sys.exit(1)

src = sqlite3.connect(f'file:{src_p.resolve()}?mode=ro', uri=True)
if dst_p.exists():
    dst_p.unlink()
dst = sqlite3.connect(str(dst_p.resolve()))
src.backup(dst)
dst.close()
src.close()

vconn = sqlite3.connect(f'file:{dst_p.resolve()}?mode=ro', uri=True)
vc = vconn.cursor()
vc.execute('PRAGMA integrity_check;')
if vc.fetchone()[0] != 'ok':
    sys.stderr.write('Backup integrity check failed\n')
    sys.exit(2)
vc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = {r[0] for r in vc.fetchall()}
req = {'alerts','audit_logs','camera_groups','cameras','detection_profiles','devices','evidence','incident_cases','incident_notes','incident_playbooks','incident_policies','notification_preferences','notifications','products','recordings','restricted_zones','surveillance_presets','users'}
if req - tables or len(tables) < 18:
    sys.stderr.write('Backup missing required tables\n')
    sys.exit(3)
vc.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
sig = hashlib.sha256(''.join(str(r[0]) for r in vc.fetchall()).encode('utf-8')).hexdigest()[:16]
if sig != 'cc2d13f77b681107':
    sys.stderr.write('Backup signature mismatch\n')
    sys.exit(4)
vc.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';")
indexes = {r[0] for r in vc.fetchall()}
req_idx = {'ix_audit_logs_action','ix_audit_logs_created_at','ix_audit_logs_user_id','ix_incident_cases_alert_id','ix_incident_cases_case_number','ix_incident_cases_user_id','ix_incident_notes_alert_id','ix_incident_notes_user_id','ix_recordings_camera_id','ix_recordings_user_id','ix_users_email'}
if req_idx - indexes:
    sys.stderr.write('Backup missing secondary indexes\n')
    sys.exit(5)
vconn.close()
sys.stdout.write('BACKUP_VERIFIED_OK\n')
sys.exit(0)
'@
                $backupOutput = & $pyCmd -c $pyBackupScript "$DbFile" "$dbSnapshot" 2>&1
                if ($LASTEXITCODE -eq 0 -and (Test-Path $dbSnapshot)) {
                    $backupOk = $true
                }
            } else {
                $backupOutput = docker run --rm -v "${InstanceDir}:/app/instance" $ImageName python /app/start_deepvision.py --create-backup /app/instance/deepvision.db /app/instance/deepvision.db.pre-upgrade.bak 2>&1
                if ($LASTEXITCODE -eq 0 -and (Test-Path $dbSnapshot)) {
                    $backupOk = $true
                }
            }

            if (-not $backupOk) {
                Write-Host " [BACKUP FAILED]" -ForegroundColor Red
                Invoke-Rollback -Reason "Pre-upgrade database backup creation or validation failed ($backupOutput)" -CandidateRan $false -OldWasRenamed $false -OldWasStopped $true
                exit 1
            }
            Write-Host "        Consistent pre-upgrade database backup verified (18 tables, signature cc2d13f77b681107, 11 indexes)." -ForegroundColor Green

            # Step 3: Preserve old container
            Write-Host "      [3/4] Preserving previous container as '$backupContainerName'..." -ForegroundColor Cyan
            docker rm -f $backupContainerName 2>$null | Out-Null
            docker rename $ContainerName $backupContainerName | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Invoke-Rollback -Reason "Failed to rename container '$ContainerName' to '$backupContainerName'" -CandidateRan $false -OldWasRenamed $false -OldWasStopped $true
                exit 1
            }
            $oldRenamed = $true

            # Step 4: Launch candidate container
            $SecretKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 50 | ForEach-Object { [char]$_ })
            Write-Host "      [4/4] Launching candidate container '$ContainerName' with '$ImageName'..." -ForegroundColor Cyan

            $candidateOutput = docker run -d `
                --name $ContainerName `
                --restart unless-stopped `
                -p "127.0.0.1:${Port}:8000" `
                -v "${InstanceDir}:/app/instance" `
                -v "${ModelsDir}:/app/models" `
                -v "${RecordingsDir}:/app/recordings" `
                -e DEEPVISION_HOST=0.0.0.0 `
                -e DEEPVISION_PORT=8000 `
                -e DJANGO_DEBUG=False `
                -e "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,deepvision-app" `
                -e "DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:${Port},http://localhost:${Port}" `
                -e "DJANGO_SECRET_KEY=$SecretKey" `
                $ImageName 2>&1

            if ($LASTEXITCODE -ne 0) {
                Invoke-Rollback -Reason "Failed to launch candidate container ($candidateOutput)" -CandidateRan $false -OldWasRenamed $true -OldWasStopped $true
                exit 1
            }
            $candidateStarted = $true
            $candidateId = $candidateOutput.Trim()
            Write-Host " [OK] (Candidate container '$ContainerName' started: $candidateId)" -ForegroundColor Green

            # Health Check Gate
            Write-Host "[6/6] Waiting for DeepVision candidate to report full readiness..." -NoNewline
            $maxRetries = 30
            $healthy = $false

            for ($i = 1; $i -le $maxRetries; $i++) {
                Start-Sleep -Seconds 1

                # Check if candidate is still running
                $cStatus = docker inspect --format '{{.State.Status}}' $candidateId 2>$null
                if ($cStatus -ne "running") {
                    Write-Host " [CONTAINER EXITED]" -ForegroundColor Red
                    Write-Host "Candidate container exited unexpectedly with status '$cStatus'." -ForegroundColor Red
                    break
                }

                try {
                    $resp = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
                    if ($resp -and $resp.status -eq "healthy" -and $resp.database -eq "connected" -and $resp.django_app -eq "online") {
                        $healthy = $true
                        break
                    }
                } catch {
                    # Keep waiting
                }
                Write-Host "." -NoNewline
            }

            if (-not $healthy) {
                Invoke-Rollback -Reason "Candidate container failed health check within $maxRetries seconds" -CandidateRan $true -OldWasRenamed $true -OldWasStopped $true
                exit 1
            }

            # If we reach here, upgrade succeeded!
            Write-Host " [HEALTHY]" -ForegroundColor Green
            Write-Host "      Upgrade verified fully healthy! Previous container preserved as '$backupContainerName'." -ForegroundColor Green
            Write-Host "      Pre-upgrade database snapshot preserved at '$dbSnapshot'." -ForegroundColor Green

        } catch {
            Invoke-Rollback -Reason "Unexpected error during upgrade: $_" -CandidateRan $candidateStarted -OldWasRenamed $oldRenamed -OldWasStopped $oldStopped
            exit 1
        }
    }
} else {
    # Fresh deployment when no existing container exists
    $SecretKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 50 | ForEach-Object { [char]$_ })

    docker run -d `
        --name $ContainerName `
        --restart unless-stopped `
        -p "127.0.0.1:${Port}:8000" `
        -v "${InstanceDir}:/app/instance" `
        -v "${ModelsDir}:/app/models" `
        -v "${RecordingsDir}:/app/recordings" `
        -e DEEPVISION_HOST=0.0.0.0 `
        -e DEEPVISION_PORT=8000 `
        -e DJANGO_DEBUG=False `
        -e "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,deepvision-app" `
        -e "DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:${Port},http://localhost:${Port}" `
        -e "DJANGO_SECRET_KEY=$SecretKey" `
        $ImageName | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host " [FAILED]" -ForegroundColor Red
        Write-Host "ERROR: Failed to launch Docker container." -ForegroundColor Red
        exit 1
    }
    Write-Host " [OK] (Container '$ContainerName' created and started)" -ForegroundColor Green

    # Wait for health check
    Write-Host "[6/6] Waiting for DeepVision to become healthy..." -NoNewline
    $maxRetries = 30
    $healthy = $false

    for ($i = 1; $i -le $maxRetries; $i++) {
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp -and $resp.status -eq "healthy" -and $resp.database -eq "connected" -and $resp.django_app -eq "online") {
                $healthy = $true
                break
            }
        } catch {
            # Keep waiting
        }
        Write-Host "." -NoNewline
    }

    if (-not $healthy) {
        Write-Host " [TIMEOUT]" -ForegroundColor Red
        Write-Host "WARNING: Container started, but healthcheck did not report 'healthy' within $maxRetries seconds." -ForegroundColor Yellow
        Write-Host "Inspect container logs with: docker logs $ContainerName" -ForegroundColor Yellow
        exit 1
    }
    Write-Host " [HEALTHY]" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DeepVision is READY." -ForegroundColor Green
Write-Host ""
Write-Host " URL:        $AppUrl" -ForegroundColor Cyan
Write-Host " Container:  $ContainerName" -ForegroundColor Cyan
Write-Host " Status:     Healthy" -ForegroundColor Green
Write-Host " Storage:    Host Bind Mounts ($InstanceDir, $ModelsDir, $RecordingsDir)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Open $AppUrl in your browser to begin." -ForegroundColor White

if (-not $NoBrowser) {
    try {
        Start-Process $AppUrl
    } catch {
        # Browser auto-open is optional
    }
}
