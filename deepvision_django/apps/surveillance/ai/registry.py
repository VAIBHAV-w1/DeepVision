"""
Native Django Surveillance Inference Registry.
Manages InferenceWorker instances with physical hardware deduping and 30s grace period.
Guarantees ONE InferenceWorker and ONE YOLO11n model per physical camera.
"""

import threading
import logging
from django.conf import settings

from apps.surveillance.ai.tracker import ByteTrackTracker
from apps.surveillance.ai.workers import InferenceWorker

logger = logging.getLogger(__name__)


class InferenceRegistry:
    """
    Thread-safe registry managing InferenceWorker instances.
    Enforces ONE InferenceWorker per physical camera source.
    Uses copy.copy() of shared YOLO weights (zero disk I/O, isolated ByteTrack state).
    """

    def __init__(self):
        self.workers = {}                    # camera_id -> InferenceWorker
        self.physical_workers = {}           # physical_source_id -> InferenceWorker
        self.camera_to_physical = {}         # camera_id -> physical_source_id
        self.cleanup_timers = {}             # physical_source_id -> Timer
        self.lock = threading.Lock()

    def get_worker(self, camera_id, camera_worker):
        phys_id = getattr(camera_worker, "physical_source_id", str(camera_id))
        iworker_to_start = None

        with self.lock:
            if phys_id in self.cleanup_timers:
                self.cleanup_timers[phys_id].cancel()
                del self.cleanup_timers[phys_id]

            # Check if physical source already has an active InferenceWorker
            p_iworker = self.physical_workers.get(phys_id)
            if p_iworker is not None:
                if not p_iworker.running or (p_iworker.thread is not None and not p_iworker.thread.is_alive()):
                    print(f"[INFERENCE_REGISTRY] Removing dead InferenceWorker for {phys_id}")
                    self.physical_workers.pop(phys_id, None)
                    p_iworker = None
                else:
                    p_iworker.ref_count += 1
                    self.workers[camera_id] = p_iworker
                    self.camera_to_physical[camera_id] = phys_id
                    print(f"[INFERENCE_REGISTRY] Logical camera {camera_id} joined active InferenceWorker {phys_id} (ref_count={p_iworker.ref_count})")
                    return p_iworker

            if p_iworker is None:
                threshold = getattr(settings, "YOLO_CONFIDENCE_THRESHOLD", 0.50)
                interval_ms = getattr(settings, "YOLO_INFERENCE_INTERVAL_MS", 150)

                tracker = ByteTrackTracker(confidence_threshold=threshold)
                iworker = InferenceWorker(camera_id, tracker, inference_interval_ms=interval_ms)
                iworker.ref_count = 1
                self.physical_workers[phys_id] = iworker
                self.workers[camera_id] = iworker
                self.camera_to_physical[camera_id] = phys_id
                iworker_to_start = iworker

        if iworker_to_start is not None:
            try:
                iworker_to_start.start(camera_worker)
            except Exception as e:
                with self.lock:
                    self.physical_workers.pop(phys_id, None)
                    self.workers.pop(camera_id, None)
                    self.camera_to_physical.pop(camera_id, None)
                raise e

        return self.workers[camera_id]

    def release_worker(self, camera_id):
        with self.lock:
            phys_id = self.camera_to_physical.get(camera_id)
            if not phys_id:
                return
            p_iworker = self.physical_workers.get(phys_id)
            if not p_iworker:
                self.workers.pop(camera_id, None)
                self.camera_to_physical.pop(camera_id, None)
                return

            p_iworker.ref_count = max(0, p_iworker.ref_count - 1)
            print(f"[DEBUG] release_inference_worker camera={camera_id} phys_id={phys_id} ref_count={p_iworker.ref_count}")

            if p_iworker.ref_count > 0:
                return

            # Grace period before stopping inference worker
            if phys_id in self.cleanup_timers:
                self.cleanup_timers[phys_id].cancel()
            try:
                timer = threading.Timer(30.0, self._cleanup_inference_worker, args=[phys_id])
                timer.daemon = True
                self.cleanup_timers[phys_id] = timer
                timer.start()
            except Exception:
                self.physical_workers.pop(phys_id, None)
                p_iworker.stop()

    def _cleanup_inference_worker(self, phys_id):
        worker_to_stop = None
        with self.lock:
            if phys_id in self.cleanup_timers:
                del self.cleanup_timers[phys_id]
            p_iworker = self.physical_workers.get(phys_id)
            if p_iworker is not None and p_iworker.ref_count <= 0:
                worker_to_stop = p_iworker
                self.physical_workers.pop(phys_id, None)
                for cid, pid in list(self.camera_to_physical.items()):
                    if pid == phys_id:
                        self.camera_to_physical.pop(cid, None)
                        self.workers.pop(cid, None)

        if worker_to_stop:
            try:
                worker_to_stop.stop()
            except Exception as e:
                logger.warning(f"[REGISTRY_WARN] Error stopping inference worker for {phys_id}: {e}")
            print(f"[DEBUG] Stopped inference worker for {phys_id} after grace period.")

    def get_active_worker(self, camera_id):
        with self.lock:
            return self.workers.get(camera_id)


_inference_registry = InferenceRegistry()

def get_inference_registry():
    return _inference_registry
