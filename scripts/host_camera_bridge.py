"""
DeepVision Native Windows Host Camera Bridge
============================================
Allows the containerized DeepVision Django + React application (running in Docker/WSL2)
to access the physical Windows DirectShow webcam (dshow://0) in real-time with
the canonical YOLO11n + ByteTrack surveillance engine without fake frames or duplicate AI models.

Architecture:
  Windows Host (:8554)
    ├── OpenCV VideoCapture(0, CAP_DSHOW) [DirectShow physical camera]
    ├── YOLO11n singleton (MODEL_LOAD_COUNT=1)
    ├── ByteTrack tracking & Kalman filtering
    └── MJPEG Streaming Server (ThreadingHTTPServer)
          ▲
          │ HTTP (:8554) via host.docker.internal
          ▼
  Docker Container (:8000)
    ├── Django Web Framework & REST APIs
    ├── React 19 SOC Operations UI
    └── Forensic Database & Alerts

Usage:
  python scripts/host_camera_bridge.py [--port 8554] [--host 0.0.0.0]
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Set up paths and Django environment
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "deepvision_django"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Avoid recursively calling the bridge from within the host bridge
os.environ["USE_HOST_CAMERA_BRIDGE"] = "False"

import django
django.setup()

from apps.ai.engine import (
    stream_camera_frames,
    get_camera_snapshot,
    get_camera_stats,
    start_camera_recording,
    stop_camera_recording,
    test_existing_camera,
    get_engine_status,
    normalize_mode,
)
from apps.cameras.models import Camera
from apps.surveillance.camera.registry import get_camera_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HOST-CAMERA-BRIDGE] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("HostCameraBridge")


class HostCameraBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Suppress verbose frame chunk logging; only log errors/connects
        if "stream" not in self.path:
            logger.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # Healthcheck endpoint
        if path in ("", "/health", "/api/health"):
            status_data = {
                "status": "online",
                "bridge": "DeepVision Native DirectShow Host Camera Bridge",
                "backend": "DirectShow (dshow://0)",
                "platform": sys.platform,
                "engine": get_engine_status()
            }
            self._send_json(status_data)
            return

        # Camera streaming endpoint: /cameras/<id>/stream
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "cameras" and parts[2] == "stream":
            try:
                camera_id = int(parts[1])
            except ValueError:
                self.send_error(400, "Invalid camera ID")
                return

            mode_param = query.get("mode", ["tracking"])[0]
            canonical_mode = normalize_mode(mode_param)

            # Resolve camera user_id for surveillance registry
            cam = Camera.objects.filter(id=camera_id).first()
            user_id = cam.user_id if cam else 1

            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            logger.info("Starting live MJPEG stream for Camera #%d (mode=%s) to %s", camera_id, canonical_mode, self.client_address[0])
            try:
                for chunk in stream_camera_frames(camera_id, user_id, canonical_mode):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                logger.info("Client disconnected from stream (Camera #%d)", camera_id)
            except Exception as e:
                logger.error("Error streaming Camera #%d: %s", camera_id, e)
            return

        # Snapshot endpoint: /cameras/<id>/snapshot
        if len(parts) >= 3 and parts[0] == "cameras" and parts[2] == "snapshot":
            try:
                camera_id = int(parts[1])
            except ValueError:
                self.send_error(400, "Invalid camera ID")
                return

            cam = Camera.objects.filter(id=camera_id).first()
            user_id = cam.user_id if cam else 1
            jpeg_bytes = get_camera_snapshot(camera_id, user_id)
            if jpeg_bytes:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(jpeg_bytes)
            else:
                self.send_error(404, "Snapshot not available")
            return

        # Stats endpoint: /cameras/<id>/stats
        if len(parts) >= 3 and parts[0] == "cameras" and parts[2] == "stats":
            try:
                camera_id = int(parts[1])
            except ValueError:
                self.send_error(400, "Invalid camera ID")
                return

            cam = Camera.objects.filter(id=camera_id).first()
            user_id = cam.user_id if cam else 1
            stats = get_camera_stats(camera_id, user_id)
            self._send_json(stats)
            return

        # Test camera connection: /cameras/<id>/test
        if len(parts) >= 3 and parts[0] == "cameras" and parts[2] == "test":
            try:
                camera_id = int(parts[1])
            except ValueError:
                self.send_error(400, "Invalid camera ID")
                return

            cam = Camera.objects.filter(id=camera_id).first()
            user_id = cam.user_id if cam else 1
            result = test_existing_camera(camera_id, user_id)
            self._send_json(result)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        parts = [p for p in path.split("/") if p]

        # Recording controls: /cameras/<id>/record/start and /cameras/<id>/record/stop
        if len(parts) >= 4 and parts[0] == "cameras" and parts[2] == "record":
            try:
                camera_id = int(parts[1])
            except ValueError:
                self.send_error(400, "Invalid camera ID")
                return

            action = parts[3]
            cam = Camera.objects.filter(id=camera_id).first()
            user_id = cam.user_id if cam else 1

            if action == "start":
                res = start_camera_recording(camera_id, user_id)
            elif action == "stop":
                res = stop_camera_recording(camera_id, user_id)
            else:
                self.send_error(400, f"Unknown recording action: {action}")
                return

            self._send_json(res)
            return

        self.send_error(404, "Endpoint not found")


def main():
    parser = argparse.ArgumentParser(description="DeepVision Native Windows Host Camera Bridge")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8554, help="Listening port (default: 8554)")
    args = parser.parse_args()

    server_address = (args.host, args.port)
    httpd = ThreadingHTTPServer(server_address, HostCameraBridgeHandler)
    logger.info("=" * 65)
    logger.info("  DEEPVISION NATIVE WINDOWS HOST CAMERA BRIDGE")
    logger.info("  DirectShow Hardware: dshow://0 -> http://%s:%d", args.host, args.port)
    logger.info("  Provides physical camera & YOLO11n telemetry to Docker container")
    logger.info("=" * 65)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping host camera bridge...")
    finally:
        httpd.server_close()
        logger.info("Host camera bridge stopped.")


if __name__ == "__main__":
    main()
