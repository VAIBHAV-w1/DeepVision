"""
Native Django Surveillance Recording Service.
Manages camera recording sessions, asynchronous non-blocking MP4 file writing,
database records, and storage statistics using Django ORM.
"""

import os
import time
import queue
import shutil
import threading
import logging
from datetime import datetime, timezone
try:
    import cv2
except (ImportError, Exception):
    cv2 = None

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


def check_storage_capacity(min_free_mb=None):
    """
    Checks available disk space on the recordings partition.
    Returns (ok: bool, free_mb: float, required_mb: float).
    """
    required_mb = float(
        min_free_mb
        if min_free_mb is not None
        else getattr(settings, "SURVEILLANCE_MIN_FREE_DISK_MB", 500.0)
    )
    rec_dir = _get_recordings_dir()
    usage = shutil.disk_usage(rec_dir)
    free_mb = round(usage.free / (1024.0 * 1024.0), 2)
    return (free_mb >= required_mb, free_mb, required_mb)


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


class AsyncRecordingWriter(threading.Thread):
    """
    Dedicated non-blocking background thread that writes frames to disk.
    Prevents video encoding and disk I/O from stalling the camera capture loop.
    """
    def __init__(self, camera_id, full_path, fps=25.0, max_queue=90, max_file_mb=None):
        super().__init__(name=f"RecWriter-Cam{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.full_path = full_path
        self.fps = fps
        self.max_file_bytes = int(
            float(max_file_mb if max_file_mb is not None else getattr(settings, "SURVEILLANCE_MAX_SINGLE_RECORDING_MB", 2048.0))
            * 1024 * 1024
        )
        self.frame_queue = queue.Queue(maxsize=max_queue)
        self.running = True
        self.writer = None
        self.frames_written = 0
        self.stopped_by_storage_guard = False

    def run(self):
        while self.running or not self.frame_queue.empty():
            try:
                item = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is None:
                # Sentinel to finalize
                break

            frame = item
            if frame is None or getattr(frame, "size", 0) == 0:
                self.frame_queue.task_done()
                continue

            # Periodic storage & single-file size guard (every 150 frames) to prevent unbounded multi-GB disk exhaustion
            if self.frames_written > 0 and (self.frames_written % 150 == 0):
                try:
                    ok_disk, free_mb, req_mb = check_storage_capacity()
                    curr_bytes = os.path.getsize(self.full_path) if os.path.exists(self.full_path) else 0
                    if (not ok_disk) or (self.max_file_bytes > 0 and curr_bytes >= self.max_file_bytes):
                        logger.warning(
                            f"[REC_STORAGE_GUARD] Stopping recording cam={self.camera_id} "
                            f"(free_mb={free_mb}, req_mb={req_mb}, file_bytes={curr_bytes})"
                        )
                        self.stopped_by_storage_guard = True
                        self.running = False
                        self.frame_queue.task_done()
                        break
                except Exception:
                    pass

            h, w = frame.shape[:2]
            if self.writer is None and cv2 is not None:
                try:
                    self.writer = create_browser_compatible_video_writer(self.full_path, self.fps, w, h)
                except Exception as e:
                    logger.error(f"[REC_WRITER_INIT_ERROR] cam={self.camera_id}: {e}")

            if self.writer and self.writer.isOpened():
                try:
                    self.writer.write(frame)
                    self.frames_written += 1
                except Exception as e:
                    logger.error(f"[REC_WRITE_ERROR] cam={self.camera_id}: {e}")

            self.frame_queue.task_done()

        if self.writer:
            try:
                self.writer.release()
            except Exception as e:
                logger.warning(f"[REC_WRITER_RELEASE_ERROR] cam={self.camera_id}: {e}")
            self.writer = None

    def push_frame(self, frame):
        if not self.running:
            return
        try:
            # Non-blocking enqueue: drop frame if disk writer is falling behind to protect capture
            self.frame_queue.put_nowait(frame.copy())
        except queue.Full:
            pass

    def stop_and_join(self, timeout=3.0):
        self.running = False
        try:
            self.frame_queue.put_nowait(None)
        except Exception:
            pass
        self.join(timeout=timeout)


def start_recording(user_id, camera_id, fps=15.0, min_free_mb=None):
    """
    Creates a new Recording record with status='recording' using Django ORM.
    Enforces minimum free disk storage threshold and spawns an asynchronous background writer.
    """
    ok_disk, free_mb, req_mb = check_storage_capacity(min_free_mb=min_free_mb)
    if not ok_disk:
        raise OSError(f"Insufficient disk space for recording ({free_mb:.1f} MB free, {req_mb:.1f} MB required).")

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

    safe_fps = max(10.0, min(30.0, float(fps or 15.0)))
    writer_thread = AsyncRecordingWriter(camera_id, full_path, fps=safe_fps)
    writer_thread.start()

    with _lock:
        # If an existing recording was somehow still active for this camera, close it
        old_data = _active_recordings.pop(camera_id, None)
        if old_data and old_data.get('writer_thread'):
            try:
                old_data['writer_thread'].stop_and_join(timeout=1.0)
            except Exception:
                pass

        _active_recordings[camera_id] = {
            'recording_id': recording.id,
            'user_id': user_id,
            'full_path': full_path,
            'writer_thread': writer_thread,
            'start_time': now,
        }

    logger.info(f"[RECORDING_STARTED] id={recording.id} cam={camera_id} user={user_id} path={relative_path}")
    return recording


def stop_recording(recording_id, user_id=None):
    """
    Marks a recording as completed, finalizes async writer, updates duration and size.
    """
    query = Recording.objects.filter(id=recording_id, status='recording')
    if user_id is not None:
        query = query.filter(user_id=user_id)
    rec = query.first()
    if not rec:
        return None

    with _lock:
        rec_data = _active_recordings.get(rec.camera_id)
        # A camera can have a newer in-memory session than this DB row (for
        # example after a restart or overlapping start request). Only the
        # owner of that exact session may remove and stop its writer.
        if rec_data and rec_data.get('recording_id') == rec.id:
            _active_recordings.pop(rec.camera_id, None)
            writer_thread = rec_data.get('writer_thread')
            if writer_thread:
                try:
                    writer_thread.stop_and_join(timeout=3.0)
                except Exception as e:
                    logger.warning(f"[RECORDING_WRITER_RELEASE_WARN] {e}")

    now = django_timezone.now()
    rec.ended_at = now
    rec.status = 'completed'

    if rec.started_at:
        rec.duration_seconds = round(max(0.0, (now - rec.started_at).total_seconds()), 1)

    base = _get_recordings_dir()
    full_path = os.path.normpath(os.path.join(base, rec.file_path))
    if os.path.exists(full_path):
        rec.file_size = os.path.getsize(full_path)

    rec.save(update_fields=['ended_at', 'status', 'duration_seconds', 'file_size'])
    logger.info(f"[RECORDING_STOPPED] id={rec.id} cam={rec.camera_id} size={rec.file_size} dur={rec.duration_seconds}s")
    return rec


def stop_camera_recording_by_camera(camera_id, user_id=None):
    """Stops the active recording for a camera if one exists."""
    active = get_active_recording(camera_id, user_id)
    if not active:
        # Fallback check directly in database
        active_qs = Recording.objects.filter(camera_id=camera_id, status='recording')
        if user_id is not None:
            active_qs = active_qs.filter(user_id=user_id)
        active = active_qs.first()
    if not active:
        return None
    return stop_recording(active.id, user_id)


def get_active_recording(camera_id, user_id=None):
    """Returns the active (status='recording') Recording for a camera, if any."""
    qs = Recording.objects.filter(camera_id=camera_id, status='recording')
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    return qs.first()


def write_frame(camera_id, frame):
    """
    Pushes a frame to the active non-blocking async recording writer.
    Returns immediately, guaranteeing zero capture stalls.
    """
    if frame is None or not hasattr(frame, 'shape') or frame.size == 0:
        return

    with _lock:
        rec_data = _active_recordings.get(camera_id)
        if not rec_data:
            return
        writer_thread = rec_data.get('writer_thread')

    if writer_thread:
        writer_thread.push_frame(frame)
