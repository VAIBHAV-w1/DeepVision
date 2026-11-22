"""
Multi-Object Tracker for DeepVision 4.0 Surveillance Architecture.

Runs the verified shared YOLO26s ONNX engine (OpenVINO GPU/CPU -> ONNX Runtime CPU
-> OpenCV DNN CPU) paired with Genuine BoT-SORT + Re-ID (selected primary tracker)
or configurable ByteTrack / OC-SORT.
Falls back to hardened human-cue-only OpenCV structural tracking ONLY when no
neural detector runtime or verified weights are available.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import torch
except (ImportError, Exception):
    torch = None

from apps.surveillance.ai.detector import CLASS_CONFIDENCE_GATES
from apps.surveillance.ai.model_loader import (
    create_camera_model_wrapper,
    get_inference_lock,
)
from apps.surveillance.ai.trackers.botsort_core import GenuineBotSortTracker
from apps.surveillance.ai.trackers.bytetrack_core import GenuineByteTracker
from apps.surveillance.ai.trackers.ocsort_core import GenuineOCSortTracker


def _bbox_iou(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ix1 = max(a["x1"], b["x1"])
    iy1 = max(a["y1"], b["y1"])
    ix2 = min(a["x2"], b["x2"])
    iy2 = min(a["y2"], b["y2"])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (a["x2"] - a["x1"]) * (a["y2"] - a["y1"]))
    area_b = max(1, (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]))
    return inter / float(area_a + area_b - inter)


def _bbox_iomin(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ix1 = max(a["x1"], b["x1"])
    iy1 = max(a["y1"], b["y1"])
    ix2 = min(a["x2"], b["x2"])
    iy2 = min(a["y2"], b["y2"])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (a["x2"] - a["x1"]) * (a["y2"] - a["y1"]))
    area_b = max(1, (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]))
    return inter / float(min(area_a, area_b))


def _resolve_tracker_algorithm() -> str:
    algo = (os.getenv("DEEPVISION_TRACKER_ALGORITHM") or "botsort_reid").strip().lower()
    if algo in ("bytetrack", "byte"):
        return "bytetrack"
    if algo in ("ocsort", "oc-sort"):
        return "ocsort"
    return "botsort_reid"


def _build_native_tracker(algorithm: str, high_thresh: float = 0.45):
    low_thresh = 0.15
    if algorithm == "bytetrack":
        return GenuineByteTracker(
            track_high_thresh=high_thresh,
            track_low_thresh=low_thresh,
            new_track_thresh=high_thresh,
            track_buffer=75,
            match_thresh=0.80,
            fuse_score=True,
        )
    if algorithm == "ocsort":
        return GenuineOCSortTracker(
            track_high_thresh=high_thresh,
            track_low_thresh=low_thresh,
            new_track_thresh=high_thresh,
            track_buffer=75,
            match_thresh=0.80,
            inertia=0.20,
            delta_t=3,
        )
    return GenuineBotSortTracker(
        track_high_thresh=high_thresh,
        track_low_thresh=low_thresh,
        new_track_thresh=high_thresh,
        track_buffer=75,
        match_thresh=0.80,
        proximity_thresh=0.50,
        appearance_thresh=0.25,
        with_reid=True,
        use_gmc=True,
    )


class ByteTrackTracker:
    """
    Per-camera multi-object detector & tracker controller.
    Preserves the public class interface while powering ONNX/OpenVINO YOLO26s + BoT-SORT Re-ID.
    """

    def __init__(self, confidence_threshold: float = 0.45, imgsz: int = 640, lazy_init: bool = False):
        self.confidence_threshold = float(confidence_threshold)
        self.imgsz = int(imgsz)
        self.tracker_yaml = os.path.abspath(os.path.join(os.path.dirname(__file__), "bytetrack.yaml"))
        if not os.path.exists(self.tracker_yaml):
            self.tracker_yaml = "bytetrack.yaml"

        self.phone_class_id = 67
        self._init_lock = threading.Lock()
        self._model_initialized = False
        self.model = None
        self._tracker_algo = _resolve_tracker_algorithm()
        self._native_tracker = _build_native_tracker(self._tracker_algo, high_thresh=max(0.35, self.confidence_threshold))

        self.last_detections: List[Dict[str, Any]] = []
        self.last_stage_timings: Dict[str, float] = {
            "preprocess_ms": 0.0,
            "inference_ms": 0.0,
            "tracking_ms": 0.0,
            "total_ms": 0.0,
        }

        # Emergency OpenCV structural fallback state (only used if zero ONNX/PyTorch model is available)
        self._cv_haar_face = None
        self._cv_hog_person = None
        self._cv_tracks: Dict[int, Dict[str, Any]] = {}
        self._cv_lost_tracks: Dict[int, Dict[str, Any]] = {}
        self._cv_frame_idx = 0
        self._cv_next_track_id = 1

        if not lazy_init:
            self.ensure_model_loaded()

    @property
    def detector_backend(self) -> str:
        if not self._model_initialized:
            return "initializing"
        if self.model is not None:
            if hasattr(self.model, "backend_id"):
                return str(self.model.backend_id)
            if torch is not None:
                return "yolo11n"
        return "opencv_fallback"

    @property
    def tracker_backend(self) -> str:
        if not self._model_initialized:
            return "initializing"
        if self.model is not None:
            if hasattr(self.model, "infer"):
                return self._tracker_algo
            if torch is not None:
                return "bytetrack"
        return "iou_motion_fallback"

    def ensure_model_loaded(self):
        if self._model_initialized:
            return self.model
        with self._init_lock:
            if self._model_initialized:
                return self.model
            try:
                self.model = create_camera_model_wrapper()
                if hasattr(self.model, "names") and self.model and self.model.names:
                    for cid, name in self.model.names.items():
                        if name == "cell phone":
                            self.phone_class_id = int(cid)
                            break
            finally:
                self._model_initialized = True
        return self.model

    def reset_tracker_state(self):
        """Resets transient tracker pools without unloading shared compiled ONNX weights."""
        if self._native_tracker is not None:
            self._native_tracker.reset()
        self._cv_tracks.clear()
        self._cv_lost_tracks.clear()
        self._cv_frame_idx = 0
        self._cv_next_track_id = 1
        self.last_detections = []

    def unload_model(self):
        """Releases per-camera model wrapper reference and resets all tracker buffers."""
        with self._init_lock:
            self.model = None
            self._model_initialized = False
            self.reset_tracker_state()

    def reload_model(self):
        self.unload_model()
        return self.ensure_model_loaded()

    @staticmethod
    def _normalize_valid_bgr_frame(frame):
        if frame is None or not hasattr(frame, "shape") or not hasattr(frame, "size"):
            return None
        try:
            shape = getattr(frame, "shape", ())
            if not shape or len(shape) not in (2, 3) or int(getattr(frame, "size", 0)) <= 0:
                return None
            h, w = int(shape[0]), int(shape[1])
            if h < 2 or w < 2:
                return None
            import cv2
            import numpy as np
            arr = np.asarray(frame)
            if not np.issubdtype(arr.dtype, np.number):
                return None
            if np.issubdtype(arr.dtype, np.floating):
                if not np.isfinite(arr).all():
                    return None
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            elif arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            if len(arr.shape) == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            elif arr.shape[2] == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            elif arr.shape[2] != 3:
                return None
            return np.ascontiguousarray(arr)
        except Exception:
            return None

    @staticmethod
    def _compute_roi_hist(cv2_mod, frame, x1, y1, x2, y2):
        try:
            roi = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
            if roi is None or roi.size == 0:
                return None
            hsv = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2HSV)
            hist = cv2_mod.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
            cv2_mod.normalize(hist, hist, 0, 1, cv2_mod.NORM_MINMAX)
            return hist
        except Exception:
            return None

    def _track_onnx(self, frame, base_conf: float) -> List[Dict[str, Any]]:
        """Runs YOLO26 ONNX inference + genuine BoT-SORT / ByteTrack / OC-SORT tracking."""
        t0 = time.perf_counter()
        raw_dets, inf_timings = self.model.infer(frame, conf_floor=0.15)
        t_inf_done = time.perf_counter()

        # Pass hysteresis floor for tracker association, then enforce calibrated gates on emitted outputs
        tracker_inputs: List[Dict[str, Any]] = []
        filtered_dets: List[Dict[str, Any]] = []
        for det in raw_dets:
            cid = int(det["class_id"])
            conf = float(det["confidence"])
            if 14 <= cid <= 23 and conf < 0.55:
                continue
            tracker_gate = 0.22 if cid == 0 else CLASS_CONFIDENCE_GATES.get(cid, max(0.25, base_conf))
            if conf >= min(0.18 if cid == 0 else tracker_gate, tracker_gate):
                tracker_inputs.append(det)
            if conf >= CLASS_CONFIDENCE_GATES.get(cid, max(base_conf, 0.35)):
                filtered_dets.append(det)

        raw_tracked = self._native_tracker.update(tracker_inputs, frame=frame)
        # Filter emitted tracks cleanly by class-calibrated threshold (with active hysteresis down to 0.28 for person)
        gated_tracked = []
        for trk in raw_tracked:
            cid = int(trk["class_id"])
            conf = float(trk["confidence"])
            min_req = 0.28 if cid == 0 else CLASS_CONFIDENCE_GATES.get(cid, max(base_conf, 0.30))
            if conf >= min_req:
                gated_tracked.append(trk)

        # Class-aware duplicate suppression (IoU >= 0.55; preserves people overlapping in depth!)
        gated_tracked.sort(key=lambda t: (t["track_id"], -t["confidence"]))
        tracked_objects: List[Dict[str, Any]] = []
        for cand in gated_tracked:
            dup = False
            for kept in tracked_objects:
                if kept["class_id"] == cand["class_id"] and _bbox_iou(kept, cand) >= 0.55:
                    dup = True
                    break
            if not dup:
                tracked_objects.append(cand)

        t_end = time.perf_counter()
        self.last_stage_timings = {
            "preprocess_ms": inf_timings.get("preprocess_ms", 0.0),
            "inference_ms": inf_timings.get("inference_ms", round((t_inf_done - t0) * 1000.0, 3)),
            "tracking_ms": round((t_end - t_inf_done) * 1000.0, 3),
            "total_ms": round((t_end - t0) * 1000.0, 3),
        }
        self.last_detections = filtered_dets
        return tracked_objects

    def _track_opencv_fallback(self, frame, base_conf: float = 0.45):
        """
        Hardened OpenCV human-cue structural fallback (used ONLY when no ONNX/PyTorch neural model exists).
        - Requires verified human cue (Haar face or HOG person); bare motion contours never emit person boxes.
        - Enforces IoU + IoMin containment suppression and zero persistence self-injection.
        """
        try:
            import cv2
            t0 = time.perf_counter()
            now_ts = time.time()
            self._cv_frame_idx += 1
            fh, fw = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        except Exception:
            self.last_detections = []
            return []

        candidates: List[Dict[str, Any]] = []

        try:
            if self._cv_haar_face is None and hasattr(cv2, "data"):
                face_xml = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                if os.path.exists(face_xml):
                    self._cv_haar_face = cv2.CascadeClassifier(face_xml)
            if self._cv_haar_face is not None and not self._cv_haar_face.empty():
                faces = self._cv_haar_face.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(36, 36))
                for (fx, fy, fw_box, fh_box) in faces:
                    candidates.append({
                        "class_id": 0,
                        "class_name": "person",
                        "confidence": 0.89,
                        "x1": max(0, int(fx - fw_box * 0.45)),
                        "y1": max(0, int(fy - fh_box * 0.20)),
                        "x2": min(fw, int(fx + fw_box * 1.45)),
                        "y2": min(fh, int(fy + fh_box * 2.60)),
                        "human_cue": True,
                        "source": "haar_face",
                    })
        except Exception:
            pass

        try:
            if fw >= 120 and fh >= 128:
                if self._cv_hog_person is None:
                    hog = cv2.HOGDescriptor()
                    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                    self._cv_hog_person = hog
                hog_scale = min(1.0, 320.0 / float(fw))
                hog_w = max(64, int(round(fw * hog_scale)))
                hog_h = max(128, int(round(fh * hog_scale)))
                if hog_w >= 64 and hog_h >= 128:
                    hog_frame = gray if hog_scale >= 0.99 else cv2.resize(gray, (hog_w, hog_h), interpolation=cv2.INTER_AREA)
                    rects, weights = self._cv_hog_person.detectMultiScale(hog_frame, winStride=(8, 8), padding=(4, 4), scale=1.08)
                    inv_scale = 1.0 / hog_scale
                    for idx, (rx, ry, rw, rh) in enumerate(rects):
                        w_val = float(weights[idx]) if weights is not None and len(weights) > idx else 0.7
                        if w_val < 0.70:
                            continue
                        px1 = max(0, int(round(rx * inv_scale)))
                        py1 = max(0, int(round(ry * inv_scale)))
                        px2 = min(fw, int(round((rx + rw) * inv_scale)))
                        py2 = min(fh, int(round((ry + rh) * inv_scale)))
                        if (px2 - px1) < 24 or (py2 - py1) < 60:
                            continue
                        conf = round(min(0.90, max(0.58, 0.50 + 0.25 * min(1.6, w_val))), 2)
                        if conf >= base_conf:
                            candidates.append({
                                "class_id": 0,
                                "class_name": "person",
                                "confidence": conf,
                                "x1": px1,
                                "y1": py1,
                                "x2": px2,
                                "y2": py2,
                                "human_cue": True,
                                "source": "hog_person",
                            })
        except Exception:
            pass

        candidates.sort(key=lambda c: (c["confidence"], (c["x2"] - c["x1"]) * (c["y2"] - c["y1"])), reverse=True)
        filtered_dets: List[Dict[str, Any]] = []
        for cand in candidates[:8]:
            if any(_bbox_iou(cand, kept) >= 0.45 or _bbox_iomin(cand, kept) >= 0.60 for kept in filtered_dets):
                continue
            filtered_dets.append(cand)

        for det in filtered_dets:
            det["_hist"] = self._compute_roi_hist(cv2, frame, det["x1"], det["y1"], det["x2"], det["y2"])

        t_inf = time.perf_counter()
        diag = max(1.0, (fw ** 2 + fh ** 2) ** 0.5)
        pairs = []
        for d_idx, det in enumerate(filtered_dets):
            dcx, dcy = 0.5 * (det["x1"] + det["x2"]), 0.5 * (det["y1"] + det["y2"])
            for tid, trk in self._cv_tracks.items():
                if trk.get("class_id") != det.get("class_id"):
                    continue
                px = 0.5 * (trk["x1"] + trk["x2"]) + trk.get("vx", 0.0)
                py = 0.5 * (trk["y1"] + trk["y2"]) + trk.get("vy", 0.0)
                iou = _bbox_iou(det, trk)
                dist_norm = (((dcx - px) ** 2 + (dcy - py) ** 2) ** 0.5) / diag
                if iou < 0.10 and dist_norm > 0.16:
                    continue
                app_sim = 0.0
                if det.get("_hist") is not None and trk.get("hist") is not None:
                    try:
                        app_sim = max(0.0, min(1.0, float(cv2.compareHist(det["_hist"], trk["hist"], cv2.HISTCMP_CORREL))))
                    except Exception:
                        app_sim = 0.0
                pairs.append((iou * 1.4 + max(0.0, 0.35 - dist_norm) + app_sim * 0.45, d_idx, tid))

        pairs.sort(reverse=True)
        matched_tids, used_dets = set(), set()
        for _, d_idx, tid in pairs:
            if d_idx in used_dets or tid in matched_tids:
                continue
            used_dets.add(d_idx)
            matched_tids.add(tid)
            det = filtered_dets[d_idx]
            prev = self._cv_tracks[tid]
            prev.update({k: v for k, v in det.items() if k != "_hist"})
            if det.get("_hist") is not None:
                prev["hist"] = det["_hist"]
            prev["missed"] = 0
            prev["hits"] = prev.get("hits", 1) + 1
            if prev["hits"] >= 2 or det.get("human_cue"):
                prev["confirmed"] = True

        for d_idx, det in enumerate(filtered_dets):
            if d_idx in used_dets:
                continue
            new_tid = self._cv_next_track_id
            self._cv_next_track_id += 1
            self._cv_tracks[new_tid] = {
                **{k: v for k, v in det.items() if k != "_hist"},
                "track_id": new_tid,
                "vx": 0.0,
                "vy": 0.0,
                "missed": 0,
                "hits": 1,
                "confirmed": bool(det.get("human_cue") and det["confidence"] >= 0.80),
                "hist": det.get("_hist"),
            }
            matched_tids.add(new_tid)

        for tid in list(self._cv_tracks.keys()):
            if tid in matched_tids:
                continue
            trk = self._cv_tracks[tid]
            trk["missed"] = trk.get("missed", 0) + 1
            if trk["missed"] > (8 if trk.get("confirmed") else 2):
                self._cv_tracks.pop(tid, None)

        tracked_objects = [
            {
                "class_id": trk["class_id"],
                "class_name": trk["class_name"],
                "confidence": trk["confidence"],
                "x1": trk["x1"],
                "y1": trk["y1"],
                "x2": trk["x2"],
                "y2": trk["y2"],
                "track_id": tid,
                "confirmed": True,
                "hits": trk.get("hits", 1),
            }
            for tid, trk in sorted(self._cv_tracks.items())
            if trk.get("confirmed") and trk.get("missed", 0) <= 2
        ]

        t_end = time.perf_counter()
        self.last_stage_timings = {
            "preprocess_ms": round((t_inf - t0) * 250.0, 3),
            "inference_ms": round((t_inf - t0) * 750.0, 3),
            "tracking_ms": round((t_end - t_inf) * 1000.0, 3),
            "total_ms": round((t_end - t0) * 1000.0, 3),
        }
        self.last_detections = [{k: v for k, v in d.items() if k != "_hist"} for d in filtered_dets]
        return tracked_objects

    def track(self, frame, custom_conf=None):
        norm_frame = self._normalize_valid_bgr_frame(frame)
        if norm_frame is None:
            self.last_detections = []
            return []
        frame = norm_frame
        if not self._model_initialized:
            self.ensure_model_loaded()

        base_conf = float(custom_conf if custom_conf is not None else self.confidence_threshold)

        # Primary verified ONNX runtime path
        if self.model is not None and hasattr(self.model, "infer"):
            try:
                return self._track_onnx(frame, base_conf)
            except Exception as e:
                print(f"[ByteTrackTracker] ONNX tracking error: {e}")
                self.last_detections = []
                return []

        # Emergency OpenCV structural fallback when neural runtimes/weights are absent
        if torch is None or self.model is None:
            return self._track_opencv_fallback(frame, base_conf=base_conf)

        # Legacy PyTorch Ultralytics tracking path (only if explicitly active)
        try:
            fh, fw = frame.shape[:2]
            t0 = time.perf_counter()
            with get_inference_lock(), torch.inference_mode():
                results = self.model.track(
                    frame,
                    persist=True,
                    conf=0.15,
                    iou=0.50,
                    imgsz=self.imgsz,
                    tracker=self.tracker_yaml,
                    verbose=False,
                )
            t_after = time.perf_counter()
            raw_tracked, all_detections = [], []
            for result in results:
                if not hasattr(result, "boxes") or result.boxes is None:
                    continue
                for box in result.boxes:
                    xyxy_raw = box.xyxy
                    xyxy = xyxy_raw[0].tolist() if hasattr(xyxy_raw[0], "tolist") else list(xyxy_raw[0])
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = self.model.names.get(cls_id, "unknown") if cls_id in self.model.names else "unknown"
                    if 14 <= cls_id <= 23 and conf < 0.55:
                        continue
                    is_active = box.id is not None
                    min_req = (0.22 if cls_id == 0 else CLASS_CONFIDENCE_GATES.get(cls_id, 0.25)) if is_active else CLASS_CONFIDENCE_GATES.get(cls_id, max(base_conf, 0.35))
                    if conf < min_req:
                        continue
                    x1, y1 = max(0, min(fw, int(round(xyxy[0])))), max(0, min(fh, int(round(xyxy[1]))))
                    x2, y2 = max(0, min(fw, int(round(xyxy[2])))), max(0, min(fh, int(round(xyxy[3]))))
                    if (x2 - x1) < 6 or (y2 - y1) < 6:
                        continue
                    det_dict = {"class_id": cls_id, "class_name": cls_name, "confidence": conf, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
                    all_detections.append(det_dict)
                    if box.id is not None:
                        trk_dict = dict(det_dict)
                        trk_dict["track_id"] = int(box.id[0].item())
                        trk_dict["confirmed"] = True
                        raw_tracked.append(trk_dict)
            raw_tracked.sort(key=lambda t: (t["track_id"], -t["confidence"]))
            tracked_objects = []
            for cand in raw_tracked:
                if not any(kept["class_id"] == cand["class_id"] and _bbox_iou(kept, cand) >= 0.55 for kept in tracked_objects):
                    tracked_objects.append(cand)
            t_end = time.perf_counter()
            self.last_stage_timings = {
                "preprocess_ms": 0.0,
                "inference_ms": round((t_after - t0) * 1000.0, 3),
                "tracking_ms": round((t_end - t_after) * 1000.0, 3),
                "total_ms": round((t_end - t0) * 1000.0, 3),
            }
            self.last_detections = all_detections
            return tracked_objects
        except Exception as e:
            print(f"[ByteTrackTracker] Legacy PyTorch tracking error: {e}")
            self.last_detections = []
            return []
