"""
Native Django Surveillance Streaming Service.
Directly generates MJPEG streams for ORIGINAL and TRACKING+DETECTION modes
using shared singleton CameraWorker and InferenceWorker without Flask.
"""

import time
import cv2
import logging
from typing import Generator, Dict, Any, List

from apps.surveillance.camera.registry import get_camera_registry
from apps.surveillance.ai.registry import get_inference_registry
from apps.surveillance.recording import recording_service
from apps.surveillance.health.health_service import update_camera_health
from apps.surveillance.ai.reid import registry as reid_registry

logger = logging.getLogger(__name__)

_JPEG_STREAM_QUALITY = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
_stream_telemetry: Dict[int, Dict[str, Any]] = {}


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

        while True:
            if not worker.running:
                break

            with worker.lock:
                current_id = worker.frame_id
                frame = worker.latest_frame.copy() if worker.latest_frame is not None else None
                fps = worker.fps

            if current_id == last_processed_id or frame is None:
                if frame is None and (time.time() - start_no_frame_time > 10.0):
                    logger.warning(f"[RAW_STREAM] Camera {camera_id}: No frame received within 10s timeout.")
                    break
                time.sleep(0.01)
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

            ret, buffer = cv2.imencode(".jpg", frame, _JPEG_STREAM_QUALITY)
            if not ret:
                continue

            jpeg_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg_bytes)).encode('ascii') + b"\r\n\r\n" +
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

        cached_active_persons = []
        cached_active_items = []

        while True:
            if not worker.running:
                break

            with worker.lock:
                current_id = worker.frame_id
                frame = worker.latest_frame.copy() if worker.latest_frame is not None else None
                cam_fps = worker.fps

            if current_id == last_processed_id or frame is None:
                if frame is None and (time.time() - start_no_frame_time > 10.0):
                    logger.warning(f"[TRACKING_STREAM] Camera {camera_id}: No frame received within 10s timeout.")
                    break
                time.sleep(0.005)
                continue

            start_no_frame_time = time.time()
            last_processed_id = current_id
            now = time.time()

            display_frame = frame.copy()

            # Read cached inference results (non-blocking)
            _, cached_tracks, latency_ms, ai_fps, inference_id, _ = inference_worker.get_cached_result()

            # Reprocess tracks if a new inference result is available
            if inference_id != last_inference_id and cached_tracks is not None:
                last_inference_id = inference_id
                active_persons = []
                active_items = []

                for track in cached_tracks:
                    tx1, ty1, tx2, ty2 = track["x1"], track["y1"], track["x2"], track["y2"]
                    tcx = (tx1 + tx2) / 2.0
                    tcy = (ty1 + ty2) / 2.0

                    if track["class_name"] == "person":
                        cropped = frame[ty1:ty2, tx1:tx2] if (tx2 > tx1 and ty2 > ty1) else None
                        g_id, r_status, cert = reid_registry.resolve_person(camera_id, track["track_id"], cropped, now)
                        active_persons.append({
                            "track_id": track["track_id"],
                            "confidence": track.get("confidence", 1.0),
                            "global_id": g_id,
                            "bbox": [tx1, ty1, tx2, ty2],
                            "center": (tcx, tcy),
                            "reid_status": r_status,
                        })
                    elif track["class_name"] in ["backpack", "handbag", "suitcase", "bottle", "cup", "cell phone", "laptop"]:
                        g_id, cert = reid_registry.resolve_item(camera_id, track["track_id"], track["class_name"], now)
                        active_items.append({
                            "track_id": track["track_id"],
                            "global_id": g_id,
                            "bbox": [tx1, ty1, tx2, ty2],
                            "center": (tcx, tcy),
                            "class_name": track["class_name"],
                            "confidence": track["confidence"],
                            "certainty": cert,
                        })

                cached_active_persons = active_persons
                cached_active_items = active_items
            else:
                active_persons = cached_active_persons
                active_items = cached_active_items

            # Display FPS telemetry
            disp_frame_times.append(now)
            if len(disp_frame_times) > 15:
                disp_frame_times.pop(0)
            if len(disp_frame_times) >= 2:
                elapsed = disp_frame_times[-1] - disp_frame_times[0]
                if elapsed > 0:
                    display_fps = round((len(disp_frame_times) - 1) / elapsed, 1)
                    update_camera_health(
                        camera_id,
                        fps=display_fps,
                        ai_fps=ai_fps,
                        inference_latency_ms=latency_ms
                    )

            # Draw visual overlays
            # 1. Persons (Green)
            for p in active_persons:
                tx1, ty1, tx2, ty2 = p["bbox"]
                tid = p.get("track_id", "")
                gid = p.get("global_id", "")
                tconf = p.get("confidence", 1.0)
                cv2.rectangle(display_frame, (tx1, ty1), (tx2, ty2), (0, 255, 0), 2)
                label = f"person #{tid} {tconf:.2f} ({gid})" if gid else f"person #{tid} {tconf:.2f}"
                cv2.putText(display_frame, label, (tx1, max(18, ty1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # 2. Items (Orange)
            for item in active_items:
                tx1, ty1, tx2, ty2 = item["bbox"]
                color = (0, 165, 255)
                cv2.rectangle(display_frame, (tx1, ty1), (tx2, ty2), color, 2)
                lbl1 = f"{item['global_id']}"
                lbl2 = f"{item['class_name'].upper()} {item['confidence']:.2f}"
                cv2.putText(display_frame, lbl1, (tx1, max(15, ty1 - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                cv2.putText(display_frame, lbl2, (tx1, max(15, ty1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # 3. Other ByteTrack Objects (Gold)
            drawn_boxes = [p["bbox"] for p in active_persons] + [item["bbox"] for item in active_items]
            ui_tracks = []
            for trk in (cached_tracks or []):
                tx1, ty1, tx2, ty2 = trk["x1"], trk["y1"], trk["x2"], trk["y2"]
                if not any(abs(tx1 - bx[0]) < 15 and abs(ty1 - bx[1]) < 15 for bx in drawn_boxes):
                    track_color = (0, 215, 255)
                    cv2.rectangle(display_frame, (tx1, ty1), (tx2, ty2), track_color, 2)
                    lbl = f"#{trk['track_id']} {trk['class_name']} {trk['confidence']:.2f}"
                    cv2.putText(display_frame, lbl, (tx1, max(15, ty1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, track_color, 2)
                ui_tracks.append({
                    "track_id": f"#{trk['track_id']}",
                    "class_name": trk["class_name"].capitalize(),
                    "confidence": trk["confidence"],
                    "behavior": "Tracking Active",
                    "direction": "ByteTrack"
                })

            _stream_telemetry[camera_id] = {
                "camera_id": camera_id,
                "tracks": ui_tracks,
                "anomalies": getattr(inference_worker, "cached_anomalies", []),
                "fps": getattr(inference_worker, "ai_fps", 0.0),
                "status": "active"
            }

            ret, buffer = cv2.imencode(".jpg", display_frame, _JPEG_STREAM_QUALITY)
            if not ret:
                continue

            jpeg_bytes = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg_bytes)).encode('ascii') + b"\r\n\r\n" +
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
