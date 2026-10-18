"""
Native Django Surveillance Inference Worker.
Runs YOLO11n + ByteTrack + Behavior Analysis + Anomaly Detection natively.
Integrates directly with Django ORM for Alerts, Notifications, Cases, and Evidence.
"""

import os
import time
import threading
import logging
from datetime import datetime, timezone, timedelta
try:
    import cv2
    import numpy as np
except (ImportError, Exception):
    cv2 = None
    np = None

from django.db import connection
from django.utils import timezone as django_timezone

from apps.surveillance.ai.behavior.track_history import TrackHistoryManager
from apps.surveillance.ai.behavior.behavior_analyzer import BehaviorAnalyzer
from apps.surveillance.ai.anomaly.anomaly_detector import AnomalyDetector
from apps.surveillance.ai.reid import registry
from apps.surveillance.ai.item_lifecycle import ItemLifecycleManager

logger = logging.getLogger(__name__)

# Human-readable titles for each event type
_EVENT_TITLES = {
    "loitering": "Loitering Detected",
    "restricted_area_entry": "Restricted Area Entry",
    "unusual_movement": "Unusual Movement Detected",
    "abandoned_object": "Potentially Unattended Object",
    "crowding": "Crowding / High Density Detected",
    "unexpected_object": "Unauthorized Object Detected",
    "intrusion": "Restricted Perimeter Intrusion",
}
_DEFAULT_TITLE = "Security Anomaly Detected"


def _get_evidence_base_folder():
    """Returns absolute path to instance/evidence."""
    # d:\DeepVision\instance\evidence
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "instance", "evidence"))
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def _get_evidence_dir(camera_id):
    """Returns directory path for a specific camera and current date."""
    base_folder = _get_evidence_base_folder()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder_path = os.path.join(base_folder, f"camera_{camera_id}", date_str)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def create_browser_compatible_video_writer(full_path, fps, width, height):
    """
    Creates an OpenCV VideoWriter prioritized for browser H.264 (avc1) / mp4 compatibility.
    """
    attempts = [
        lambda: cv2.VideoWriter(full_path, cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*'H264'), fps, (width, height)),
        lambda: cv2.VideoWriter(full_path, cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*'avc1'), fps, (width, height)),
        lambda: cv2.VideoWriter(full_path, cv2.VideoWriter_fourcc(*'avc1'), fps, (width, height)),
        lambda: cv2.VideoWriter(full_path, cv2.VideoWriter_fourcc(*'H264'), fps, (width, height)),
        lambda: cv2.VideoWriter(full_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height)),
        lambda: cv2.VideoWriter(full_path, cv2.VideoWriter_fourcc(*'XVID'), fps, (width, height)),
    ]
    for attempt in attempts:
        try:
            w = attempt()
            if w and w.isOpened():
                return w
        except Exception:
            continue
    return None


