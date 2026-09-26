"""
Native Django Surveillance Recording Service.
Manages camera recording sessions, MP4 file writing, database records,
and storage statistics using Django ORM.
"""

import os
import threading
import logging
import cv2
from datetime import datetime, timezone

from django.conf import settings
from django.utils import timezone as django_timezone
from django.db import connection

from apps.recordings.models import Recording
from apps.surveillance.ai.workers import create_browser_compatible_video_writer

logger = logging.getLogger(__name__)

_active_recordings = {}
_lock = threading.Lock()


def _get_recordings_dir():
    """Returns the base recordings directory path: instance/recordings."""
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "instance", "recordings"))
    os.makedirs(base, exist_ok=True)
    return base


def _get_evidence_dir():
    """Returns the base evidence directory path: instance/evidence."""
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "instance", "evidence"))
    os.makedirs(base, exist_ok=True)
    return base


def validate_recording_path(file_path):
    """Validates that a file path is safely within recordings or evidence directory."""
    if not file_path:
        return False
    base_rec = _get_recordings_dir()
    full_rec = os.path.normpath(os.path.join(base_rec, file_path))
    if full_rec.startswith(base_rec + os.sep) or full_rec == base_rec:
        return True

    base_ev = _get_evidence_dir()
    clean_path = file_path.replace("evidence" + os.sep, "").replace("evidence/", "")
    full_ev = os.path.normpath(os.path.join(base_ev, clean_path))
    return full_ev.startswith(base_ev + os.sep) or full_ev == base_ev


def start_recording(user_id, camera_id):
    """
    Creates a new Recording record with status='recording' using Django ORM.
    Generates safe filename and sets up active recording registry.
    """
    now = django_timezone.now()
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'cam_{camera_id}_rec_{timestamp_str}.mp4'

    rec_dir = _get_recordings_dir()
    cam_dir = os.path.join(rec_dir, f'camera_{camera_id}')
    os.makedirs(cam_dir, exist_ok=True)

    relative_path = os.path.join(f'camera_{camera_id}', filename).replace('\\', '/')
    full_path = os.path.normpath(os.path.join(rec_dir, relative_path))

    recording = Recording.objects.create(
        user_id=user_id,
        camera_id=camera_id,
        filename=filename,
        file_path=relative_path,
        started_at=now,
        status='recording',
        duration_seconds=0.0,
        file_size=0,
    )

    with _lock:
        _active_recordings[camera_id] = {
            'recording_id': recording.id,
            'user_id': user_id,
            'full_path': full_path,
            'writer': None,
            'start_time': now,
        }

    logger.info(f"[RECORDING_STARTED] id={recording.id} cam={camera_id} path={relative_path}")
    return recording


def stop_recording(recording_id, user_id):
    """
    Marks a recording as completed, finalizes VideoWriter, updates duration and size.
    """
    rec = Recording.objects.filter(id=recording_id, user_id=user_id, status='recording').first()
    if not rec:
        return None

    with _lock:
        rec_data = _active_recordings.pop(rec.camera_id, None)
        if rec_data:
            writer = rec_data.get('writer')
            if writer:
                try:
                    writer.release()
                except Exception as e:
                    logger.warning(f"[RECORDING_WRITER_RELEASE_WARN] {e}")

    now = django_timezone.now()
    rec.ended_at = now
    rec.status = 'completed'

    if rec.started_at:
        rec.duration_seconds = max(0.0, (now - rec.started_at).total_seconds())

    base = _get_recordings_dir()
    full_path = os.path.normpath(os.path.join(base, rec.file_path))
    if os.path.exists(full_path):
        rec.file_size = os.path.getsize(full_path)

    rec.save(update_fields=['ended_at', 'status', 'duration_seconds', 'file_size'])
    logger.info(f"[RECORDING_STOPPED] id={rec.id} cam={rec.camera_id} size={rec.file_size} dur={rec.duration_seconds}s")
    return rec


def stop_camera_recording_by_camera(camera_id, user_id):
    """Stops the active recording for a camera if one exists."""
    active = get_active_recording(camera_id, user_id)
    if not active:
        return None
    return stop_recording(active.id, user_id)


def get_active_recording(camera_id, user_id):
    """Returns the active (status='recording') Recording for a camera, if any."""
    return Recording.objects.filter(camera_id=camera_id, user_id=user_id, status='recording').first()


def write_frame(camera_id, frame):
    """
    Writes a frame to the active recording VideoWriter for the camera.
    Initializes VideoWriter lazily on first frame.
    """
    if frame is None or not hasattr(frame, 'shape') or frame.size == 0:
        return

    h, w = frame.shape[:2]
    with _lock:
        rec_data = _active_recordings.get(camera_id)
        if not rec_data:
            return

        writer = rec_data.get('writer')
        if writer is None:
            writer = create_browser_compatible_video_writer(rec_data['full_path'], 20.0, w, h)
            rec_data['writer'] = writer

        if writer and writer.isOpened():
            try:
                writer.write(frame)
            except Exception as e:
                logger.error(f"[RECORDING_WRITE_FRAME_ERROR] cam={camera_id}: {e}")
