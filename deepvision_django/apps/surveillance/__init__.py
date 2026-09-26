"""
Native Django Surveillance Subsystem.
Provides singleton hardware camera management, YOLO11n + ByteTrack inference,
recording, evidence collection, and health telemetry.
"""

from apps.surveillance.camera.registry import get_camera_registry
from apps.surveillance.ai.registry import get_inference_registry
from apps.surveillance.recording import recording_service
from apps.surveillance.health.health_service import update_camera_health, get_camera_health, get_user_cameras_health
from apps.surveillance.streaming.stream_service import generate_raw_stream, generate_tracking_stream, get_camera_telemetry

__all__ = [
    "get_camera_registry",
    "get_inference_registry",
    "recording_service",
    "update_camera_health",
    "get_camera_health",
    "get_user_cameras_health",
    "generate_raw_stream",
    "generate_tracking_stream",
    "get_camera_telemetry",
]