def _collect_and_save_evidence(alert_id, camera_id, user_id, camera_worker, pre_event_frames, moment_frame):
    """
    Background worker that collects post-event frames, combines with pre-event buffer,
    and persists snapshot and MP4 video evidence records using Django ORM.
    """
    try:
        from apps.alerts.models import Alert
        from apps.evidence.models import Evidence

        alert = Alert.objects.filter(id=alert_id).first()
        if not alert:
            return

        folder = _get_evidence_dir(camera_id)
        base_folder = _get_evidence_base_folder()
        now = django_timezone.now()

        # 1. Save Snapshot
        if moment_frame is not None:
            try:
                snap_name = f"alert_{alert_id}_snapshot.jpg"
                snap_path = os.path.join(folder, snap_name)
                success, buffer = cv2.imencode(".jpg", moment_frame)
                if success:
                    with open(snap_path, "wb") as f:
                        f.write(buffer.tobytes())
                    snap_size = os.path.getsize(snap_path)
                    snap_rel = os.path.relpath(snap_path, base_folder).replace("\\", "/")
                    Evidence.objects.create(
                        alert_id=alert_id,
                        user_id=user_id,
                        camera_id=camera_id,
                        evidence_type="snapshot",
                        file_path=snap_rel,
                        file_name=snap_name,
                        mime_type="image/jpeg",
                        file_size=snap_size,
                        captured_at=now,
                        created_at=now,
                    )
                    logger.info(f"[EVIDENCE_SNAPSHOT_SAVED] alert={alert_id} cam={camera_id}")
            except Exception as snap_err:
                logger.error(f"[EVIDENCE_SNAPSHOT_ERROR] alert={alert_id}: {snap_err}")

        # 2. Collect post-event frames for ~4 seconds
        post_frames = []
        start_t = time.time()
        last_fid = -1
        while len(post_frames) < 80 and (time.time() - start_t < 4.0):
            with camera_worker.lock:
                fid = camera_worker.frame_id
                f = camera_worker.latest_frame
            if f is not None and fid != last_fid:
                last_fid = fid
                post_frames.append(f.copy())
            time.sleep(0.025)

        all_frames = (pre_event_frames or []) + post_frames
        if all_frames:
            try:
                vid_name = f"alert_{alert_id}_clip.mp4"
                vid_path = os.path.join(folder, vid_name)
                h, w = all_frames[0].shape[:2]
                fps = 15.0
                writer = create_browser_compatible_video_writer(vid_path, fps, w, h)
                if writer:
                    for frm in all_frames:
                        if frm.shape[:2] != (h, w):
                            frm = cv2.resize(frm, (w, h))
                        writer.write(frm)
                    writer.release()

                    if os.path.exists(vid_path) and os.path.getsize(vid_path) > 0:
                        vid_size = os.path.getsize(vid_path)
                        vid_rel = os.path.relpath(vid_path, base_folder).replace("\\", "/")
                        dur = round(len(all_frames) / fps, 1)
                        Evidence.objects.create(
                            alert_id=alert_id,
                            user_id=user_id,
                            camera_id=camera_id,
                            evidence_type="video",
                            file_path=vid_rel,
                            file_name=vid_name,
                            mime_type="video/mp4",
                            file_size=vid_size,
                            duration_seconds=dur,
                            captured_at=now,
                            created_at=now,
                        )
                        try:
                            from apps.recordings.models import Recording
                            Recording.objects.create(
                                user_id=user_id,
                                camera_id=camera_id,
                                filename=vid_name,
                                file_path=f"evidence/{vid_rel}".replace("\\", "/"),
                                duration_seconds=dur,
                                file_size=vid_size,
                                started_at=now,
                                ended_at=now + timedelta(seconds=dur),
                                status="completed",
                                created_at=now,
                            )
                        except Exception as rec_err:
                            logger.warning(f"[EVIDENCE_REC_INDEX_WARN] alert={alert_id}: {rec_err}")

                        logger.info(f"[EVIDENCE_VIDEO_SAVED] alert={alert_id} cam={camera_id} total_frames={len(all_frames)} dur={dur}s")
            except Exception as vid_err:
                logger.error(f"[EVIDENCE_VIDEO_ERROR] alert={alert_id}: {vid_err}")

    except Exception as ev_err:
        logger.error(f"[EVIDENCE_COLLECT_ERROR] alert={alert_id}: {ev_err}")
    finally:
        connection.close()


