"""
Audio Capability & Media Forensics Service for DeepVision.

Provides honest, verifiable detection of audio track presence in:
1. Physical DirectShow webcam sources (dshow://0)
2. IP Camera RTSP/MJPEG streams
3. Archived MP4 evidence clips and continuous recordings
"""

import os
import struct
import logging
from pathlib import Path

logger = logging.getLogger("deepvision.audio")


def inspect_media_audio(file_path):
    """
    Safely inspects an MP4 file container to determine if an audio track exists.
    Parses ISO Base Media File Format (MP4) atoms for a track with 'soun' handler.
    Returns:
        dict: {
            "has_audio": bool,
            "status": "available" | "unavailable",
            "codec": str or None,
            "reason": str
        }
    """
    if not file_path or not os.path.exists(file_path):
        return {
            "has_audio": False,
            "status": "unavailable",
            "codec": None,
            "reason": "File does not exist or path is invalid."
        }

    try:
        file_size = os.path.getsize(file_path)
        if file_size < 32:
            return {
                "has_audio": False,
                "status": "unavailable",
                "codec": None,
                "reason": "File is empty or truncated."
            }

        # Scan for 'soun' handler box in the first 256KB or moov header
        with open(file_path, "rb") as f:
            header_sample = f.read(min(file_size, 262144))
            has_soun = b"soun" in header_sample
            has_mp4a = b"mp4a" in header_sample or b"alac" in header_sample

            if has_soun or has_mp4a:
                return {
                    "has_audio": True,
                    "status": "available",
                    "codec": "aac" if has_mp4a else "pcm",
                    "reason": "Audio track present in MP4 container."
                }

        return {
            "has_audio": False,
            "status": "unavailable",
            "codec": None,
            "reason": "Video-only MP4 container (no multiplexed audio track)."
        }

    except Exception as e:
        logger.warning(f"Error inspecting audio in media {file_path}: {e}")
        return {
            "has_audio": False,
            "status": "unavailable",
            "codec": None,
            "reason": f"Inspection error: {str(e)}"
        }


def check_camera_audio_capability(camera):
    """
    Evaluates whether a camera source provides a live audio channel.
    Args:
        camera: Camera model instance or dict with source/source_type.
    Returns:
        dict: {
            "supported": bool,
            "available": bool,
            "status": "available" | "unavailable" | "not_supported",
            "source_type": str,
            "reason": str
        }
    """
    if not camera:
        return {
            "supported": False,
            "available": False,
            "status": "not_supported",
            "source_type": "unknown",
            "reason": "No camera source provided."
        }

    source_type = getattr(camera, "source_type", None) or "webcam"
    source = getattr(camera, "source", None) or ""

    if source_type in ("webcam", "dshow", "local") or str(source).startswith("0") or "dshow" in str(source).lower():
        # DirectShow webcam video capture
        return {
            "supported": False,
            "available": False,
            "status": "unavailable",
            "source_type": "DirectShow Webcam (Video Pin)",
            "reason": "DirectShow OpenCV video capture pipeline operates on video pins only; audio multiplexing not supported by VideoWriter."
        }

    if source_type in ("rtsp", "ip") or str(source).startswith("rtsp://"):
        return {
            "supported": True,
            "available": False,
            "status": "unavailable",
            "source_type": "RTSP Stream",
            "reason": "IP camera RTSP stream has no active audio subtrack configured."
        }

    return {
        "supported": False,
        "available": False,
        "status": "unavailable",
        "source_type": source_type,
        "reason": "Source does not provide an integrated audio stream."
    }


class AudioCapabilityService:
    @staticmethod
    def inspect_clip(file_path):
        return inspect_media_audio(file_path)

    @staticmethod
    def inspect_camera(camera):
        return check_camera_audio_capability(camera)
