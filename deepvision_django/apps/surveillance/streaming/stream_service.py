"""
Native Django Surveillance Streaming Service.
Directly generates MJPEG streams for ORIGINAL and TRACKING+DETECTION modes
using shared singleton CameraWorker and InferenceWorker without Flask.
"""

import os
import time
try:
    import cv2
    import numpy as np
    _STREAM_Q = max(50, min(92, int(os.getenv("DEEPVISION_STREAM_JPEG_QUALITY", "80") or 80)))
    _JPEG_STREAM_QUALITY = [int(cv2.IMWRITE_JPEG_QUALITY), _STREAM_Q]
except (ImportError, Exception):
    cv2 = None
    np = None
    _JPEG_STREAM_QUALITY = [1, 80]
import logging
from typing import Generator, Dict, Any, List

from apps.surveillance.camera.registry import get_camera_registry
from apps.surveillance.recording import recording_service
from apps.surveillance.health.health_service import update_camera_health
try:
    from apps.surveillance.ai.registry import get_inference_registry
    from apps.surveillance.ai.reid import registry as reid_registry
except (ImportError, Exception):
    get_inference_registry = None
    reid_registry = None

logger = logging.getLogger(__name__)

_stream_telemetry: Dict[int, Dict[str, Any]] = {}


from apps.surveillance.ai.anomaly.zones import (
    resolve_zone_pixel_bounds,
    resolve_polygon_pixel_points,
    point_in_polygon,
)


def _to_pixel_coords(x1: float, y1: float, x2: float, y2: float, fw: int, fh: int, ref_width: int = None, ref_height: int = None):
    """Safely converts coordinates (normalized, 720p/1080p, or native pixels) to valid frame bounds."""
    return resolve_zone_pixel_bounds(
        x1, y1, x2, y2, frame_width=fw, frame_height=fh, ref_width=ref_width, ref_height=ref_height
    )


def _zone_pixel_polygon(z: dict, fw: int, fh: int):
    return resolve_polygon_pixel_points(
        z.get("points"),
        z.get("x1", 0),
        z.get("y1", 0),
        z.get("x2", 0),
        z.get("y2", 0),
        frame_width=fw,
        frame_height=fh,
        ref_width=z.get("ref_width"),
        ref_height=z.get("ref_height"),
    )


def _point_in_zone(px: float, py: float, z: dict, fw: int, fh: int) -> bool:
    """Checks whether reference point (px, py) falls inside a polygon or rectangular zone."""
    pts = z.get("points")
    if isinstance(pts, (list, tuple)) and len(pts) >= 3:
        poly = _zone_pixel_polygon(z, fw, fh)
        return point_in_polygon(float(px), float(py), poly)
    zx1, zy1, zx2, zy2 = _to_pixel_coords(
        z["x1"],
        z["y1"],
        z["x2"],
        z["y2"],
        fw,
        fh,
        ref_width=z.get("ref_width"),
        ref_height=z.get("ref_height"),
    )
    return zx1 <= px <= zx2 and zy1 <= py <= zy2


def get_camera_telemetry(camera_id: int) -> Dict[str, Any]:
    """Returns the latest tracking telemetry for UI stats polling."""
    return _stream_telemetry.get(camera_id, {
        "camera_id": camera_id,
        "tracks": [],
        "anomalies": [],
        "fps": 0.0,
        "status": "active"
    })


def clear_camera_telemetry(camera_id: int) -> None:
    """Clears cached per-camera stream telemetry on disconnect, source change, or deletion."""
    _stream_telemetry.pop(int(camera_id), None)


def _resolve_stream_encode_params(camera_id: int):
    try:
        from apps.cameras.surveillance_config import get_camera_surveillance_config, resolve_video_quality_profile
        cfg = get_camera_surveillance_config(camera_id)
        q_prof = resolve_video_quality_profile(cfg.get("video_quality"))
        q_val = max(55, min(95, int(os.getenv("DEEPVISION_STREAM_JPEG_QUALITY", str(q_prof["stream_jpeg_quality"])))))
        return str(q_prof["id"]), [int(cv2.IMWRITE_JPEG_QUALITY), q_val]
    except Exception:
        return "high", _JPEG_STREAM_QUALITY


