"""
Native Django Surveillance Streaming Service.
Directly generates MJPEG streams for ORIGINAL and TRACKING+DETECTION modes
using shared singleton CameraWorker and InferenceWorker without Flask.
"""

import time
try:
    import cv2
    import numpy as np
    _JPEG_STREAM_QUALITY = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
except (ImportError, Exception):
    cv2 = None
    np = None
    _JPEG_STREAM_QUALITY = [1, 85]
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


def _to_pixel_coords(x1: float, y1: float, x2: float, y2: float, fw: int, fh: int):
    """Safely converts coordinates (normalized or pixel) to valid frame bounds."""
    if max(x1, x2) <= 1.0 and max(y1, y2) <= 1.0:
        return int(x1 * fw), int(y1 * fh), int(x2 * fw), int(y2 * fh)
    return max(0, min(fw, int(x1))), max(0, min(fh, int(y1))), max(0, min(fw, int(x2))), max(0, min(fh, int(y2)))


def _point_in_zone(px: float, py: float, z: dict, fw: int, fh: int) -> bool:
    """Checks whether a center point (px, py) falls inside a restricted zone."""
    zx1, zy1, zx2, zy2 = _to_pixel_coords(z["x1"], z["y1"], z["x2"], z["y2"], fw, fh)
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


def generate_raw_stream(camera_id: int, user_id: int) -> Generator[bytes, None, None]:
    """
    Generator for ORIGINAL CCTV raw video stream (no AI overlays).
    """
    camera_registry = get_camera_registry()
    worker = None
    last_processed_id = -1
    disp_frame_times: List[float] = []
    start_no_frame_time = time.time()

    update_camera_health(camera_id, delta_stream_count=1)

    try:
        worker = camera_registry.get_worker(camera_id, user_id)
        update_camera_health(camera_id, status="online", stream_active=True, detection_active=False, tracking_active=False)
        cond = getattr(worker, "frame_condition", None)

        while True:
            if not worker.running:
                break

            if cond is not None:
                with cond:
                    while worker.running and worker.frame_id == last_processed_id:
                        if not cond.wait(timeout=0.08):
                            break
                    if not worker.running:
                        break
                    current_id = worker.frame_id
                    frame = worker.latest_frame.copy() if worker.latest_frame is not None else None
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())
            else:
                with worker.lock:
                    current_id = worker.frame_id
                    frame = worker.latest_frame.copy() if (worker.latest_frame is not None and current_id != last_processed_id) else None
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())

            if current_id == last_processed_id or frame is None:
                if frame is None and (time.time() - start_no_frame_time > 10.0):
                    logger.warning(f"[RAW_STREAM] Camera {camera_id}: No frame received within 10s timeout.")
                    break
                time.sleep(0.003)
                continue

            start_no_frame_time = time.time()
            last_processed_id = current_id

            now = time.time()
            disp_frame_times.append(now)
            if len(disp_frame_times) > 15:
                disp_frame_times.pop(0)
            if len(disp_frame_times) >= 2:
                elapsed = disp_frame_times[-1] - disp_frame_times[0]
                if elapsed > 0:
                    display_fps = round((len(disp_frame_times) - 1) / elapsed, 1)
                    update_camera_health(camera_id, fps=display_fps)

            cap_handoff_ms = max(0.0, (time.monotonic() - cap_mono) * 1000.0) if cap_mono > 0 else 0.0
            acq_ms = float(getattr(worker, "last_acquisition_ms", 0.0) or 0.0)
            t_enc0 = time.monotonic()
            ret, buffer = cv2.imencode(".jpg", frame, _JPEG_STREAM_QUALITY)
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


