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


def main():
    global django_proc

    logger.info("=================================================================")
    logger.info("  DEEPVISION AI SMART SURVEILLANCE — PRODUCTION LAUNCHER")
    logger.info("  Architecture: Unified Native Django (:8000) Surveillance System")
    logger.info("=================================================================")

    # Start Django Application on port 8000 (if not already running)
    if is_port_open("127.0.0.1", 8000):
        logger.info("Django application is already running on port 8000.")
    else:
        logger.info("Starting unified Django surveillance application on port 8000...")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        django_proc = subprocess.Popen(
            [PYTHON_EXE, str(DJANGO_DIR / "manage.py"), "runserver", "127.0.0.1:8000", "--noreload"],
            cwd=str(ROOT_DIR),
            env=env,
        )
        logger.info("Django server launched (PID %s).", django_proc.pid)

    logger.info("DeepVision native Django architecture is active.")
    logger.info("Access the application at: http://127.0.0.1:8000/")
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