def generate_raw_stream(camera_id: int, user_id: int) -> Generator[bytes, None, None]:
    """
    Generator for ORIGINAL CCTV raw video stream (no AI overlays).
    """
    camera_registry = get_camera_registry()
    worker = None
    last_processed_id = -1
    disp_frame_times: List[float] = []
    start_no_frame_time = time.time()
    last_health_sync_mono = 0.0
    last_cfg_sync_mono = 0.0
    video_quality_id, encode_params = _resolve_stream_encode_params(camera_id)

    update_camera_health(camera_id, delta_stream_count=1)

    try:
        worker = camera_registry.get_worker(camera_id, user_id)
        last_new_frame_mono = time.monotonic()
        has_yielded_frame = False
        init_status = "online" if float(getattr(worker, "last_valid_frame_time", 0.0) or 0.0) > 0.0 else "connecting"
        update_camera_health(camera_id, status=init_status, stream_active=True, detection_active=False, tracking_active=False, ai_fps=0.0, inference_latency_ms=0.0)
        cond = getattr(worker, "frame_condition", None)

        while True:
            if not worker.running:
                update_camera_health(camera_id, status="offline", fps=0.0, stream_active=False)
                break

            if cond is not None:
                with cond:
                    while worker.running and worker.frame_id == last_processed_id:
                        if not cond.wait(timeout=0.25):
                            break
                    if not worker.running:
                        update_camera_health(camera_id, status="offline", fps=0.0, stream_active=False)
                        break
                    current_id = worker.frame_id
                    frame = worker.latest_frame
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())
            else:
                with worker.lock:
                    current_id = worker.frame_id
                    frame = worker.latest_frame if (worker.latest_frame is not None and current_id != last_processed_id) else None
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())

            if current_id == last_processed_id or frame is None:
                idle_sec = time.monotonic() - last_new_frame_mono
                is_reconn = bool(getattr(worker, "is_reconnecting", False))
                if (frame is None and idle_sec > 10.0) or (has_yielded_frame and idle_sec > 12.0 and not is_reconn) or (idle_sec > 18.0):
                    logger.warning(f"[RAW_STREAM] Camera {camera_id}: No fresh frame within {idle_sec:.1f}s; closing stale stream.")
                    update_camera_health(camera_id, status="offline", fps=0.0, stream_active=False, last_error="Stream timed out waiting for fresh camera frames.")
                    break
                time.sleep(0.003)
                continue

            now_mono = time.monotonic()
            last_new_frame_mono = now_mono
            has_yielded_frame = True
            last_processed_id = current_id

            now = time.time()
            disp_frame_times.append(now)
            if len(disp_frame_times) > 15:
                disp_frame_times.pop(0)
            display_fps = 0.0
            if len(disp_frame_times) >= 2:
                elapsed = disp_frame_times[-1] - disp_frame_times[0]
                if elapsed > 0:
                    display_fps = round((len(disp_frame_times) - 1) / elapsed, 1)

            fh, fw = frame.shape[:2]
            if (now_mono - last_health_sync_mono) >= 0.25:
                last_health_sync_mono = now_mono
                update_camera_health(camera_id, status="online", fps=display_fps if display_fps > 0 else None, width=fw, height=fh)
            if (now_mono - last_cfg_sync_mono) >= 2.5:
                last_cfg_sync_mono = now_mono
                video_quality_id, encode_params = _resolve_stream_encode_params(camera_id)

            cap_handoff_ms = max(0.0, (now_mono - cap_mono) * 1000.0) if cap_mono > 0 else 0.0
            acq_ms = float(getattr(worker, "last_acquisition_ms", 0.0) or 0.0)
            t_enc0 = time.monotonic()
            ret, buffer = cv2.imencode(".jpg", frame, encode_params)
            encode_ms = (time.monotonic() - t_enc0) * 1000.0
            if not ret:
                continue

            send_mono = time.monotonic()
            jpeg_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg_bytes)).encode('ascii') + b"\r\n"
                   b"X-Capture-Timestamp: " + f"{cap_mono:.6f}".encode('ascii') + b"\r\n"
                   b"X-Server-Send-Timestamp: " + f"{send_mono:.6f}".encode('ascii') + b"\r\n"
                   b"X-Acquisition-Ms: " + f"{acq_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Handoff-Ms: " + f"{cap_handoff_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Encode-Ms: " + f"{encode_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Frame-ID: " + str(current_id).encode('ascii') + b"\r\n\r\n" +
                   jpeg_bytes + b"\r\n")

    except (GeneratorExit, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        logger.info(f"[RAW_STREAM_CLIENT_DISCONNECTED] camera_id={camera_id}")
    except Exception as e:
        logger.error(f"[RAW_STREAM_ERROR] camera_id={camera_id}: {e}")
        update_camera_health(camera_id, status="offline", last_error=str(e))
    finally:
        if worker is not None:
            try:
                camera_registry.release_worker(camera_id)
            except Exception as e:
                logger.warning(f"[RAW_STREAM_CLEANUP_WARN] {e}")
        update_camera_health(camera_id, delta_stream_count=-1)


def render_annotated_frame(
    frame,
    camera_id: int,
    inference_worker=None,
    current_id: int = 0,
    cap_mono: float = 0.0,
    display_fps: float = 0.0,
    worker=None,
):
    """
    Renders real restricted zones, zone intrusion highlights, person/item/object
    bounding boxes and ByteTrack track IDs directly onto a BGR frame copy,
    returning `(annotated_frame, telemetry_dict)`.
    Used by both the live MJPEG tracking stream and annotated snapshot endpoint.
    """
    if frame is None or cv2 is None:
        return frame, {}

    out = frame.copy()
    fh, fw = out.shape[:2]
    res_scale = max(0.75, min(1.6, fw / 1280.0))
    box_thick = max(2, int(round(2.0 * res_scale)))
    font_sm = round(0.50 * res_scale, 2)
    font_zone = round(0.56 * res_scale, 2)
    now_mono = time.monotonic()

    cached_tracks = []
    latency_ms = 0.0
    ai_fps = 0.0
    inf_source_fid = 0
    active_persons = []
    active_items = []
    inf_comp_time = 0.0
    detector_backend = "inactive"
    tracker_backend = "inactive"
    cached_anomalies = []
    cached_zones = []
    stage_timings = {}
    inf_handoff_ms = 0.0
    summary = {}

    if inference_worker is not None:
        inf_res = inference_worker.get_cached_result()
        cached_tracks = inf_res[1] or []
        latency_ms = inf_res[2] or 0.0
        ai_fps = inf_res[3] or 0.0
        inf_source_fid = inf_res[5] if len(inf_res) > 5 else 0
        active_persons = inf_res[6] if len(inf_res) > 6 else []
        active_items = inf_res[7] if len(inf_res) > 7 else []
        inf_comp_time = inf_res[8] if len(inf_res) > 8 else 0.0
        tracker = getattr(inference_worker, "tracker", None)
        detector_backend = getattr(tracker, "detector_backend", "unknown") if tracker is not None else "unknown"
        tracker_backend = getattr(tracker, "tracker_backend", "unknown") if tracker is not None else "unknown"
        cached_anomalies = getattr(inference_worker, "cached_anomalies", []) or []
        stage_timings = getattr(inference_worker, "last_stage_timings", None) or {}
        inf_handoff_ms = float(getattr(inference_worker, "last_handoff_ms", 0.0) or 0.0)
        if hasattr(inference_worker, "get_telemetry_summary"):
            summary = inference_worker.get_telemetry_summary()

        raw_zones = inference_worker.get_cached_zones(camera_id) if hasattr(inference_worker, "get_cached_zones") else []
        seen_sigs = set()
        for z in raw_zones:
            pts = z.get("points")
            pts_sig = tuple((round(float(p["x"]), 4), round(float(p["y"]), 4)) for p in pts) if isinstance(pts, list) else None
            coord_key = pts_sig or (int(z.get("x1", 0)), int(z.get("y1", 0)), int(z.get("x2", 0)), int(z.get("y2", 0)))
            if coord_key not in seen_sigs:
                seen_sigs.add(coord_key)
                cached_zones.append(z)

    stream_handoff_ms = max(0.0, (now_mono - cap_mono) * 1000.0) if cap_mono > 0 else 0.0
    if inf_handoff_ms <= 0.0:
        inf_handoff_ms = stream_handoff_ms
    acq_ms = float(getattr(worker, "last_acquisition_ms", 0.0) or 0.0) if worker is not None else 0.0
    preprocess_ms = float(stage_timings.get("preprocess_ms", 0.0) or 0.0)
    inference_only_ms = float(stage_timings.get("inference_ms", 0.0) or 0.0)
    tracking_only_ms = float(stage_timings.get("tracking_ms", 0.0) or 0.0)

    inference_age_ms = max(0.0, (now_mono - inf_comp_time) * 1000.0) if inf_comp_time > 0 else 0.0
    is_stale_detection = (
        (current_id - inf_source_fid > 25) if (inf_source_fid and current_id) else (inference_age_ms > 2000.0 and inf_comp_time > 0)
    )
    hide_boxes = (inference_age_ms > 6000.0 and inf_comp_time > 0)

    # Detect which zones currently contain any person's bottom-center foot reference point
    active_intrusions = set()
    if not hide_boxes:
        person_ref_points = []
        for p in (active_persons or []):
            if p.get("foot_point"):
                person_ref_points.append(p["foot_point"])
            else:
                bx1, _, bx2, by2 = p["bbox"]
                person_ref_points.append((0.5 * (bx1 + bx2), float(by2)))
        if not person_ref_points and cached_tracks:
            for trk in cached_tracks:
                if trk.get("class_name") == "person":
                    person_ref_points.append((0.5 * (trk["x1"] + trk["x2"]), float(trk["y2"])))
        for rpx, rpy in person_ref_points:
            for z in cached_zones:
                if z.get("enabled", True) and _point_in_zone(rpx, rpy, z, fw, fh):
                    active_intrusions.add(z["id"])

    # 1. Draw Restricted Zones (polygons or rectangles)
    for z in cached_zones:
        if not z.get("enabled", True):
            continue
        poly_pts = _zone_pixel_polygon(z, fw, fh)
        zid = z["id"]
        zname = z.get("name", "Restricted Area")
        is_intruded = zid in active_intrusions
        lx = poly_pts[0][0] if poly_pts else 10
        ly = min((pt[1] for pt in poly_pts), default=24)

        if is_intruded:
            z_color = (0, 0, 235)
            if np is not None and len(poly_pts) >= 3:
                pts_arr = np.array(poly_pts, dtype=np.int32)
                rx0 = max(0, int(np.min(pts_arr[:, 0])))
                ry0 = max(0, int(np.min(pts_arr[:, 1])))
                rx1 = min(fw, int(np.max(pts_arr[:, 0])) + 1)
                ry1 = min(fh, int(np.max(pts_arr[:, 1])) + 1)
                if rx1 > rx0 and ry1 > ry0:
                    roi_dst = out[ry0:ry1, rx0:rx1]
                    roi_ovr = roi_dst.copy()
                    pts_local = (pts_arr - np.array([rx0, ry0], dtype=np.int32)).reshape((-1, 1, 2))
                    cv2.fillPoly(roi_ovr, [pts_local], (0, 0, 180))
                    cv2.addWeighted(roi_dst, 0.78, roi_ovr, 0.22, 0, roi_dst)
                cv2.polylines(out, [pts_arr.reshape((-1, 1, 2))], True, z_color, max(2, box_thick + 1))
            zlabel = f"[!] RESTRICTED ENTRY: {zname.upper()}"
            cv2.putText(out, zlabel, (max(8, lx + 8), max(24, ly + 22)), cv2.FONT_HERSHEY_SIMPLEX, font_zone, (0, 0, 255), box_thick)
        else:
            z_color = (0, 165, 255)
            if np is not None and len(poly_pts) >= 3:
                pts_arr = np.array(poly_pts, dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(out, [pts_arr], True, z_color, box_thick)
            zlabel = f"ZONE: {zname}"
            cv2.putText(out, zlabel, (max(8, lx + 8), max(20, ly + 20)), cv2.FONT_HERSHEY_SIMPLEX, font_sm, z_color, box_thick)

    ui_tracks = []
    if not hide_boxes:
        # 2. Persons (Green or Red if foot point inside restricted zone)
        for p in (active_persons or []):
            tx1, ty1, tx2, ty2 = p["bbox"]
            tid = p.get("track_id", "")
            gid = p.get("global_id", "")
            tconf = p.get("confidence", 1.0)
            rpx, rpy = p.get("foot_point") or (0.5 * (tx1 + tx2), float(ty2))
            in_zone = any(_point_in_zone(rpx, rpy, z, fw, fh) for z in cached_zones if z.get("enabled", True))
            if in_zone:
                box_color = (0, 0, 235)
                label = f"ALERT PERSON #{tid} (IN ZONE) {tconf:.2f}"
            else:
                box_color = (0, 200, 100) if not is_stale_detection else (0, 180, 180)
                short_gid = "-".join(str(gid).split("-")[:2]) if gid else ""
                label = f"person #{tid} {tconf:.2f} ({short_gid})" if short_gid else f"person #{tid} {tconf:.2f}"
            cv2.rectangle(out, (tx1, ty1), (tx2, ty2), box_color, box_thick)
            cv2.circle(out, (int(round(rpx)), int(round(rpy))), max(3, box_thick + 2), box_color, -1)
            cv2.putText(out, label, (tx1, max(18, ty1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, font_sm, box_color, box_thick)

        # 3. Items (Orange)
        for item in (active_items or []):
            tx1, ty1, tx2, ty2 = item["bbox"]
            color = (0, 165, 255)
            cv2.rectangle(out, (tx1, ty1), (tx2, ty2), color, 2)
            lbl1 = f"{item.get('global_id','')}"
            lbl2 = f"{item['class_name'].upper()} {item.get('confidence', 1.0):.2f}"
            cv2.putText(out, lbl1, (tx1, max(15, ty1 - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            cv2.putText(out, lbl2, (tx1, max(15, ty1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # 4. Other / All ByteTrack Objects (Gold)
        drawn_boxes = [p["bbox"] for p in (active_persons or [])] + [item["bbox"] for item in (active_items or [])]
        for trk in (cached_tracks or []):
            tx1, ty1, tx2, ty2 = trk["x1"], trk["y1"], trk["x2"], trk["y2"]
            if not any(abs(tx1 - bx[0]) < 15 and abs(ty1 - bx[1]) < 15 for bx in drawn_boxes):
                track_color = (0, 215, 255)
                cv2.rectangle(out, (tx1, ty1), (tx2, ty2), track_color, 2)
                lbl = f"#{trk['track_id']} {trk['class_name']} {trk['confidence']:.2f}"
                cv2.putText(out, lbl, (tx1, max(15, ty1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, track_color, 2)
            ui_tracks.append({
                "track_id": f"#{trk['track_id']}",
                "class_name": trk["class_name"].capitalize(),
                "confidence": round(float(trk["confidence"]), 3),
                "bbox": [int(trk["x1"]), int(trk["y1"]), int(trk["x2"]), int(trk["y2"])],
                "behavior": trk.get("behavior") or "normal",
                "direction": trk.get("direction") or "stationary",
                "speed": round(float(trk.get("speed", 0.0) or 0.0), 1),
            })

    if detector_backend == "initializing":
        cv2.rectangle(out, (10, fh - 34), (185, fh - 10), (15, 23, 42), -1)
        cv2.putText(out, "AI INITIALIZING...", (18, fh - 17), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (56, 189, 248), 1)

    telemetry = {
        "camera_id": camera_id,
        "tracks": ui_tracks,
        "anomalies": cached_anomalies,
        "zones": cached_zones,
        "active_intrusions": list(active_intrusions),
        "frame_width": int(fw),
        "frame_height": int(fh),
        "resolution": f"{int(fw)}x{int(fh)}",
        "fourcc": getattr(worker, "fourcc", "") if worker is not None else "",
        "currently_visible_persons": summary.get("currently_visible_persons", len(active_persons)),
        "active_tracks": summary.get("active_tracks", len(ui_tracks)),
        "unique_persons_observed": summary.get("unique_persons_observed", len(active_persons)),
        "total_detection_events": summary.get("total_detection_events", len(ui_tracks)),
        "recent_detections": summary.get("recent_detections", []),
        "recent_zone_events": summary.get("recent_zone_events", []),
        "camera_purpose": summary.get("camera_purpose", "general"),
        "restricted_entry_enabled": summary.get("restricted_entry_enabled", bool(cached_zones)),
        "fps": display_fps if display_fps > 0 else (ai_fps or (worker.fps if worker else 0.0)),
        "ai_fps": ai_fps,
        "latency_ms": latency_ms,
        "p50_latency_ms": summary.get("p50_latency_ms", latency_ms),
        "p95_latency_ms": summary.get("p95_latency_ms", latency_ms),
        "frame_age_ms": round(stream_handoff_ms, 1),
        "ai_profile": summary.get("ai_profile", "balanced"),
        "detector_backend": detector_backend,
        "tracker_backend": tracker_backend,
        "motion_active": summary.get("motion_active", False),
        "motion_ratio": summary.get("motion_ratio", 0.0),
        "motion_lighting_shift": summary.get("motion_lighting_shift", False),
        "motion_backend": summary.get("motion_backend", "mog2"),
        "inference_dropped_frames": summary.get("inference_dropped_frames", 0),
        "session_started_at": summary.get("session_started_at", ""),
        "stage_timings": {
            "acquisition_ms": round(acq_ms, 2),
            "handoff_ms": round(inf_handoff_ms, 2),
            "stream_handoff_ms": round(stream_handoff_ms, 2),
            "preprocess_ms": round(preprocess_ms, 2),
            "inference_ms": round(inference_only_ms, 2),
            "tracking_ms": round(tracking_only_ms, 2),
        },
        "inference_age_ms": round(inference_age_ms, 1),
        "is_stale_detection": is_stale_detection,
        "status": "active",
        "_raw_counts": {
            "acq_ms": acq_ms,
            "inf_handoff_ms": inf_handoff_ms,
            "preprocess_ms": preprocess_ms,
            "inference_only_ms": inference_only_ms,
            "tracking_only_ms": tracking_only_ms,
            "inf_source_fid": inf_source_fid,
            "inference_age_ms": inference_age_ms,
            "ai_fps": ai_fps,
            "latency_ms": latency_ms,
        },
    }
    return out, telemetry


def generate_tracking_stream(camera_id: int, user_id: int) -> Generator[bytes, None, None]:
    """
    Generator for TRACKING + DETECTION stream (YOLO11n + ByteTrack overlays).
    """
    camera_registry = get_camera_registry()
    inference_registry = get_inference_registry()
    worker = None
    inference_worker = None
    last_processed_id = -1
    disp_frame_times: List[float] = []
    start_no_frame_time = time.time()
    last_health_sync_mono = 0.0
    last_cfg_sync_mono = 0.0
    video_quality_id, encode_params = _resolve_stream_encode_params(camera_id)

    update_camera_health(camera_id, delta_stream_count=1)

    try:
        worker = camera_registry.get_worker(camera_id, user_id)
        try:
            inference_worker = inference_registry.get_worker(camera_id, worker) if get_inference_registry else None
        except Exception as inf_init_err:
            logger.warning(f"[TRACKING_STREAM_INF_INIT_WARN] camera_id={camera_id}: {inf_init_err}")
            inference_worker = None
        last_new_frame_mono = time.monotonic()
        has_yielded_frame = False
        init_status = "online" if float(getattr(worker, "last_valid_frame_time", 0.0) or 0.0) > 0.0 else "connecting"
        update_camera_health(
            camera_id,
            status=init_status,
            stream_active=True,
            detection_active=bool(inference_worker),
            tracking_active=bool(inference_worker),
        )
        cond = getattr(worker, "frame_condition", None)

        while True:
            if not worker.running:
                update_camera_health(camera_id, status="offline", fps=0.0, ai_fps=0.0, inference_latency_ms=0.0, stream_active=False)
                break

            if cond is not None:
                with cond:
                    while worker.running and worker.frame_id == last_processed_id:
                        if not cond.wait(timeout=0.25):
                            break
                    if not worker.running:
                        update_camera_health(camera_id, status="offline", fps=0.0, ai_fps=0.0, inference_latency_ms=0.0, stream_active=False)
                        break
                    current_id = worker.frame_id
                    frame = worker.latest_frame
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())
            else:
                with worker.lock:
                    current_id = worker.frame_id
                    frame = worker.latest_frame if (worker.latest_frame is not None and current_id != last_processed_id) else None
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())

            if current_id == last_processed_id or frame is None:
                idle_sec = time.monotonic() - last_new_frame_mono
                is_reconn = bool(getattr(worker, "is_reconnecting", False))
                if (frame is None and idle_sec > 10.0) or (has_yielded_frame and idle_sec > 12.0 and not is_reconn) or (idle_sec > 18.0):
                    logger.warning(f"[TRACKING_STREAM] Camera {camera_id}: No fresh frame within {idle_sec:.1f}s; closing stale stream.")
                    update_camera_health(
                        camera_id,
                        status="offline",
                        fps=0.0,
                        ai_fps=0.0,
                        inference_latency_ms=0.0,
                        stream_active=False,
                        last_error="Stream timed out waiting for fresh camera frames.",
                    )
                    break
                time.sleep(0.003)
                continue

            last_new_frame_mono = time.monotonic()
            has_yielded_frame = True
            last_processed_id = current_id
            now = time.time()
            disp_frame_times.append(now)
            if len(disp_frame_times) > 15:
                disp_frame_times.pop(0)
            display_fps = 0.0
            if len(disp_frame_times) >= 2:
                elapsed = disp_frame_times[-1] - disp_frame_times[0]
                if elapsed > 0:
                    display_fps = round((len(disp_frame_times) - 1) / elapsed, 1)

            try:
                annotated_frame, telemetry = render_annotated_frame(
                    frame,
                    camera_id,
                    inference_worker=inference_worker,
                    current_id=current_id,
                    cap_mono=cap_mono,
                    display_fps=display_fps,
                    worker=worker,
                )
            except Exception as ann_err:
                logger.warning(f"[TRACKING_ANNOTATE_ERROR] camera_id={camera_id}: {ann_err}")
                annotated_frame = frame
                telemetry = {
                    "camera_id": camera_id,
                    "fps": display_fps,
                    "ai_fps": 0.0,
                    "latency_ms": 0.0,
                    "stage_timings": {},
                    "_raw_counts": {"ai_fps": 0.0, "latency_ms": 0.0},
                }

            raw_counts = telemetry.pop("_raw_counts", {})
            ai_fps = raw_counts.get("ai_fps", 0.0)
            latency_ms = raw_counts.get("latency_ms", 0.0)
            now_mono = time.monotonic()
            fh_cur, fw_cur = annotated_frame.shape[:2]
            if (now_mono - last_health_sync_mono) >= 0.25:
                last_health_sync_mono = now_mono
                update_camera_health(
                    camera_id,
                    status="online",
                    fps=display_fps if display_fps > 0 else None,
                    ai_fps=ai_fps,
                    inference_latency_ms=latency_ms,
                    width=fw_cur,
                    height=fh_cur,
                )
            if (now_mono - last_cfg_sync_mono) >= 2.5:
                last_cfg_sync_mono = now_mono
                video_quality_id, encode_params = _resolve_stream_encode_params(camera_id)

            t_enc0 = time.monotonic()
            ret, buffer = cv2.imencode(".jpg", annotated_frame, encode_params)
            encode_ms = (time.monotonic() - t_enc0) * 1000.0
            if not ret:
                continue

            telemetry["stage_timings"]["encode_ms"] = round(encode_ms, 2)
            _stream_telemetry[camera_id] = telemetry

            acq_ms = raw_counts.get("acq_ms", 0.0)
            inf_handoff_ms = raw_counts.get("inf_handoff_ms", 0.0)
            preprocess_ms = raw_counts.get("preprocess_ms", 0.0)
            inference_only_ms = raw_counts.get("inference_only_ms", 0.0)
            tracking_only_ms = raw_counts.get("tracking_only_ms", 0.0)
            inf_source_fid = raw_counts.get("inf_source_fid", 0)
            inference_age_ms = raw_counts.get("inference_age_ms", 0.0)

            send_mono = time.monotonic()
            jpeg_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg_bytes)).encode('ascii') + b"\r\n"
                   b"X-Capture-Timestamp: " + f"{cap_mono:.6f}".encode('ascii') + b"\r\n"
                   b"X-Server-Send-Timestamp: " + f"{send_mono:.6f}".encode('ascii') + b"\r\n"
                   b"X-Acquisition-Ms: " + f"{acq_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Handoff-Ms: " + f"{inf_handoff_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Preprocess-Ms: " + f"{preprocess_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Inference-Ms: " + f"{inference_only_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Tracking-Ms: " + f"{tracking_only_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Encode-Ms: " + f"{encode_ms:.3f}".encode('ascii') + b"\r\n"
                   b"X-Frame-ID: " + str(current_id).encode('ascii') + b"\r\n"
                   b"X-Inference-Age: " + f"{inference_age_ms:.1f}".encode('ascii') + b"\r\n"
                   b"X-Inference-Frame-ID: " + str(inf_source_fid).encode('ascii') + b"\r\n\r\n" +
                   jpeg_bytes + b"\r\n")

    except (GeneratorExit, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        logger.info(f"[TRACKING_STREAM_CLIENT_DISCONNECTED] camera_id={camera_id}")
    except Exception as e:
        logger.error(f"[TRACKING_STREAM_ERROR] camera_id={camera_id}: {e}")
        update_camera_health(camera_id, status="offline", last_error=str(e))
    finally:
        if inference_worker is not None:
            try:
                inference_registry.release_worker(camera_id)
            except Exception as e:
                logger.warning(f"[INFERENCE_CLEANUP_WARN] {e}")
        if worker is not None:
            try:
                camera_registry.release_worker(camera_id)
            except Exception as e:
                logger.warning(f"[CAMERA_CLEANUP_WARN] {e}")
        update_camera_health(camera_id, delta_stream_count=-1)
