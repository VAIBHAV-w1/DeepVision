"""
DeepVision Unified Native Production Launcher
=============================================
Launches the unified native Django application:
  Django (Port 8000)
      ↓
  Native Surveillance Services
      ↓
  OpenCV / DirectShow (dshow://0)
      ↓
  YOLO11n + ByteTrack
      ↓
  Recording / Evidence / Alerts / Cases / Notifications

Usage:
    python start_deepvision.py

Graceful shutdown: Ctrl+C / SIGTERM
"""

import os
import sys
import time
import signal
import socket
import logging
import sqlite3
import hashlib
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")
DJANGO_DIR = ROOT_DIR / "deepvision_django"
PYTHON_EXE = sys.executable
venv_py_win = ROOT_DIR / "venv" / "Scripts" / "python.exe"
venv_py_posix = ROOT_DIR / "venv" / "bin" / "python"
if venv_py_win.exists() and sys.prefix == sys.base_prefix:
    PYTHON_EXE = str(venv_py_win)
elif venv_py_posix.exists() and sys.prefix == sys.base_prefix:
    PYTHON_EXE = str(venv_py_posix)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DEEPVISION-LAUNCHER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("Launcher")

django_proc = None
shutdown_requested = False


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info("Shutdown signal received — terminating DeepVision Django process...")
    shutdown_requested = True
    terminate_processes()
    sys.exit(0)


def terminate_processes():
    global django_proc
    if django_proc and django_proc.poll() is None:
        logger.info("Stopping Django application process (PID %s)...", django_proc.pid)
        django_proc.terminate()
        try:
            django_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            django_proc.kill()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)



EXPECTED_TABLE_COUNT = 18
EXPECTED_SCHEMA_SIGNATURE = "cc2d13f77b681107"
REQUIRED_SCHEMA_TABLES = frozenset([
    "alerts", "audit_logs", "camera_groups", "cameras",
    "detection_profiles", "devices", "evidence", "incident_cases",
    "incident_notes", "incident_playbooks", "incident_policies",
    "notification_preferences", "notifications", "products",
    "recordings", "restricted_zones", "surveillance_presets", "users"
])

EXPECTED_SECONDARY_INDEXES = frozenset([
    "ix_audit_logs_action",
    "ix_audit_logs_created_at",
    "ix_audit_logs_user_id",
    "ix_incident_cases_alert_id",
    "ix_incident_cases_case_number",
    "ix_incident_cases_user_id",
    "ix_incident_notes_alert_id",
    "ix_incident_notes_user_id",
    "ix_recordings_camera_id",
    "ix_recordings_user_id",
    "ix_users_email",
])


def is_production_environment() -> bool:
    """
    Determines whether the application is running in production mode.
    - Inside a container (sys.platform != 'win32' or /.dockerenv exists):
      Defaults to production unless DEEPVISION_ENV=development and DJANGO_DEBUG=True.
    - Outside container (e.g. Windows native):
      Production if DEEPVISION_ENV=production or DJANGO_DEBUG is explicitly False/0.
      Defaults to development for Windows desktop workflows.
    """
    in_container = sys.platform != "win32" or Path("/.dockerenv").exists()
    explicit_prod = os.getenv("DEEPVISION_ENV", "").lower() == "production"
    debug_str = os.getenv("DJANGO_DEBUG", "")

    if in_container:
        return (os.getenv("DEEPVISION_ENV", "").lower() != "development") and (debug_str.lower() not in ("true", "1"))
    return explicit_prod or (debug_str.lower() in ("false", "0"))


