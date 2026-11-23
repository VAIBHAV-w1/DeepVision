"""
Native Django Surveillance Inference Registry.
Manages InferenceWorker instances with physical hardware deduping and 30s grace period.
Guarantees ONE InferenceWorker and ONE YOLO11n model per physical camera.
"""

import os
import json
import threading
import logging
from django.conf import settings

from apps.surveillance.ai.tracker import ByteTrackTracker
from apps.surveillance.ai.workers import InferenceWorker

logger = logging.getLogger(__name__)


def _get_runtime_config_path() -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "instance"))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "detection_runtime.json")


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
        self.phys_locks = {}                 # physical_source_id -> Lock (serializes worker creation)
        self.runtime_confidence_threshold = float(getattr(settings, "YOLO_CONFIDENCE_THRESHOLD", 0.35))
        self.runtime_ai_profile = (os.getenv("DEEPVISION_AI_PROFILE") or "balanced").strip().lower()
        if self.runtime_ai_profile not in ("balanced", "lightweight"):
            self.runtime_ai_profile = "balanced"
        self.runtime_anomaly_rules = {
            "LOITERING_ENABLED": True,
            "RESTRICTED_ENTRY_ENABLED": True,
            "CROWDING_ENABLED": True,
            "UNUSUAL_MOVEMENT_ENABLED": True,
            "RAPID_MOVEMENT_ENABLED": True,
            "ABANDONED_OBJECT_ENABLED": True,
        }
        self.lock = threading.Lock()
        self._load_persisted_settings()

    def _load_persisted_settings(self):
        try:
            cfg_path = _get_runtime_config_path()
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if "confidence_threshold" in data:
                    self.runtime_confidence_threshold = max(0.15, min(0.95, float(data["confidence_threshold"])))
                if isinstance(data.get("ai_profile"), str):
                    prof = data["ai_profile"].strip().lower()
                    if prof in ("balanced", "lightweight"):
                        self.runtime_ai_profile = prof
                        os.environ["DEEPVISION_AI_PROFILE"] = prof
                if isinstance(data.get("rules"), dict):
                    for k, v in data["rules"].items():
                        if k in self.runtime_anomaly_rules:
                            self.runtime_anomaly_rules[k] = bool(v)
        except Exception as e:
            logger.warning(f"[INFERENCE_REGISTRY_LOAD_WARN] {e}")

    def _persist_settings(self):
        try:
            cfg_path = _get_runtime_config_path()
            payload = {
                "confidence_threshold": self.runtime_confidence_threshold,
                "ai_profile": self.runtime_ai_profile,
                "rules": dict(self.runtime_anomaly_rules),
            }
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except Exception as e:
            logger.warning(f"[INFERENCE_REGISTRY_SAVE_WARN] {e}")

    def apply_runtime_settings(self, confidence_threshold=None, rules=None, ai_profile=None):
        """Updates live confidence threshold, explicit AI profile, and anomaly rule flags cleanly."""
        profile_changed = False
        with self.lock:
            if confidence_threshold is not None:
                self.runtime_confidence_threshold = max(0.15, min(0.95, float(confidence_threshold)))
            if isinstance(ai_profile, str):
                norm_prof = ai_profile.strip().lower()
                if norm_prof in ("lightweight", "nano", "low_resource", "cpu_lite", "fast", "fast_cpu"):
                    norm_prof = "lightweight"
                elif norm_prof in ("balanced", "yolo26s", "standard"):
                    norm_prof = "balanced"
                else:
                    norm_prof = None
                if norm_prof and norm_prof != self.runtime_ai_profile:
                    self.runtime_ai_profile = norm_prof
                    os.environ["DEEPVISION_AI_PROFILE"] = norm_prof
                    profile_changed = True
            if isinstance(rules, dict):
                for k, v in rules.items():
                    self.runtime_anomaly_rules[k] = bool(v)
            self._persist_settings()
            active_iworkers = set(self.physical_workers.values())

        if profile_changed:
            try:
                from apps.surveillance.ai.model_loader import reload_shared_yolo_model
                reload_shared_yolo_model(self.runtime_ai_profile)
            except Exception as e:
                logger.warning(f"[INFERENCE_REGISTRY_RELOAD_WARN] {e}")

        for iw in active_iworkers:
            if iw and iw.tracker is not None and profile_changed and hasattr(iw.tracker, "reload_model"):
                try:
                    iw.tracker.reload_model()
                except Exception as e:
                    logger.warning(f"[INFERENCE_WORKER_RELOAD_WARN] {e}")
            if iw and iw.tracker is not None and confidence_threshold is not None:
                iw.tracker.confidence_threshold = self.runtime_confidence_threshold
            if iw and iw.anomaly_detector is not None and isinstance(rules, dict):
                iw.anomaly_detector.config.update(self.runtime_anomaly_rules)
            if iw:
                iw.invalidate_zones()

    def get_runtime_settings(self):
        with self.lock:
            return {
                "confidence_threshold": self.runtime_confidence_threshold,
                "ai_profile": self.runtime_ai_profile,
                "rules": dict(self.runtime_anomaly_rules),
            }

    def get_worker(self, camera_id, camera_worker):
        phys_id = getattr(camera_worker, "physical_source_id", str(camera_id))

        with self.lock:
            phys_lock = self.phys_locks.get(phys_id)
            if phys_lock is None:
                phys_lock = threading.Lock()
                self.phys_locks[phys_id] = phys_lock

        with phys_lock:
            with self.lock:
                if phys_id in self.cleanup_timers:
                    self.cleanup_timers[phys_id].cancel()
                    del self.cleanup_timers[phys_id]

                p_iworker = self.physical_workers.get(phys_id)
                if p_iworker is not None:
                    if not p_iworker.running or (p_iworker.thread is not None and not p_iworker.thread.is_alive()):
                        print(f"[INFERENCE_REGISTRY] Removing dead InferenceWorker for {phys_id}")
                        self.physical_workers.pop(phys_id, None)
                        p_iworker = None
                    else:
                        p_iworker.ref_count += 1
                        p_iworker.bind_camera(camera_id)
                        self.workers[camera_id] = p_iworker
                        self.camera_to_physical[camera_id] = phys_id
                        print(f"[INFERENCE_REGISTRY] Logical camera {camera_id} joined active InferenceWorker {phys_id} (ref_count={p_iworker.ref_count})")
                        return p_iworker

                threshold = self.runtime_confidence_threshold
                interval_ms = getattr(settings, "YOLO_INFERENCE_INTERVAL_MS", 60)
                imgsz = getattr(settings, "YOLO_IMAGE_SIZE", 640)
                rules_snapshot = dict(self.runtime_anomaly_rules)

            # Construct & start strictly ONE InferenceWorker while holding phys_lock.
            # Use lazy_init=True so HTTP stream/ingest endpoints return immediately while
            # YOLO11n weights load inside the background InferenceWorker thread.
            tracker = ByteTrackTracker(confidence_threshold=threshold, imgsz=imgsz, lazy_init=True)
            iworker = InferenceWorker(camera_id, tracker, inference_interval_ms=interval_ms)
            iworker.anomaly_detector.config.update(rules_snapshot)
            iworker.ref_count = 1
            iworker.start(camera_worker)

            with self.lock:
                self.physical_workers[phys_id] = iworker
                self.workers[camera_id] = iworker
                self.camera_to_physical[camera_id] = phys_id

            return iworker

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

    def remove_worker(self, camera_id):
        """Immediately detaches a camera from its InferenceWorker and stops it if no longer referenced."""
        worker_to_stop = None
        with self.lock:
            self.workers.pop(camera_id, None)
            phys_id = self.camera_to_physical.pop(camera_id, None)
            if not phys_id:
                return
            still_bound = [cid for cid, pid in self.camera_to_physical.items() if pid == phys_id]
            p_iworker = self.physical_workers.get(phys_id)
            if p_iworker is not None:
                with p_iworker.lock:
                    p_iworker.bound_camera_ids.discard(camera_id)
                    if still_bound and getattr(p_iworker, "camera_id", None) == camera_id:
                        p_iworker.camera_id = still_bound[0]
                p_iworker.ref_count = max(0, p_iworker.ref_count - 1)
                if not still_bound:
                    p_iworker.ref_count = 0
                    timer = self.cleanup_timers.pop(phys_id, None)
                    if timer is not None:
                        timer.cancel()
                    self.physical_workers.pop(phys_id, None)
                    worker_to_stop = p_iworker
        if worker_to_stop is not None:
            try:
                worker_to_stop.stop()
            except Exception as e:
                logger.warning(f"[REGISTRY_WARN] Error stopping inference worker for camera {camera_id}: {e}")

    def ensure_worker(self, camera_id, camera_worker):
        """Returns active live InferenceWorker for camera_id without stacking ref_count on repeated pushes."""
        iw = self.get_active_worker(camera_id)
        if iw is not None:
            return iw
        return self.get_worker(camera_id, camera_worker)

    def get_active_worker(self, camera_id):
        with self.lock:
            iw = self.workers.get(camera_id)
            if iw is None:
                return None
            if not getattr(iw, "running", False) or (iw.thread is not None and not iw.thread.is_alive()):
                self.workers.pop(camera_id, None)
                phys_id = self.camera_to_physical.pop(camera_id, None)
                if phys_id and self.physical_workers.get(phys_id) is iw:
                    self.physical_workers.pop(phys_id, None)
                return None
            return iw


_inference_registry = InferenceRegistry()

def get_inference_registry():
    return _inference_registry
