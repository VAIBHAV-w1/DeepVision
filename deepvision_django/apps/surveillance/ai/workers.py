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
from apps.accounts.email_service import send_security_alert_email

logger = logging.getLogger(__name__)

# Human-readable titles for each event type
_EVENT_TITLES = {
    "loitering": "Loitering Detected",
    "restricted_area_entry": "Restricted Area Entry",
    "unusual_movement": "Unusual Movement Detected",
    "rapid_movement": "Rapid Movement Detected",
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
                orig_h, orig_w = all_frames[0].shape[:2]
                target_w = min(orig_w, 640)
                target_h = int(orig_h * (target_w / orig_w)) if orig_w > 0 else orig_h
                # Ensure even dimensions for h264
                target_w = target_w - (target_w % 2)
                target_h = target_h - (target_h % 2)
                fps = 15.0
                writer = create_browser_compatible_video_writer(vid_path, fps, target_w, target_h)
                if writer:
                    for frm in all_frames:
                        if frm.shape[1] != target_w or frm.shape[0] != target_h:
                            frm = cv2.resize(frm, (target_w, target_h), interpolation=cv2.INTER_AREA)
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
        self.last_inference_completion_time = 0.0
        self.source_frame_capture_monotonic = 0.0
        self.active_persons = []
        self.active_items = []
        self.inference_id = 0
        self.source_frame_id = 0
        self.last_handoff_ms = 0.0
        self.last_stage_timings = {}

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
            "RAPID_MOVEMENT_ENABLED": True,
            "ABANDONED_OBJECT_ENABLED": True,
        })
        self.lifecycle_manager = ItemLifecycleManager()
        self._global_track_last_seen = {}
        self.cached_anomalies = []
        self.cached_zones = []
        self.cached_zones_by_camera = {}
        self.bound_camera_ids = {camera_id}
        self.force_zone_refresh = True

    def bind_camera(self, camera_id):
        with self.lock:
            if camera_id not in self.bound_camera_ids:
                self.bound_camera_ids.add(camera_id)
                self.force_zone_refresh = True

    def invalidate_zones(self):
        self.force_zone_refresh = True

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
        cond = getattr(camera_worker, "frame_condition", None)
        while True:
            with self.lock:
                if not self.running:
                    break

            now = time.time()
            if now - self.last_inference_time < self.inference_interval:
                time.sleep(0.002)
                continue

            source_cap_mono = 0.0
            if cond is not None:
                with cond:
                    while camera_worker.running and camera_worker.frame_id == last_processed_frame_id:
                        if not cond.wait(timeout=0.08):
                            break
                    if not camera_worker.running:
                        break
                    frame_id = camera_worker.frame_id
                    frame = camera_worker.latest_frame.copy() if camera_worker.latest_frame is not None else None
                    source_cap_mono = getattr(camera_worker, "last_capture_monotonic", time.monotonic())
            else:
                with camera_worker.lock:
                    frame_id = camera_worker.frame_id
                    frame = camera_worker.latest_frame.copy() if camera_worker.latest_frame is not None else None
                    source_cap_mono = getattr(camera_worker, "last_capture_monotonic", time.monotonic())

            if frame is None or frame_id == last_processed_frame_id:
                time.sleep(0.002)
                continue

            last_processed_frame_id = frame_id
            self.last_inference_time = now
            handoff_ms = max(0.0, (time.monotonic() - source_cap_mono) * 1000.0) if source_cap_mono > 0 else 0.0

            t0 = time.time()
            try:
                results = self.tracker.track(frame)
                raw_detections = getattr(self.tracker, "last_detections", None)
                stage_timings = dict(getattr(self.tracker, "last_stage_timings", None) or {})
            except Exception as e:
                logger.error(f"[InferenceWorker] Inference error camera {self.camera_id}: {e}")
                results = []
                raw_detections = []
                stage_timings = {}
            t1 = time.time()

            latency = (t1 - t0) * 1000

            # Responsive cadence: minimal pause between inferences
            self.inference_interval = 0.02

            if fps_frame_times and (t1 - fps_frame_times[-1] > 2.0):
                fps_frame_times.clear()
            fps_frame_times.append(t1)
            if len(fps_frame_times) > 10:
                fps_frame_times.pop(0)
            if len(fps_frame_times) >= 2:
                elapsed = fps_frame_times[-1] - fps_frame_times[0]
                ai_fps = round((len(fps_frame_times) - 1) / elapsed, 1) if elapsed > 0 else 0.0
            elif latency > 0:
                ai_fps = round(min(30.0, 1000.0 / latency), 1)
            else:
                ai_fps = 0.0

            # Refresh restricted zones & detection profiles periodically or on demand across all bound logical cameras
            if self.force_zone_refresh or (now - last_zone_refresh > 2.0):
                self.force_zone_refresh = False
                with self.lock:
                    target_cam_ids = sorted(self.bound_camera_ids)
                try:
                    raw_db_zones = list(RestrictedZone.objects.filter(camera_id__in=target_cam_ids, enabled=True).order_by("-id"))
                except Exception:
                    raw_db_zones = []

                # Deduplicate identical coordinates per camera (keep newest row first)
                seen_cam_coords = set()
                stream_zones = []
                zones_by_cam = {cid: [] for cid in target_cam_ids}
                for z in raw_db_zones:
                    ckey = (z.camera_id, int(z.x1), int(z.y1), int(z.x2), int(z.y2))
                    if ckey in seen_cam_coords:
                        continue
                    seen_cam_coords.add(ckey)
                    stream_zones.append(z)
                    zones_by_cam.setdefault(z.camera_id, []).append({
                        "id": z.id,
                        "camera_id": z.camera_id,
                        "name": z.name,
                        "x1": float(z.x1),
                        "y1": float(z.y1),
                        "x2": float(z.x2),
                        "y2": float(z.y2),
                        "color": getattr(z, "color", "#f59e0b") or "#f59e0b",
                        "enabled": bool(z.enabled),
                    })

                # Sync DetectionProfile thresholds from SQLite and preserve active runtime rule toggles
                try:
                    from apps.core.models import DetectionProfile
                    from apps.surveillance.ai.registry import get_inference_registry
                    prof = DetectionProfile.objects.filter(camera_id__in=target_cam_ids).order_by("-updated_at").first()
                    if prof is not None:
                        self.anomaly_detector.config.update({
                            "STATIONARY_DISTANCE_THRESHOLD": float(prof.stationary_distance_threshold or 20.0),
                            "STATIONARY_TIME_THRESHOLD": float(prof.stationary_time_threshold or 3.0),
                            "LOITERING_RADIUS": float(prof.loitering_radius or 80.0),
                            "LOITERING_TIME_THRESHOLD": float(prof.loitering_time_threshold or 10.0),
                            "SPEED_FAST_THRESHOLD": float(prof.speed_fast_threshold or 150.0),
                            "SPEED_SLOW_THRESHOLD": float(prof.speed_slow_threshold or 15.0),
                            "ABANDONED_OBJECT_TIME_THRESHOLD": float(prof.abandoned_object_time_threshold or 10.0),
                            "ABANDONED_OBJECT_DISTANCE_THRESHOLD": float(prof.abandoned_object_distance_threshold or 120.0),
                            "PERSON_OBJECT_ASSOCIATION_DISTANCE": float(prof.person_object_association_distance or 140.0),
                            "UNUSUAL_MOVEMENT_PERSISTENCE_SECONDS": float(prof.unusual_movement_persistence_seconds or 1.5),
                            "ANOMALY_EVENT_COOLDOWN_SECONDS": float(prof.anomaly_event_cooldown_seconds or 30.0),
                        })
                    runtime_cfg = get_inference_registry().get_runtime_settings()
                    if isinstance(runtime_cfg.get("rules"), dict):
                        self.anomaly_detector.config.update(runtime_cfg["rules"])
                except Exception:
                    pass

                last_zone_refresh = now
                with self.lock:
                    self.cached_zones_by_camera = zones_by_cam
                    self.cached_zones = zones_by_cam.get(self.camera_id, [])

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
                            "center": (cx, cy),
                            "confidence": conf
                        })
                    elif cls_name in ["backpack", "handbag", "suitcase", "bottle", "cup", "cell phone", "laptop"]:
                        global_id, certainty = registry.resolve_item(self.camera_id, tid, cls_name, now)
                        active_items.append({
                            "track_id": tid, "global_id": global_id,
                            "class_name": cls_name, "confidence": conf,
                            "certainty": certainty, "bbox": (x1, y1, x2, y2),
                            "center": (cx, cy)
                        })

                reid_track_ids = {
                    int(trk["track_id"]) for trk in results
                    if trk.get("class_name") == "person"
                    or trk.get("class_name") in {"backpack", "handbag", "suitcase", "bottle", "cup", "cell phone", "laptop"}
                }
                registry.reconcile_camera_tracks(
                    self.camera_id, reid_track_ids, self._global_track_last_seen, timestamp=now
                )

                self.lifecycle_manager.update_associations_and_lifecycles(
                    active_persons, active_items, stream_zones, self.camera_id, now
                )

                # Real-time Anomaly Detection Evaluation
                cfg_anom = {
                    "STATIONARY_DISTANCE_THRESHOLD": 20.0,
                    "STATIONARY_TIME_THRESHOLD": 3.0,
                    "LOITERING_RADIUS": 80.0,
                    "LOITERING_TIME_THRESHOLD": 10.0,
                    "SPEED_FAST_THRESHOLD": 150.0,
                    "SPEED_SLOW_THRESHOLD": 15.0,
                    "TRACK_TIMEOUT_SECONDS": 5,
                    **self.anomaly_detector.config,
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
                    trk["behavior"] = beh.get("behavior", "normal")
                    trk["direction"] = beh.get("direction", "stationary")
                    trk["speed"] = round(float(beh.get("speed", 0.0) or 0.0), 1)
                    tracked_objects_for_anom.append({
                        "track_id": t_id,
                        "class_name": c_name,
                        "confidence": c_conf,
                        "center_x": cx,
                        "center_y": cy,
                        "behavior": beh.get("behavior", "normal"),
                        "direction": beh.get("direction", "stationary"),
                        "speed": beh.get("speed", 0.0),
                        "window_speed": beh.get("window_speed", beh.get("speed", 0.0)),
                        "window_displacement": beh.get("window_displacement", 0.0),
                        "direction_reversals": beh.get("direction_reversals", 0),
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

            comp_mono = time.monotonic()
            with self.lock:
                self.inference_id += 1
                self.source_frame_id = frame_id
                self.source_frame_capture_monotonic = source_cap_mono
                self.last_inference_completion_time = comp_mono
                self.last_handoff_ms = round(handoff_ms, 2)
                self.last_stage_timings = stage_timings
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
            if not InferenceWorker._alert_semaphore.acquire(timeout=2.0):
                logger.warning(f"[ALERT_THROTTLED] cam={self.camera_id} event={event.get('event_type','?')} - concurrent limit reached")
                return
            try:
                from apps.alerts.models import Alert, IncidentCase
                from apps.notifications.models import Notification

                target_cam_id = int(event.get("camera_id") or self.camera_id)
                user_id = int(event.get("user_id") or getattr(camera_worker, "user_id", 1) or 1)
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
                    camera_id=target_cam_id,
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
                    camera_id=target_cam_id,
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
                print(f"[ALERT_CREATED] id={alert.id} event={alert.event_type} cam={target_cam_id}")

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

                # Email is limited to configured high/critical alerts and is
                # delivered inside this alert worker, never the capture or
                # inference loop. The persisted in-app notification remains
                # available if SMTP is unavailable.
                try:
                    send_security_alert_email(user_id, alert)
                except Exception:
                    logger.warning("[ALERT_EMAIL_DELIVERY_FAILED] alert_id=%s", alert.id)

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
                    args=(alert.id, target_cam_id, user_id, camera_worker, pre_event_frames, moment_frame),
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
                self.source_frame_id,
                list(self.active_persons),
                list(self.active_items),
                self.last_inference_completion_time,
                self.source_frame_capture_monotonic
            )

    def get_cached_zones(self, camera_id=None):
        with self.lock:
            if camera_id is not None:
                if camera_id not in self.bound_camera_ids:
                    self.bound_camera_ids.add(camera_id)
                    self.force_zone_refresh = True
                return list(self.cached_zones_by_camera.get(camera_id, []))
            return list(self.cached_zones)

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