def validate_sqlite_indexes(db_path: Path) -> tuple[bool, str, list[str]]:
    """
    Validates the presence of secondary performance and uniqueness indexes.

    Coverage context:
    - Primary table signature ('cc2d13f77b681107') hashes table DDLs (sqlite_master type='table').
      It strictly covers all 18 table structures, column definitions, types, defaults,
      and inline constraints (including autoindexes like sqlite_autoindex_detection_profiles_1).
    - It does NOT cover secondary indexes, views, or triggers.
    - Views in baseline: 0. Triggers in baseline: 0.
    - Secondary indexes: 11 explicit B-tree indexes for query optimization and uniqueness.

    Returns: (is_valid, detail_message, missing_index_names)
    """
    if not db_path.exists():
        return False, f"Database file does not exist at '{db_path}'", list(EXPECTED_SECONDARY_INDEXES)
    if not db_path.is_file():
        return False, f"Database path '{db_path}' is not a regular file", list(EXPECTED_SECONDARY_INDEXES)
    if db_path.stat().st_size == 0:
        return False, f"Database file '{db_path}' is empty (0 bytes)", list(EXPECTED_SECONDARY_INDEXES)

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';")
        present = {row[0] for row in c.fetchall()}
        missing = sorted(EXPECTED_SECONDARY_INDEXES - present)
        if missing:
            return False, f"Database is missing secondary indexes: {missing}", missing
        return True, f"All {len(EXPECTED_SECONDARY_INDEXES)} expected secondary indexes verified", []
    except Exception as e:
        return False, f"Failed to inspect secondary indexes: {e}", list(EXPECTED_SECONDARY_INDEXES)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def validate_sqlite_database(db_path: Path) -> tuple[bool, str]:
    """
    Performs comprehensive preflight validation of the SQLite database:
    1. Confirms file existence and non-zero size.
    2. Runs SQLite 'PRAGMA integrity_check'.
    3. Verifies all 18 expected schema tables exist and count >= 18.
    4. Compares schema SHA-256 signature against baseline 'cc2d13f77b681107'.
    Returns (True, "OK") or (False, error_detail).
    """
    if not db_path.exists():
        return False, f"Database file does not exist at '{db_path}'"
    if not db_path.is_file():
        return False, f"Database path '{db_path}' is not a regular file"
    if db_path.stat().st_size == 0:
        return False, f"Database file '{db_path}' is empty (0 bytes)"

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        c = conn.cursor()

        # Integrity check
        c.execute("PRAGMA integrity_check;")
        row = c.fetchone()
        if not row or row[0] != "ok":
            return False, f"SQLite integrity check failed: {row[0] if row else 'no output'}"

        # Schema table verification
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = {r[0] for r in c.fetchall()}

        if len(tables) < EXPECTED_TABLE_COUNT:
            return False, f"Database has only {len(tables)} tables (expected at least {EXPECTED_TABLE_COUNT})"

        missing = REQUIRED_SCHEMA_TABLES - tables
        if missing:
            return False, f"Database is missing required tables: {sorted(missing)}"

        # Schema signature verification against known baseline
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
        schema_sql = "".join(str(r[0]) for r in c.fetchall())
        sig = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()[:16]
        if sig != EXPECTED_SCHEMA_SIGNATURE:
            return False, f"Schema signature mismatch: got '{sig}', expected '{EXPECTED_SCHEMA_SIGNATURE}'"

        return True, "OK"
    except Exception as e:
        return False, f"SQLite database validation error: {e}"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def create_sqlite_backup(src_path: Path, dst_path: Path) -> tuple[bool, str]:
    """
    Creates a consistent SQLite database backup using SQLite's native backup API.
    Guarantees consistency across both rollback-journal and WAL modes.
    Validates the resulting backup file (integrity, 18 tables, signature, indexes).
    Cleans up any partial or invalid destination file on failure.
    Returns: (is_valid, message)
    """
    if not src_path.exists():
        return False, f"Source database '{src_path}' does not exist"
    if not src_path.is_file():
        return False, f"Source path '{src_path}' is not a regular file"
    if src_path.stat().st_size == 0:
        return False, f"Source database '{src_path}' is empty (0 bytes)"

    conn_src = None
    conn_dst = None
    success = False
    try:
        # Open source in read-only mode to prevent write locks or accidental mutation
        conn_src = sqlite3.connect(f"file:{src_path.resolve()}?mode=ro", uri=True)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if dst_path.exists():
            dst_path.unlink()
        conn_dst = sqlite3.connect(str(dst_path.resolve()))
        conn_src.backup(conn_dst)
        conn_dst.close()
        conn_src.close()
        conn_dst = None
        conn_src = None

        # Validate the newly created backup file
        ok, msg = validate_sqlite_database(dst_path)
        if not ok:
            return False, f"Backup created but failed validation: {msg}"

        ok_idx, msg_idx, _ = validate_sqlite_indexes(dst_path)
        if not ok_idx:
            return False, f"Backup created but failed secondary index validation: {msg_idx}"

        success = True
        return True, "Backup created and verified successfully (integrity ok, 18 tables, signature cc2d13f77b681107, 11 indexes)"
    except Exception as e:
        return False, f"Failed to create SQLite backup: {e}"
    finally:
        if conn_dst is not None:
            try:
                conn_dst.close()
            except Exception:
                pass
        if conn_src is not None:
            try:
                conn_src.close()
            except Exception:
                pass
        if not success and dst_path.exists():
            try:
                dst_path.unlink()
            except Exception:
                pass


