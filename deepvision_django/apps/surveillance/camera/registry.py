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
        self._lock = threading.Lock()

    def get_worker(self, camera_id: int, user_id: int = None) -> CameraWorker:
        with self._lock:
            # 1. Existing running worker for this camera
            worker = self._workers.get(camera_id)
            if worker and worker.running:
                worker.ref_count += 1
                return worker

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
                return existing_physical

            # 4. Resolve source and allocate new CameraWorker
            cap_source = resolve_camera_capture_source(source_type, source)
            worker = CameraWorker(
                camera_id=camera_id,
                cap_source=cap_source,
                source_type=source_type,
                user_id=owner_id,
                physical_source_id=physical_key,
            )
            worker.start()
            if not worker.running:
                raise RuntimeError(f"Failed to start CameraWorker for camera {camera_id}: {worker.start_error}")

            worker.ref_count = 1
            self._workers[camera_id] = worker
            self._physical_map[physical_key] = worker
            return worker

    def get_active_worker(self, camera_id: int) -> CameraWorker:
        with self._lock:
            worker = self._workers.get(camera_id)
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