class InferenceWorker:
    """
    Native Django shared per-camera background inference thread.
    Runs YOLO11n + ByteTrack at a wall-clock controlled rate (~125-200ms).
    Multiple stream generators (ORIGINAL, TRACKING+DETECTION) share ONE InferenceWorker per camera.
    """
    _alert_semaphore = threading.BoundedSemaphore(4)

    def __init__(self, camera_id, tracker, inference_interval_ms=150):
        self.camera_id = camera_id
        self.tracker = tracker
        self.inference_interval = inference_interval_ms / 1000.0

        self.thread = None
        self.running = False
        self.ref_count = 0
        self.lock = threading.Lock()

        self.cached_detections = []
        self.cached_tracks = []
        self.latency_ms = 0.0
        self.ai_fps = 0.0
        self.last_inference_time = 0.0
        self.active_persons = []
        self.active_items = []
        self.inference_id = 0
        self.source_frame_id = 0

        self.track_history = TrackHistoryManager()
        self.behavior_analyzer = BehaviorAnalyzer()
        self.anomaly_detector = AnomalyDetector({
            "ANOMALY_EVENT_COOLDOWN_SECONDS": 30,
            "CROWDING_THRESHOLD": 4,
            "CROWDING_ENABLED": True,
            "UNEXPECTED_OBJECT_ENABLED": True,
            "LOITERING_ENABLED": True,
            "RESTRICTED_ENTRY_ENABLED": True,
            "UNUSUAL_MOVEMENT_ENABLED": True,
            "ABANDONED_OBJECT_ENABLED": True,
        })
        self.lifecycle_manager = ItemLifecycleManager()
        self.cached_anomalies = []

    def start(self, camera_worker):
        with self.lock:
            if not self.running:
                self.running = True
                self.thread = threading.Thread(
                    target=self._inference_loop,
                    args=(camera_worker,),
                    name=f"InferenceWorker-{self.camera_id}",
                    daemon=True
                )
                self.thread.start()
                print(f"[INFERENCE_WORKER_STARTED] camera_id={self.camera_id}")

    def _inference_loop(self, camera_worker):
        from apps.core.models import RestrictedZone

        last_processed_frame_id = -1
        fps_frame_times = []
        stream_zones = []
        last_zone_refresh = 0.0

        print(f"[INFERENCE_LOOP_ENTER] camera_id={self.camera_id}")
        while True:
            with self.lock:
                if not self.running:
                    break

            now = time.time()
            if now - self.last_inference_time < self.inference_interval:
                time.sleep(0.005)
                continue

            with camera_worker.lock:
                frame_id = camera_worker.frame_id
                frame = camera_worker.latest_frame.copy() if camera_worker.latest_frame is not None else None

            if frame is None or frame_id == last_processed_frame_id:
                time.sleep(0.005)
                continue

            last_processed_frame_id = frame_id
            self.last_inference_time = now

            t0 = time.time()
            try:
                results = self.tracker.track(frame)
                raw_detections = getattr(self.tracker, "last_detections", None)
            except Exception as e:
                logger.error(f"[InferenceWorker] Inference error camera {self.camera_id}: {e}")
                results = []
                raw_detections = []
            t1 = time.time()

            latency = (t1 - t0) * 1000

            # Adaptive cadence
            if latency < 120:
                target_interval = 0.125
            elif latency < 200:
                target_interval = 0.200
            elif latency < 350:
                target_interval = 0.333
            else:
                target_interval = 0.500
            self.inference_interval = target_interval

            fps_frame_times.append(now)
            if len(fps_frame_times) > 10:
                fps_frame_times.pop(0)
            if len(fps_frame_times) >= 2:
                elapsed = fps_frame_times[-1] - fps_frame_times[0]
                ai_fps = round((len(fps_frame_times) - 1) / elapsed, 1) if elapsed > 0 else 0.0
            else:
                ai_fps = 0.0

            # Refresh restricted zones periodically
            if now - last_zone_refresh > 5.0:
                try:
                    stream_zones = list(RestrictedZone.objects.filter(camera_id=self.camera_id, enabled=True))
                except Exception:
                    stream_zones = []
                last_zone_refresh = now

            active_persons = []
            active_items = []
            detection_list = []

            if raw_detections:
                for det in raw_detections:
                    detection_list.append({
                        "x1": det["x1"], "y1": det["y1"], "x2": det["x2"], "y2": det["y2"],
                        "class_name": det["class_name"], "confidence": det["confidence"]
                    })
            else:
                for trk in results:
                    detection_list.append({
                        "x1": trk["x1"], "y1": trk["y1"], "x2": trk["x2"], "y2": trk["y2"],
                        "class_name": trk["class_name"], "confidence": trk["confidence"]
                    })

            try:
                for trk in results:
                    x1, y1, x2, y2 = trk["x1"], trk["y1"], trk["x2"], trk["y2"]
                    tid = trk["track_id"]
                    cls_name = trk["class_name"]
                    conf = trk["confidence"]
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0

                    if cls_name == "person":
                        cropped = frame[y1:y2, x1:x2] if (x2 > x1 and y2 > y1) else None
                        global_id, reid_status, certainty = registry.resolve_person(self.camera_id, tid, cropped, now)
                        active_persons.append({
                            "track_id": tid, "global_id": global_id,
                            "reid_status": reid_status, "certainty": certainty,
                            "bbox": (x1, y1, x2, y2),
                            "center": (cx, cy)
                        })
                    elif cls_name in ["backpack", "handbag", "suitcase", "bottle", "cup", "cell phone", "laptop"]:
                        global_id, certainty = registry.resolve_item(self.camera_id, tid, cls_name, now)
                        active_items.append({
                            "track_id": tid, "global_id": global_id,
                            "class_name": cls_name, "confidence": conf,
                            "certainty": certainty, "bbox": (x1, y1, x2, y2),
                            "center": (cx, cy)
                        })

                self.lifecycle_manager.update_associations_and_lifecycles(
                    active_persons, active_items, stream_zones, self.camera_id, now
                )

                # Real-time Anomaly Detection Evaluation
                cfg_anom = {
                    "STATIONARY_DISTANCE_THRESHOLD": 15.0,
                    "STATIONARY_TIME_THRESHOLD": 3.0,
                    "LOITERING_RADIUS": 80.0,
                    "LOITERING_TIME_THRESHOLD": 10.0,
                    "SPEED_FAST_THRESHOLD": 150.0,
                    "SPEED_SLOW_THRESHOLD": 15.0,
                    "TRACK_TIMEOUT_SECONDS": 5
                }
                tracked_objects_for_anom = []
                for trk in results:
                    t_id = trk["track_id"]
                    c_name = trk["class_name"]
                    c_conf = trk["confidence"]
                    x1, y1, x2, y2 = trk["x1"], trk["y1"], trk["x2"], trk["y2"]
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0
                    hist = self.track_history.update(t_id, x1, y1, x2, y2, now, cfg_anom)
                    beh = self.behavior_analyzer.analyze(hist, cfg_anom)
                    tracked_objects_for_anom.append({
                        "track_id": t_id,
                        "class_name": c_name,
                        "confidence": c_conf,
                        "center_x": cx,
                        "center_y": cy,
                        "behavior": beh.get("behavior", "normal"),
                        "speed": beh.get("speed", 0.0),
                        "stationary_duration": beh.get("stationary_duration", 0.0)
                    })
                self.track_history.clean_stale_tracks(now, cfg_anom)

                events = self.anomaly_detector.detect(tracked_objects_for_anom, now, zones=stream_zones)
                if events:
                    self.cached_anomalies = events
                    pre_buf = camera_worker.get_recent_buffer(60)
                    m_frame = frame.copy() if frame is not None else None
                    for ev in events:
                        self._trigger_alert_async(ev, camera_worker, pre_buf, m_frame)
            except Exception as e:
                logger.warning(f"[InferenceWorker] Tracking / Anomaly warning camera {self.camera_id}: {e}")

            with self.lock:
                self.inference_id += 1
                self.source_frame_id = frame_id
                self.cached_detections = detection_list
                self.cached_tracks = results
                self.latency_ms = round(latency, 1)
                self.ai_fps = ai_fps
                self.active_persons = active_persons
                self.active_items = active_items

        print(f"[INFERENCE_LOOP_EXIT] camera_id={self.camera_id}")

    def _trigger_alert_async(self, event, camera_worker, pre_event_frames, moment_frame):
        """Dispatches alert persistence and evidence recording natively using Django ORM."""
        def _runner():
            if not InferenceWorker._alert_semaphore.acquire(blocking=False):
                logger.warning(f"[ALERT_THROTTLED] cam={self.camera_id} event={event.get('event_type','?')} - concurrent limit reached")
                return
            try:
                from apps.alerts.models import Alert, IncidentCase
                from apps.notifications.models import Notification

                user_id = getattr(camera_worker, "user_id", 1) or 1
                event_type = event.get("event_type", "unknown")
                track_id = event.get("track_id")
                severity = event.get("severity", "medium").lower()
                message = event.get("message", "")
                confidence = event.get("confidence")
                class_name = event.get("class_name", "")
                raw_ts = event.get("timestamp")
                detected_at = datetime.fromtimestamp(raw_ts, tz=timezone.utc) if raw_ts else django_timezone.now()

                # Deduplication check
                cooldown_seconds = 30
                cutoff = detected_at - timedelta(seconds=cooldown_seconds)
                dup = Alert.objects.filter(
                    camera_id=self.camera_id,
                    event_type=event_type,
                    track_id=track_id,
                    detected_at__gte=cutoff
                ).exclude(status="resolved").first()

                if dup:
                    return

                title = _EVENT_TITLES.get(event_type, _DEFAULT_TITLE)
                if class_name:
                    title = f"{title} ({class_name.capitalize()})"

                now = django_timezone.now()
                alert = Alert.objects.create(
                    user_id=user_id,
                    camera_id=self.camera_id,
                    track_id=track_id,
                    event_type=event_type,
                    title=title,
                    message=message,
                    severity=severity,
                    status="new",
                    confidence=confidence,
                    detected_at=detected_at,
                    created_at=now,
                    updated_at=now,
                    response_state="NEW",
                )
                print(f"[ALERT_CREATED] id={alert.id} event={alert.event_type} cam={self.camera_id}")

                # Notification
                try:
                    Notification.objects.create(
                        user_id=user_id,
                        alert=alert,
                        is_read=False,
                        created_at=now,
                    )
                except Exception as notif_err:
                    logger.warning(f"[NOTIFICATION_CREATE_WARN] alert={alert.id}: {notif_err}")

                # Auto Incident Case for critical / high
                if severity in ("critical", "high"):
                    try:
                        import uuid
                        date_prefix = datetime.now().strftime("%Y%m%d")
                        case_number = f"CASE-{date_prefix}-{uuid.uuid4().hex[:6].upper()}"
                        IncidentCase.objects.create(
                            case_number=case_number,
                            user_id=user_id,
                            alert=alert,
                            title=f"Auto Case: {alert.title}",
                            description=f"Auto-generated incident case for {severity.upper()} alert #{alert.id}.",
                            priority=severity.upper(),
                            status="open",
                            created_at=now,
                            updated_at=now,
                        )
                        print(f"[AUTO_CASE_CREATED] case_number={case_number} alert={alert.id}")
                    except Exception as case_err:
                        logger.warning(f"[AUTO_CASE_WARN] alert={alert.id}: {case_err}")

                # Evidence collection
                t_ev = threading.Thread(
                    target=_collect_and_save_evidence,
                    args=(alert.id, self.camera_id, user_id, camera_worker, pre_event_frames, moment_frame),
                    daemon=True,
                    name=f"EvidenceCollector-{alert.id}"
                )
                t_ev.start()

            except Exception as e:
                logger.error(f"[ALERT_TRIGGER_ERROR] cam={self.camera_id}: {e}")
            finally:
                connection.close()
                InferenceWorker._alert_semaphore.release()

        threading.Thread(target=_runner, daemon=True).start()

    def get_cached_result(self):
        with self.lock:
            return (
                list(self.cached_detections),
                list(self.cached_tracks),
                self.latency_ms,
                self.ai_fps,
                self.inference_id,
                self.source_frame_id
            )

    def stop(self):
        with self.lock:
            self.running = False
        if self.thread:
            try:
                self.thread.join(timeout=2.0)
            except Exception as e:
                logger.warning(f"[INFERENCE_WORKER_WARN] camera_id={self.camera_id} thread join error: {e}")
            self.thread = None
        print(f"[INFERENCE_WORKER_STOPPED] camera_id={self.camera_id}")