def ensure_database():
    """
    Validates the SQLite database before startup.
    In production mode (DJANGO_DEBUG=False or DEEPVISION_ENV=production):
    - Fails closed if the database does not exist, is corrupted, or has an invalid schema.
    - NEVER initializes or overwrites an existing/missing database.
    In development mode:
    - Verifies existing DB integrity before using.
    - Only initializes schema if the database does not exist or has 0 bytes.
    - Never overwrites a corrupted database.
    """
    use_mysql = os.getenv('USE_MYSQL', '').lower() in ('true', '1') or os.getenv('DB_ENGINE', '') == 'django.db.backends.mysql'
    if use_mysql:
        logger.info("Using MySQL backend for DeepVision (configured via environment variables).")
        return

    db_dir = ROOT_DIR / "instance"
    db_path = db_dir / "deepvision.db"

    is_production = is_production_environment()

    if is_production:
        # Production mode: Strict fail-closed database validation
        logger.info("Production mode detected: Running preflight database validation on %s...", db_path)
        valid, detail = validate_sqlite_database(db_path)
        if not valid:
            logger.critical("FATAL: Database preflight validation FAILED in production mode: %s", detail)
            logger.critical("DeepVision production launcher refuses to silently create or overwrite databases to prevent data loss.")
            logger.critical("Ensure host volume 'instance' containing 'deepvision.db' is correctly mounted.")
            raise RuntimeError(f"Database preflight validation failed: {detail}")

        # Secondary index check (separate from table signature)
        valid_idx, idx_msg, missing_idx = validate_sqlite_indexes(db_path)
        if not valid_idx:
            logger.warning("Database secondary index warning: %s. Table signature is verified, but secondary indexes are missing.", idx_msg)
        else:
            logger.info("Database secondary index validation PASSED: %s.", idx_msg)

        logger.info("Database preflight validation PASSED: %s (18 tables, integrity ok, signature %s).", db_path, EXPECTED_SCHEMA_SIGNATURE)
        return

    # Development mode: allow clean init only when database is completely absent
    db_dir.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and db_path.stat().st_size > 0:
        valid, detail = validate_sqlite_database(db_path)
        if not valid:
            logger.critical("Database at %s failed validation: %s", db_path, detail)
            raise RuntimeError(f"Database validation failed: {detail}. Halting to prevent data loss.")
        logger.info("Existing database at %s verified successfully.", db_path)
        return

    # Database is absent in development mode: initialize schema
    logger.info("Development mode: Initializing clean DeepVision database schema at %s...", db_path)
    schema_file = DJANGO_DIR / "schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found at {schema_file}")

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    logger.info("Clean development database schema successfully initialized (18 tables).")



def get_server_launch_command(host: str, port: int):
    """
    Selects the single-process, thread-safe server runner.
    Architecture requires strictly 1 worker process because YOLO11n weights and
    camera capture handles are in-process singletons.
    - Production / Linux / Container: Gunicorn WSGI (1 worker, 8 threads)
      Fails closed (raises RuntimeError) if Gunicorn cannot be imported in production.
      NEVER falls back to Django runserver --insecure in production.
    - Windows / Development: Django Single-Process Server (--noreload --insecure)
    """
    bind_addr = f"{host}:{port}"
    is_prod = is_production_environment()
    is_linux_or_container = sys.platform != "win32" or Path("/.dockerenv").exists()

    if is_prod or is_linux_or_container:
        # Production / Container / Linux mode: Gunicorn WSGI is strictly required
        try:
            import gunicorn  # noqa: F401
            threads = os.getenv("DEEPVISION_WSGI_THREADS", "8")
            timeout = os.getenv("DEEPVISION_WSGI_TIMEOUT", "120")
            cmd = [
                PYTHON_EXE, "-m", "gunicorn",
                "config.wsgi:application",
                "--bind", bind_addr,
                "--workers", "1",
                "--threads", str(threads),
                "--timeout", str(timeout),
                "--access-logfile", "-",
                "--error-logfile", "-",
            ]
            return cmd, f"Gunicorn WSGI (1 worker, {threads} threads)"
        except ImportError as e:
            logger.critical("FATAL: Gunicorn WSGI server is required in production/Linux/container mode, but could not be imported: %s", e)
            logger.critical("Refusing to fall back to Django runserver in production mode to prevent insecure operation.")
            raise RuntimeError(f"Gunicorn WSGI server is required in production/container mode: {e}")

    # Windows native development mode only (when not in production)
    cmd = [
        PYTHON_EXE, str(DJANGO_DIR / "manage.py"), "runserver",
        bind_addr, "--noreload", "--insecure"
    ]
    return cmd, "Django Single-Process Server (--noreload --insecure)"