def generate_tracking_stream(camera_id: int, user_id: int) -> Generator[bytes, None, None]:
    """
    Generator for TRACKING + DETECTION stream (YOLO11n + ByteTrack overlays).
    """
    camera_registry = get_camera_registry()
    inference_registry = get_inference_registry()
    worker = None
    inference_worker = None
    last_processed_id = -1
    last_inference_id = -1
    disp_frame_times: List[float] = []
    start_no_frame_time = time.time()

    update_camera_health(camera_id, delta_stream_count=1)

    try:
        worker = camera_registry.get_worker(camera_id, user_id)
        inference_worker = inference_registry.get_worker(camera_id, worker)
        update_camera_health(camera_id, status="online", stream_active=True, detection_active=True, tracking_active=True)
        cond = getattr(worker, "frame_condition", None)

        while True:
            if not worker.running:
                break

            if cond is not None:
                with cond:
                    while worker.running and worker.frame_id == last_processed_id:
                        if not cond.wait(timeout=0.08):
                            break
                    if not worker.running:
                        break
                    current_id = worker.frame_id
                    frame = worker.latest_frame.copy() if worker.latest_frame is not None else None
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())
            else:
                with worker.lock:
                    current_id = worker.frame_id
                    frame = worker.latest_frame.copy() if (worker.latest_frame is not None and current_id != last_processed_id) else None
                    cap_mono = getattr(worker, "last_capture_monotonic", time.monotonic())

            if current_id == last_processed_id or frame is None:
                if frame is None and (time.time() - start_no_frame_time > 10.0):
                    logger.warning(f"[TRACKING_STREAM] Camera {camera_id}: No frame received within 10s timeout.")
                    break
                time.sleep(0.003)
                continue

            start_no_frame_time = time.time()
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

            # Read cached inference results (non-blocking)
            inf_res = inference_worker.get_cached_result()
            cached_tracks = inf_res[1]
            latency_ms = inf_res[2]
            ai_fps = inf_res[3]
            inference_id = inf_res[4]
            inf_source_fid = inf_res[5] if len(inf_res) > 5 else 0
            active_persons = inf_res[6] if len(inf_res) > 6 else []
            active_items = inf_res[7] if len(inf_res) > 7 else []
            inf_comp_time = inf_res[8] if len(inf_res) > 8 else 0.0

            now_mono = time.monotonic()
            stream_handoff_ms = max(0.0, (now_mono - cap_mono) * 1000.0) if cap_mono > 0 else 0.0
            acq_ms = float(getattr(worker, "last_acquisition_ms", 0.0) or 0.0)
            stage_timings = getattr(inference_worker, "last_stage_timings", None) or {}
            inf_handoff_ms = float(getattr(inference_worker, "last_handoff_ms", stream_handoff_ms) or stream_handoff_ms)
            preprocess_ms = float(stage_timings.get("preprocess_ms", 0.0) or 0.0)
            inference_only_ms = float(stage_timings.get("inference_ms", 0.0) or 0.0)
            tracking_only_ms = float(stage_timings.get("tracking_ms", 0.0) or 0.0)

            inference_age_ms = max(0.0, (now_mono - inf_comp_time) * 1000.0) if inf_comp_time > 0 else 0.0
            is_stale_detection = (current_id - inf_source_fid > 15) if (inf_source_fid and current_id) else False
            hide_boxes = (inference_age_ms > 1500.0 and inf_comp_time > 0)

            if display_fps > 0:
                update_camera_health(camera_id, fps=display_fps, ai_fps=ai_fps, inference_latency_ms=latency_ms)

            # Retrieve active restricted zones scoped specifically to this logical camera (deduplicated visually)
            raw_zones = inference_worker.get_cached_zones(camera_id) if hasattr(inference_worker, "get_cached_zones") else []
            seen_coords = set()
            cached_zones = []
            for z in raw_zones:
                coord_key = (int(z.get("x1", 0)), int(z.get("y1", 0)), int(z.get("x2", 0)), int(z.get("y2", 0)))
                if coord_key not in seen_coords:
                    seen_coords.add(coord_key)
                    cached_zones.append(z)
            fh, fw = frame.shape[:2]

            # Detect which zones currently have any active person center inside
            active_intrusions = set()
            if not hide_boxes:
                for p in active_persons:
                    pcx, pcy = p.get("center", (0, 0))
                    for z in cached_zones:
                        if z.get("enabled", True) and _point_in_zone(pcx, pcy, z, fw, fh):
                            active_intrusions.add(z["id"])

            # 1. Draw Restricted Zones (monitored boundaries)
            for z in cached_zones:
                if not z.get("enabled", True):
                    continue
                zx1, zy1, zx2, zy2 = _to_pixel_coords(z["x1"], z["y1"], z["x2"], z["y2"], fw, fh)
                zid = z["id"]
                zname = z.get("name", "Restricted Area")
                is_intruded = zid in active_intrusions

                if is_intruded:
                    z_color = (0, 0, 235)  # Alert Red
                    # Subtle semi-transparent red alert tint inside zone
                    sub = frame[zy1:zy2, zx1:zx2]
                    if sub.shape[0] > 0 and sub.shape[1] > 0 and np is not None:
                        red_layer = np.full_like(sub, (0, 0, 180), dtype=np.uint8)
                        cv2.addWeighted(sub, 0.78, red_layer, 0.22, 0, sub)
                        frame[zy1:zy2, zx1:zx2] = sub
                    cv2.rectangle(frame, (zx1, zy1), (zx2, zy2), z_color, 3)
                    zlabel = f"[!] INTRUSION DETECTED: {zname.upper()}"
                    cv2.putText(frame, zlabel, (zx1 + 10, max(24, zy1 + 24)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
                else:
                    z_color = (0, 165, 255)  # Amber
                    cv2.rectangle(frame, (zx1, zy1), (zx2, zy2), z_color, 2)
                    zlabel = f"ZONE: {zname}"
                    cv2.putText(frame, zlabel, (zx1 + 8, max(20, zy1 + 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, z_color, 2)

            ui_tracks = []
            if not hide_boxes:
                # 2. Persons (Green or Red if inside restricted zone)
                for p in active_persons:
                    tx1, ty1, tx2, ty2 = p["bbox"]
                    tid = p.get("track_id", "")
                    gid = p.get("global_id", "")
                    tconf = p.get("confidence", 1.0)
                    pcx, pcy = p.get("center", ((tx1 + tx2) / 2.0, (ty1 + ty2) / 2.0))
                    in_zone = any(_point_in_zone(pcx, pcy, z, fw, fh) for z in cached_zones if z.get("enabled", True))
                    if in_zone:
                        box_color = (0, 0, 235)  # Alert Red
                        label = f"ALERT PERSON #{tid} (INTRUDER) {tconf:.2f}"
                    else:
                        box_color = (0, 200, 100) if not is_stale_detection else (0, 180, 180)
                        label = f"person #{tid} {tconf:.2f} ({gid})" if gid else f"person #{tid} {tconf:.2f}"
                    cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), box_color, 2)
                    cv2.putText(frame, label, (tx1, max(18, ty1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

                # 3. Items (Orange)
                for item in active_items:
                    tx1, ty1, tx2, ty2 = item["bbox"]
                    color = (0, 165, 255)
                    cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), color, 2)
                    lbl1 = f"{item.get('global_id','')}"
                    lbl2 = f"{item['class_name'].upper()} {item.get('confidence', 1.0):.2f}"
                    cv2.putText(frame, lbl1, (tx1, max(15, ty1 - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                    cv2.putText(frame, lbl2, (tx1, max(15, ty1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                # 4. Other ByteTrack Objects (Gold)
                drawn_boxes = [p["bbox"] for p in active_persons] + [item["bbox"] for item in active_items]
                for trk in (cached_tracks or []):
                    tx1, ty1, tx2, ty2 = trk["x1"], trk["y1"], trk["x2"], trk["y2"]
                    if not any(abs(tx1 - bx[0]) < 15 and abs(ty1 - bx[1]) < 15 for bx in drawn_boxes):
                        track_color = (0, 215, 255)
                        cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), track_color, 2)
                        lbl = f"#{trk['track_id']} {trk['class_name']} {trk['confidence']:.2f}"
                        cv2.putText(frame, lbl, (tx1, max(15, ty1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, track_color, 2)
                    ui_tracks.append({
                        "track_id": f"#{trk['track_id']}",
                        "class_name": trk["class_name"].capitalize(),
                        "confidence": trk["confidence"],
                        "bbox": [int(trk["x1"]), int(trk["y1"]), int(trk["x2"]), int(trk["y2"])],
                        "behavior": trk.get("behavior") or "normal",
                        "direction": trk.get("direction") or "stationary",
                        "speed": round(float(trk.get("speed", 0.0) or 0.0), 1),
                    })

            t_enc0 = time.monotonic()
            ret, buffer = cv2.imencode(".jpg", frame, _JPEG_STREAM_QUALITY)
            encode_ms = (time.monotonic() - t_enc0) * 1000.0
            if not ret:
                continue

            _stream_telemetry[camera_id] = {
                "camera_id": camera_id,
                "tracks": ui_tracks,
                "anomalies": getattr(inference_worker, "cached_anomalies", []),
                "zones": cached_zones,
                "active_intrusions": list(active_intrusions),
                "fps": display_fps if display_fps > 0 else (getattr(inference_worker, "ai_fps", 0.0) or (worker.fps if worker else 0.0)),
                "ai_fps": getattr(inference_worker, "ai_fps", 0.0),
                "latency_ms": latency_ms,
                "stage_timings": {
                    "acquisition_ms": round(acq_ms, 2),
                    "handoff_ms": round(inf_handoff_ms, 2),
                    "stream_handoff_ms": round(stream_handoff_ms, 2),
                    "preprocess_ms": round(preprocess_ms, 2),
                    "inference_ms": round(inference_only_ms, 2),
                    "tracking_ms": round(tracking_only_ms, 2),
                    "encode_ms": round(encode_ms, 2),
                },
                "inference_age_ms": round(inference_age_ms, 1),
                "is_stale_detection": is_stale_detection,
                "status": "active"
            }

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
