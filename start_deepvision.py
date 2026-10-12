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


def ensure_database():
    """
    Ensures the SQLite database exists and has the required schema if in SQLite mode.
    If MySQL is configured, defers schema to MySQL backend.
    """
    use_mysql = os.getenv('USE_MYSQL', '').lower() in ('true', '1') or os.getenv('DB_ENGINE', '') == 'django.db.backends.mysql'
    if use_mysql:
        logger.info("Using MySQL backend for DeepVision (configured via environment variables).")
        return

    db_dir = ROOT_DIR / "instance"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "deepvision.db"

    import sqlite3
    need_init = True
    if db_path.exists() and db_path.stat().st_size > 0:
        try:
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
            count = c.fetchone()[0]
            conn.close()
            if count >= 18:
                need_init = False
        except Exception:
            pass

    if need_init:
        logger.info("Initializing clean DeepVision database schema at %s...", db_path)
        schema_file = DJANGO_DIR / "schema.sql"
        if schema_file.exists():
            with open(schema_file, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            conn = sqlite3.connect(str(db_path))
            conn.executescript(schema_sql)
            conn.commit()
            conn.close()
            logger.info("Clean database schema successfully initialized (18 tables).")


def main():
    global django_proc

    logger.info("=================================================================")
    logger.info("  DEEPVISION AI SMART SURVEILLANCE — PRODUCTION LAUNCHER")
    logger.info("  Architecture: Unified Native Django (:8000) Surveillance System")
    logger.info("=================================================================")

    # Ensure database schema exists before launching Django
    ensure_database()

    # Start Django Application (configurable via DEEPVISION_HOST and DEEPVISION_PORT)
    host = os.getenv("DEEPVISION_HOST", "127.0.0.1")
    port = int(os.getenv("DEEPVISION_PORT", "8000"))
    bind_addr = f"{host}:{port}"

    if is_port_open(host, port):
        logger.info("Django application is already running on %s.", bind_addr)
    else:
        logger.info("Starting unified Django surveillance application on %s...", bind_addr)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        django_proc = subprocess.Popen(
            [PYTHON_EXE, str(DJANGO_DIR / "manage.py"), "runserver", bind_addr, "--noreload", "--insecure"],
            cwd=str(ROOT_DIR),
            env=env,
        )
        logger.info("Django server launched (PID %s).", django_proc.pid)

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