def main():
    global django_proc

    if "--preflight-check" in sys.argv:
        db_arg = None
        for i, a in enumerate(sys.argv):
            if a == "--preflight-check" and i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("-"):
                db_arg = sys.argv[i + 1]
                break
        target = Path(db_arg) if db_arg else ROOT_DIR / "instance" / "deepvision.db"
        ok, msg = validate_sqlite_database(target)
        if not ok:
            sys.stderr.write(f"PREFLIGHT_FAIL: {msg}\n")
            sys.exit(1)
        ok_idx, idx_msg, missing_idx = validate_sqlite_indexes(target)
        if not ok_idx:
            sys.stdout.write(f"PREFLIGHT_WARN: {idx_msg}\n")
        sys.stdout.write(f"PREFLIGHT_OK: Database valid ({EXPECTED_SCHEMA_SIGNATURE})\n")
        sys.exit(0)

    if "--create-backup" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        src = Path(args[0]) if len(args) > 0 else ROOT_DIR / "instance" / "deepvision.db"
        dst = Path(args[1]) if len(args) > 1 else ROOT_DIR / "instance" / "deepvision.db.pre-upgrade.bak"
        ok, msg = create_sqlite_backup(src, dst)
        if not ok:
            sys.stderr.write(f"BACKUP_FAIL: {msg}\n")
            sys.exit(1)
        sys.stdout.write(f"BACKUP_OK: {msg}\n")
        sys.exit(0)

    logger.info("=================================================================")
    logger.info("  DEEPVISION AI SMART SURVEILLANCE — PRODUCTION LAUNCHER")
    logger.info("  Architecture: Unified Native Django (:8000) Surveillance System")
    logger.info("=================================================================")

    try:
        # Ensure database schema exists before launching Django
        ensure_database()

        # Start Django Application (configurable via DEEPVISION_HOST and DEEPVISION_PORT)
        host = os.getenv("DEEPVISION_HOST", "127.0.0.1")
        port = int(os.getenv("DEEPVISION_PORT", "8000"))
        bind_addr = f"{host}:{port}"

        if is_port_open(host, port):
            logger.info("Django application is already running on %s.", bind_addr)
        else:
            cmd, runner_desc = get_server_launch_command(host, port)
            logger.info("Starting unified Django surveillance application on %s using %s...", bind_addr, runner_desc)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            # Ensure PYTHONPATH includes both DJANGO_DIR and ROOT_DIR for module resolution
            current_pythonpath = env.get("PYTHONPATH", "")
            extra_paths = f"{DJANGO_DIR}{os.pathsep}{ROOT_DIR}"
            env["PYTHONPATH"] = f"{extra_paths}{os.pathsep}{current_pythonpath}" if current_pythonpath else extra_paths

            django_proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                env=env,
            )
            logger.info("Django server launched (PID %s).", django_proc.pid)
    except Exception as e:
        logger.critical("FATAL: DeepVision startup halted: %s", e)
        sys.exit(1)

    logger.info("DeepVision native Django architecture is active.")
    logger.info("Access the application at: http://%s/", bind_addr)
    logger.info("Press Ctrl+C to stop services.")

    # Monitor process
    try:
        while not shutdown_requested:
            if django_proc and django_proc.poll() is not None:
                logger.error("Django process exited with code %s.", django_proc.returncode)
                break
            time.sleep(2.0)
    except KeyboardInterrupt:
        pass
    finally:
        terminate_processes()


if __name__ == "__main__":
    main()
