"""
Camera Registry Singleton for Django Surveillance Architecture.
Maintains thread-safe lifecycle and prevents duplicate VideoCapture hardware handles.
"""
import threading
from apps.surveillance.camera.sources import (
    resolve_camera_capture_source,
    get_physical_source_key,
)
from apps.surveillance.camera.workers import CameraWorker

_camera_registry_instance = None
_registry_lock = threading.Lock()


class CameraRegistry:
    def __init__(self):
        self._workers = {}  # camera_id -> CameraWorker
        self._physical_map = {}  # physical_source_key -> CameraWorker
        self._unreachable_until = {}  # physical_source_key -> monotonic timestamp
        self._lock = threading.Lock()

    def get_worker(self, camera_id: int, user_id: int = None, bypass_backoff: bool = False) -> CameraWorker:
        import time
        with self._lock:
            # 1. Existing running worker for this camera
            worker = self._workers.get(camera_id)
            if worker and worker.running:
                worker.ref_count += 1
                return worker
            elif worker and not worker.running:
                self._workers.pop(camera_id, None)
                if getattr(worker, "physical_source_id", None) in self._physical_map:
                    self._physical_map.pop(worker.physical_source_id, None)

            # 2. Look up camera in Django database
            from apps.cameras.models import Camera
            camera = Camera.objects.filter(id=camera_id).first()
            if not camera:
                raise ValueError(f"Camera with ID {camera_id} not found in database.")

            source_type = camera.source_type
            source = camera.source
            owner_id = user_id or camera.user_id
            physical_key = get_physical_source_key(source_type, source)

            # 3. Check if physical hardware is already claimed
            existing_physical = self._physical_map.get(physical_key)
            if existing_physical and existing_physical.running:
                print(f"[REGISTRY] Re-binding existing physical worker ({physical_key}) to camera {camera_id}")
                self._workers[camera_id] = existing_physical
                existing_physical.ref_count += 1
                if camera.status != "online":
                    Camera.objects.filter(id=camera_id).update(status="online")
                return existing_physical
            elif existing_physical and not existing_physical.running:
                self._physical_map.pop(physical_key, None)

            # 3b. Fast-fail backoff for unreachable network streams to prevent HTTP thread starvation
            is_network = source_type in ("phone", "ipcamera", "rtsp", "http", "https", "ip", "mjpeg")
            now_mono = time.monotonic()
            if is_network and not bypass_backoff:
                backoff_until = self._unreachable_until.get(physical_key, 0.0)
                if now_mono < backoff_until:
                    if camera.status != "offline":
                        Camera.objects.filter(id=camera_id).update(status="offline")
                    raise RuntimeError(f"Network camera {camera_id} ({physical_key}) is unreachable (retry backoff active).")

            # 4. Resolve source and allocate new CameraWorker
            cap_source = resolve_camera_capture_source(source_type, source)
            worker = CameraWorker(
                camera_id=camera_id,
                cap_source=cap_source,
                source_type=source_type,
                user_id=owner_id,
                physical_source_id=physical_key,
            )
            try:
                worker.start()
            except Exception as start_exc:
                if is_network:
                    self._unreachable_until[physical_key] = time.monotonic() + 30.0
                if camera.status != "offline":
                    Camera.objects.filter(id=camera_id).update(status="offline")
                raise start_exc

            if not worker.running:
                if is_network:
                    self._unreachable_until[physical_key] = time.monotonic() + 30.0
                if camera.status != "offline":
                    Camera.objects.filter(id=camera_id).update(status="offline")
                raise RuntimeError(f"Failed to start CameraWorker for camera {camera_id}: {worker.start_error}")

            self._unreachable_until.pop(physical_key, None)
            if camera.status != "online":
                Camera.objects.filter(id=camera_id).update(status="online")
            worker.ref_count = 1
            self._workers[camera_id] = worker
            self._physical_map[physical_key] = worker
            return worker

    def get_active_worker(self, camera_id: int) -> CameraWorker:
        with self._lock:
            worker = self._workers.get(camera_id)
            if worker and worker.running:
                return worker
            # Also check if another logical camera already opened the same physical source
            try:
                from apps.cameras.models import Camera
                camera = Camera.objects.filter(id=camera_id).only("id", "source_type", "source").first()
                if camera:
                    physical_key = get_physical_source_key(camera.source_type, camera.source)
                    phys_worker = self._physical_map.get(physical_key)
                    if phys_worker and phys_worker.running:
                        self._workers[camera_id] = phys_worker
                        return phys_worker
            except Exception:
                pass
            return None

    def get_bound_camera_ids(self, physical_key: str):
        with self._lock:
            ids = [cid for cid, w in self._workers.items() if getattr(w, "physical_source_id", None) == physical_key and w.running]
            return ids

    def remove_camera(self, camera_id: int):
        """Safely detaches a deleted or reconfigured camera; stops hardware worker if no other camera shares it."""
        worker_to_stop = None
        with self._lock:
            worker = self._workers.pop(camera_id, None)
            if worker:
                phys_key = getattr(worker, "physical_source_id", None)
                still_shared = any(w is worker for w in self._workers.values())
                if not still_shared:
                    if phys_key and self._physical_map.get(phys_key) is worker:
                        self._physical_map.pop(phys_key, None)
                    worker_to_stop = worker
        if worker_to_stop:
            try:
                worker_to_stop.stop()
            except Exception:
                pass

    def get_physical_worker(self, physical_key: str) -> CameraWorker:
        with self._lock:
            worker = self._physical_map.get(physical_key)
            if worker and worker.running:
                return worker
            return None

    def release_worker(self, camera_id: int):
        with self._lock:
            worker = self._workers.get(camera_id)
            if worker:
                worker.ref_count = max(0, worker.ref_count - 1)
                # Keep active for continuous background surveillance

    @property
    def workers(self):
        with self._lock:
            return dict(self._workers)

    def get_all_workers(self):
        with self._lock:
            return [w for w in self._workers.values() if w.running]


def get_camera_registry() -> CameraRegistry:
    global _camera_registry_instance
    with _registry_lock:
        if _camera_registry_instance is None:
            _camera_registry_instance = CameraRegistry()
        return _camera_registry_instance
