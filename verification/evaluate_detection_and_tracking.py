"""
DeepVision 4.0 — P0 Detection (YOLO11n) & Tracking (ByteTrack) Evaluation Suite
================================================================================
Evaluates the production YOLO11n model (models/yolo11n.pt), YOLODetector, and
ByteTrackTracker (apps/surveillance/ai/tracker.py + bytetrack.yaml) against the
human-verified ground-truth dataset in verification/eval_dataset/ground_truth.json
extracted from authorized real camera recordings (1280x720).

Evaluates and reports:
1. YOLO11n Detection Quality:
   - Overall Precision, Recall, F1, Mean Matched Bounding-Box IoU (at IoU >= 0.45 and >= 0.50)
   - Per-class metrics (person, bottle, bowl, cell phone, backpack, handbag, laptop, chair, etc.)
   - Small object detection recall
   - Partially occluded object recall
   - Multiple moving objects recall & concurrency
   - False dog / animal detections check (eliminates handheld phone edge noise)
   - Exact False Positives and False Negatives catalog
   - COCO 80-class mapping integrity verification
   - CPU inference latency and achieved FPS breakdown

2. ByteTrack Multi-Frame Tracking Quality:
   - Stable IDs (ID stability ratio across 180 real frames in 3 sequences)
   - ID switches count
   - Track fragmentation count (with active track hysteresis)
   - Occlusion recovery test (8-frame full blackout occlusion on real footage -> exact ID recovery)
   - Duplicate tracks check (same-class active tracks overlapping IoU >= 0.70)
   - Lost-track handling test (105-frame disappearance > track_buffer=75 -> zero phantom tracks + fresh ID on re-entry)
   - Trajectory correctness (centroid smoothness, max frame-to-frame jump, 0 out-of-bounds coordinates)

Saves full quantitative report to D:\\DeepVision\\reports\\p0_detection_tracking_eval.json
and visual GT-vs-Prediction renders to D:\\DeepVision\\verification\\eval_dataset\\renders\\.
"""

import json
import math
import os
import sys
import time
from pathlib import Path

os.environ["YOLO_CONFIG_DIR"] = str(Path(__file__).resolve().parent.parent / "Ultralytics")

import cv2
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / "deepvision_django"
EVAL_DIR = ROOT_DIR / "verification" / "eval_dataset"
GT_PATH = EVAL_DIR / "ground_truth.json"
RENDER_DIR = EVAL_DIR / "renders"
REPORT_PATH = ROOT_DIR / "reports" / "p0_detection_tracking_eval.json"

sys.path.insert(0, str(DJANGO_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.surveillance.ai.model_loader import get_shared_yolo_model
from apps.surveillance.ai.detector import YOLODetector, CLASS_CONFIDENCE_GATES
from apps.surveillance.ai.tracker import ByteTrackTracker


def compute_iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in box_a]
    bx1, by1, bx2, by2 = [float(v) for v in box_b]
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = area_a + area_b - inter
    return float(inter / denom) if denom > 0.0 else 0.0


def greedy_match_detections(gt_objs, preds, iou_thresh=0.45, allow_bag_cup_alias=False):
    """
    Greedy IoU matching sorted by IoU descending.
    Strict class equality by default; optionally allows surveillance taxonomy aliasing
    (backpack <-> handbag, bowl <-> cup).
    """
    candidates = []
    for gi, g in enumerate(gt_objs):
        g_cls = g["class_name"]
        for pi, p in enumerate(preds):
            p_cls = p["class_name"]
            cls_ok = (g_cls == p_cls)
            if not cls_ok and allow_bag_cup_alias:
                if {g_cls, p_cls} in ({"backpack", "handbag"}, {"bowl", "cup"}):
                    cls_ok = True
            if not cls_ok:
                continue
            iou = compute_iou(g["bbox"], p["bbox"])
            if iou >= iou_thresh:
                candidates.append((iou, gi, pi))

    candidates.sort(key=lambda x: x[0], reverse=True)
    matched_gt = {}
    matched_pred = {}
    for iou, gi, pi in candidates:
        if gi not in matched_gt and pi not in matched_pred:
            matched_gt[gi] = (pi, iou)
            matched_pred[pi] = (gi, iou)

    return matched_gt, matched_pred


def prf1(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def evaluate_detector_predictions(predictions_by_frame, gt_frames, iou_match_thresh=0.45, allow_bag_cup_alias=False, save_renders=False):
    """
    Evaluates a dictionary of frame_id -> list of predictions against ground truth.
    Computes overall, per-class, small-object, occluded, and multi-moving metrics.
    """
    total_tp = total_fp = total_fn = 0
    matched_ious = []

    # Per-class accumulator: cls_name -> {tp, fp, fn, matched_ious}
    all_classes = set()
    for fmeta in gt_frames:
        for g in fmeta["objects"]:
            all_classes.add(g["class_name"])
    for fid, preds in predictions_by_frame.items():
        for p in preds:
            all_classes.add(p["class_name"])

    per_class_counts = {c: {"tp": 0, "fp": 0, "fn": 0, "ious": []} for c in all_classes}

    person_tp = person_fp = person_fn = 0
    person_ious = []
    common_tp = common_fp = common_fn = 0
    common_ious = []

    small_tp = small_fn = 0
    occluded_tp = occluded_fn = 0
    multi_tp = multi_fn = 0

    dog_false_positives = 0
    animal_classes = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}

    fp_catalog = []
    fn_catalog = []
    per_frame_details = []

    if save_renders:
        RENDER_DIR.mkdir(parents=True, exist_ok=True)

    for fmeta in gt_frames:
        fid = fmeta["frame_id"]
        gt_objs = fmeta["objects"]
        preds = predictions_by_frame.get(fid, [])

        matched_gt, matched_pred = greedy_match_detections(
            gt_objs, preds, iou_thresh=iou_match_thresh, allow_bag_cup_alias=allow_bag_cup_alias
        )

        tp = len(matched_gt)
        fp = len(preds) - len(matched_pred)
        fn = len(gt_objs) - len(matched_gt)

        total_tp += tp
        total_fp += fp
        total_fn += fn

        for gi, g in enumerate(gt_objs):
            g_cls = g["class_name"]
            is_matched = gi in matched_gt
            is_person = (g_cls == "person")

            if is_matched:
                pi, iou = matched_gt[gi]
                matched_ious.append(iou)
                per_class_counts[g_cls]["tp"] += 1
                per_class_counts[g_cls]["ious"].append(iou)

                if is_person:
                    person_tp += 1
                    person_ious.append(iou)
                else:
                    common_tp += 1
                    common_ious.append(iou)

                if g.get("small"):
                    small_tp += 1
                if g.get("occluded"):
                    occluded_tp += 1
                if fmeta.get("multi_moving"):
                    multi_tp += 1
            else:
                per_class_counts[g_cls]["fn"] += 1
                if is_person:
                    person_fn += 1
                else:
                    common_fn += 1

                if g.get("small"):
                    small_fn += 1
                if g.get("occluded"):
                    occluded_fn += 1
                if fmeta.get("multi_moving"):
                    multi_fn += 1

                fn_catalog.append({
                    "frame_id": fid,
                    "class_name": g_cls,
                    "gt_bbox": g["bbox"],
                    "small": bool(g.get("small")),
                    "occluded": bool(g.get("occluded")),
                })

        for pi, p in enumerate(preds):
            p_cls = p["class_name"]
            if p_cls in animal_classes:
                dog_false_positives += 1

            if pi not in matched_pred:
                per_class_counts[p_cls]["fp"] += 1
                if p_cls == "person":
                    person_fp += 1
                else:
                    common_fp += 1

                best_any_iou = 0.0
                best_gt_cls = None
                for g in gt_objs:
                    ov = compute_iou(g["bbox"], p["bbox"])
                    if ov > best_any_iou:
                        best_any_iou = ov
                        best_gt_cls = g["class_name"]

                fp_catalog.append({
                    "frame_id": fid,
                    "predicted_class": p_cls,
                    "confidence": p["confidence"],
                    "pred_bbox": p["bbox"],
                    "max_gt_overlap_iou": round(best_any_iou, 3),
                    "overlapping_gt_class": best_gt_cls if best_any_iou >= 0.30 else None,
                })

        per_frame_details.append({
            "frame_id": fid,
            "gt_count": len(gt_objs),
            "pred_count": len(preds),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        })

        if save_renders:
            img_path = EVAL_DIR / fmeta["file"]
            img = cv2.imread(str(img_path))
            if img is not None:
                vis = img.copy()
                for g in gt_objs:
                    gx1, gy1, gx2, gy2 = g["bbox"]
                    cv2.rectangle(vis, (gx1, gy1), (gx2, gy2), (0, 220, 0), 2)
                    tag = f"GT:{g['class_name']}"
                    if g.get("small"):
                        tag += "[S]"
                    if g.get("occluded"):
                        tag += "[O]"
                    cv2.putText(vis, tag, (gx1 + 4, max(18, gy1 + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 0), 2)
                for pi, p in enumerate(preds):
                    px1, py1, px2, py2 = p["bbox"]
                    color = (255, 220, 0) if pi in matched_pred else (0, 80, 255)
                    cv2.rectangle(vis, (px1, py1), (px2, py2), color, 2)
                    ptag = f"PRED:{p['class_name']} {p['confidence']:.2f}"
                    cv2.putText(vis, ptag, (px1 + 4, max(36, py2 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2)
                render_name = f"{fid}_eval_calibrated.jpg" if allow_bag_cup_alias else f"{fid}_eval_strict.jpg"
                cv2.imwrite(str(RENDER_DIR / render_name), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])

    overall = prf1(total_tp, total_fp, total_fn)
    overall["mean_bbox_iou"] = round(float(np.mean(matched_ious)), 4) if matched_ious else 0.0

    person_metrics = prf1(person_tp, person_fp, person_fn)
    person_metrics["mean_bbox_iou"] = round(float(np.mean(person_ious)), 4) if person_ious else 0.0

    common_metrics = prf1(common_tp, common_fp, common_fn)
    common_metrics["mean_bbox_iou"] = round(float(np.mean(common_ious)), 4) if common_ious else 0.0

    per_class_summary = {}
    for c, stat in sorted(per_class_counts.items()):
        m = prf1(stat["tp"], stat["fp"], stat["fn"])
        m["mean_bbox_iou"] = round(float(np.mean(stat["ious"])), 4) if stat["ious"] else 0.0
        per_class_summary[c] = m

    return {
        "iou_match_threshold": iou_match_thresh,
        "allow_bag_cup_alias": allow_bag_cup_alias,
        "overall": overall,
        "per_class": per_class_summary,
        "person_detection": person_metrics,
        "common_object_detection": common_metrics,
        "small_object_detection": {
            "tp": small_tp,
            "fn": small_fn,
            "total_gt": small_tp + small_fn,
            "recall": round(small_tp / (small_tp + small_fn), 4) if (small_tp + small_fn) > 0 else 0.0,
        },
        "partially_occluded_detection": {
            "tp": occluded_tp,
            "fn": occluded_fn,
            "total_gt": occluded_tp + occluded_fn,
            "recall": round(occluded_tp / (occluded_tp + occluded_fn), 4) if (occluded_tp + occluded_fn) > 0 else 0.0,
        },
        "multiple_moving_objects": {
            "tp": multi_tp,
            "fn": multi_fn,
            "total_gt": multi_tp + multi_fn,
            "recall": round(multi_tp / (multi_tp + multi_fn), 4) if (multi_tp + multi_fn) > 0 else 0.0,
        },
        "dog_false_positives": dog_false_positives,
        "false_positives": fp_catalog,
        "false_negatives": fn_catalog,
        "per_frame": per_frame_details,
    }


def evaluate_bytetrack_sequences(gt_sequences):
    seq_reports = []
    total_target_obs = 0
    total_primary_id_obs = 0
    total_id_switches = 0
    total_fragmentations = 0
    total_duplicate_frames = 0
    total_oob_boxes = 0
    all_step_displacements = []
    max_jump_px = 0.0

    for seq in gt_sequences:
        seq_id = seq["sequence_id"]
        sdir = EVAL_DIR / seq["directory"]
        frame_files = sorted(sdir.glob("*.jpg"))
        tracker = ByteTrackTracker(confidence_threshold=0.35, imgsz=640)

        target_history = {t["gt_id"]: [] for t in seq["targets"]}
        track_centroids = {}
        seq_dup_frames = 0
        seq_oob = 0

        for fidx, fp in enumerate(frame_files):
            frame = cv2.imread(str(fp))
            fh, fw = frame.shape[:2]
            tracks = tracker.track(frame)
            for tr in tracks:
                tr["bbox"] = [tr["x1"], tr["y1"], tr["x2"], tr["y2"]]

            # Check out-of-bounds & duplicate overlapping tracks
            for tr in tracks:
                x1, y1, x2, y2 = tr["bbox"]
                if x1 < 0 or y1 < 0 or x2 > fw or y2 > fh or x2 <= x1 or y2 <= y1:
                    seq_oob += 1
                tid = tr["track_id"]
                cx = 0.5 * (x1 + x2)
                cy = 0.5 * (y1 + y2)
                if tid in track_centroids:
                    px, py, pf = track_centroids[tid]
                    if fidx == pf + 1:
                        dist = math.hypot(cx - px, cy - py)
                        all_step_displacements.append(dist)
                        if dist > max_jump_px:
                            max_jump_px = dist
                track_centroids[tid] = (cx, cy, fidx)

            has_dup = False
            for i in range(len(tracks)):
                for j in range(i + 1, len(tracks)):
                    if tracks[i]["class_name"] == tracks[j]["class_name"]:
                        if compute_iou(tracks[i]["bbox"], tracks[j]["bbox"]) >= 0.70:
                            has_dup = True
            if has_dup:
                seq_dup_frames += 1

            # Associate active tracks to sequence GT target regions
            for t in seq["targets"]:
                gid = t["gt_id"]
                t_cls = t["class_name"]
                t_reg = t["region"]
                best_tid = None
                best_iou = 0.0
                for tr in tracks:
                    if tr["class_name"] != t_cls:
                        continue
                    ov = compute_iou(t_reg, tr["bbox"])
                    bx1, by1, bx2, by2 = tr["bbox"]
                    cx, cy = 0.5 * (bx1 + bx2), 0.5 * (by1 + by2)
                    in_reg = (t_reg[0] <= cx <= t_reg[2]) and (t_reg[1] <= cy <= t_reg[3])
                    score = ov if ov >= 0.25 else (0.25 if in_reg else 0.0)
                    if score > best_iou:
                        best_iou = score
                        best_tid = tr["track_id"]
                target_history[gid].append(best_tid)

        total_duplicate_frames += seq_dup_frames
        total_oob_boxes += seq_oob

        target_summaries = []
        for t in seq["targets"]:
            gid = t["gt_id"]
            hist = target_history[gid]
            non_null = [tid for tid in hist if tid is not None]
            unique_ids = sorted(set(non_null))

            id_sw = 0
            prev_valid = None
            for tid in non_null:
                if prev_valid is not None and tid != prev_valid:
                    id_sw += 1
                prev_valid = tid

            frags = 0
            seen_first = False
            in_gap = False
            for tid in hist:
                if tid is not None:
                    if seen_first and in_gap:
                        frags += 1
                    seen_first = True
                    in_gap = False
                else:
                    if seen_first:
                        in_gap = True

            primary_count = 0
            primary_id = None
            if non_null:
                counts = {}
                for tid in non_null:
                    counts[tid] = counts.get(tid, 0) + 1
                primary_id, primary_count = max(counts.items(), key=lambda kv: kv[1])

            stability = (primary_count / len(non_null)) if non_null else 0.0
            coverage = len(non_null) / len(hist) if hist else 0.0

            total_target_obs += len(non_null)
            total_primary_id_obs += primary_count
            total_id_switches += id_sw
            total_fragmentations += frags

            target_summaries.append({
                "gt_id": gid,
                "class_name": t["class_name"],
                "frames_total": len(hist),
                "frames_tracked": len(non_null),
                "coverage_ratio": round(coverage, 4),
                "primary_track_id": primary_id,
                "unique_track_ids": unique_ids,
                "id_stability_ratio": round(stability, 4),
                "id_switches": id_sw,
                "fragmentations": frags,
            })

        seq_reports.append({
            "sequence_id": seq_id,
            "frames_evaluated": len(frame_files),
            "duplicate_track_frames": seq_dup_frames,
            "out_of_bounds_boxes": seq_oob,
            "targets": target_summaries,
        })

    # Controlled Stress Test A: Occlusion Recovery (8-frame full blackout)
    seq1_files = sorted((EVAL_DIR / "sequences" / "seq_01_cam4_motion").glob("*.jpg"))
    occ_tracker = ByteTrackTracker(confidence_threshold=0.35, imgsz=640)
    pre_occ_ids = []
    during_occ_ids = []
    post_occ_ids = []
    for idx, fp in enumerate(seq1_files[:45]):
        frame = cv2.imread(str(fp))
        if 20 <= idx <= 27:
            frame[:, :] = 0
        tracks = occ_tracker.track(frame)
        person_tids = [tr["track_id"] for tr in tracks if tr["class_name"] == "person"]
        if idx < 20:
            pre_occ_ids.extend(person_tids)
        elif idx <= 27:
            during_occ_ids.extend(person_tids)
        else:
            post_occ_ids.extend(person_tids)

    pre_primary = max(set(pre_occ_ids), key=pre_occ_ids.count) if pre_occ_ids else None
    post_primary = max(set(post_occ_ids), key=post_occ_ids.count) if post_occ_ids else None
    occlusion_recovery = {
        "occluded_frames": 8,
        "pre_occlusion_track_id": pre_primary,
        "phantom_tracks_during_blackout": len(during_occ_ids),
        "post_occlusion_track_id": post_primary,
        "recovered_same_id": (pre_primary is not None and pre_primary == post_primary and len(during_occ_ids) == 0),
    }

    # Controlled Stress Test B: Lost-Track Expiration (>75 frames buffer)
    lost_tracker = ByteTrackTracker(confidence_threshold=0.35, imgsz=640)
    initial_ids = []
    for fp in seq1_files[:15]:
        frame = cv2.imread(str(fp))
        tracks = lost_tracker.track(frame)
        initial_ids.extend([tr["track_id"] for tr in tracks if tr["class_name"] == "person"])
    init_id = max(set(initial_ids), key=initial_ids.count) if initial_ids else None

    black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    phantom_during_100_blank = 0
    for _ in range(105):
        tracks = lost_tracker.track(black_frame)
        phantom_during_100_blank += len(tracks)

    reentry_ids = []
    for fp in seq1_files[15:25]:
        frame = cv2.imread(str(fp))
        tracks = lost_tracker.track(frame)
        reentry_ids.extend([tr["track_id"] for tr in tracks if tr["class_name"] == "person"])
    reentry_id = max(set(reentry_ids), key=reentry_ids.count) if reentry_ids else None

    lost_track_handling = {
        "absent_frames": 105,
        "track_buffer_configured": 75,
        "initial_track_id": init_id,
        "phantom_emissions_while_lost": phantom_during_100_blank,
        "reentry_track_id_after_expiry": reentry_id,
        "expired_and_reallocated_cleanly": (
            init_id is not None
            and reentry_id is not None
            and reentry_id != init_id
            and phantom_during_100_blank == 0
        ),
    }

    overall_stability = (total_primary_id_obs / total_target_obs) if total_target_obs > 0 else 0.0
    return {
        "overall_id_stability_ratio": round(overall_stability, 4),
        "total_tracked_target_observations": total_target_obs,
        "total_id_switches": total_id_switches,
        "total_fragmentations": total_fragmentations,
        "total_duplicate_track_frames": total_duplicate_frames,
        "total_out_of_bounds_boxes": total_oob_boxes,
        "trajectory_metrics": {
            "mean_step_displacement_px": round(float(np.mean(all_step_displacements)), 3) if all_step_displacements else 0.0,
            "p95_step_displacement_px": round(float(np.percentile(all_step_displacements, 95)), 3) if all_step_displacements else 0.0,
            "max_step_jump_px": round(float(max_jump_px), 3),
            "out_of_bounds_coordinates": total_oob_boxes,
        },
        "occlusion_recovery_test": occlusion_recovery,
        "lost_track_handling_test": lost_track_handling,
        "sequences": seq_reports,
    }


def main():
    print("=" * 76)
    print("  DEEPVISION 4.0 — P0 DETECTION (YOLO11n) & TRACKING (ByteTrack) EVALUATION")
    print("=" * 76)

    gt_data = json.loads(GT_PATH.read_text(encoding="utf-8"))
    model = get_shared_yolo_model()
    detector = YOLODetector()

    # 1. Verify COCO class mapping integrity
    expected_classes = {
        0: "person",
        24: "backpack",
        26: "handbag",
        28: "suitcase",
        39: "bottle",
        41: "cup",
        45: "bowl",
        56: "chair",
        62: "tv",
        63: "laptop",
        67: "cell phone",
    }
    mapping_checks = {
        str(cid): {
            "expected": ename,
            "actual": model.names.get(cid),
            "matches": model.names.get(cid) == ename,
        }
        for cid, ename in expected_classes.items()
    }
    class_mapping_valid = len(model.names) == 80 and all(v["matches"] for v in mapping_checks.values())
    print(f"COCO 80-Class Mapping Check: {'PASS' if class_mapping_valid else 'FAIL'}")

    # 2. Warmup model and benchmark steady-state CPU inference latency
    warmup_img = cv2.imread(str(EVAL_DIR / gt_data["frames"][0]["file"]))
    t_warm0 = time.perf_counter()
    detector.detect(warmup_img)
    cold_start_ms = round((time.perf_counter() - t_warm0) * 1000.0, 2)
    detector.detect(warmup_img)

    print("\nRunning production detector with class-specific confidence gates...")
    latencies = []
    prod_predictions = {}
    for fmeta in gt_data["frames"]:
        fid = fmeta["frame_id"]
        img_path = EVAL_DIR / fmeta["file"]
        img = cv2.imread(str(img_path))
        t0 = time.perf_counter()
        raw_dets = detector.detect(img)
        t_el = (time.perf_counter() - t0) * 1000.0
        latencies.append(t_el)

        preds = []
        for d in raw_dets:
            preds.append({
                "class_id": d["class_id"],
                "class_name": d["class_name"],
                "confidence": round(float(d["confidence"]), 4),
                "bbox": [d["x1"], d["y1"], d["x2"], d["y2"]],
            })
        prod_predictions[fid] = preds

    avg_latency_ms = round(float(np.mean(latencies)), 2)
    p95_latency_ms = round(float(np.percentile(latencies, 95)), 2)
    achieved_fps = round(1000.0 / avg_latency_ms, 2)
    print(f"Detection Latency: mean={avg_latency_ms} ms, p95={p95_latency_ms} ms, FPS={achieved_fps}")

    # 3. Evaluate production detector: Strict COCO vs Surveillance Taxonomy Aliasing
    prod_eval_strict = evaluate_detector_predictions(
        prod_predictions, gt_data["frames"], iou_match_thresh=0.45, allow_bag_cup_alias=False, save_renders=True
    )
    prod_eval_aliased = evaluate_detector_predictions(
        prod_predictions, gt_data["frames"], iou_match_thresh=0.45, allow_bag_cup_alias=True, save_renders=True
    )
    prod_eval_iou50 = evaluate_detector_predictions(
        prod_predictions, gt_data["frames"], iou_match_thresh=0.50, allow_bag_cup_alias=True, save_renders=False
    )

    print("\n=== PRODUCTION DETECTION METRICS (STRICT COCO MATCHING) ===")
    print(f"Overall: P={prod_eval_strict['overall']['precision']:.4f}, R={prod_eval_strict['overall']['recall']:.4f}, F1={prod_eval_strict['overall']['f1']:.4f}, MeanIoU={prod_eval_strict['overall']['mean_bbox_iou']:.4f}")
    print(f"  Person: P={prod_eval_strict['person_detection']['precision']:.4f}, R={prod_eval_strict['person_detection']['recall']:.4f}, F1={prod_eval_strict['person_detection']['f1']:.4f}")
    print(f"  Common Objects: P={prod_eval_strict['common_object_detection']['precision']:.4f}, R={prod_eval_strict['common_object_detection']['recall']:.4f}, F1={prod_eval_strict['common_object_detection']['f1']:.4f}")
    print(f"  Small Objects Recall: {prod_eval_strict['small_object_detection']['recall']:.4f} ({prod_eval_strict['small_object_detection']['tp']}/{prod_eval_strict['small_object_detection']['total_gt']})")
    print(f"  False Dog / Animal Detections: {prod_eval_strict['dog_false_positives']}")

    print("\n=== PRODUCTION DETECTION METRICS (SURVEILLANCE TAXONOMY ALIASED) ===")
    print(f"Overall: P={prod_eval_aliased['overall']['precision']:.4f}, R={prod_eval_aliased['overall']['recall']:.4f}, F1={prod_eval_aliased['overall']['f1']:.4f}, MeanIoU={prod_eval_aliased['overall']['mean_bbox_iou']:.4f}")
    print(f"  Person: P={prod_eval_aliased['person_detection']['precision']:.4f}, R={prod_eval_aliased['person_detection']['recall']:.4f}, F1={prod_eval_aliased['person_detection']['f1']:.4f}")
    print(f"  Common Objects: P={prod_eval_aliased['common_object_detection']['precision']:.4f}, R={prod_eval_aliased['common_object_detection']['recall']:.4f}, F1={prod_eval_aliased['common_object_detection']['f1']:.4f}")
    print(f"  Small Objects Recall: {prod_eval_aliased['small_object_detection']['recall']:.4f} ({prod_eval_aliased['small_object_detection']['tp']}/{prod_eval_aliased['small_object_detection']['total_gt']})")

    print("\nPer-Class Breakdown (Aliased):")
    for cname, cm in sorted(prod_eval_aliased["per_class"].items()):
        if cm["tp"] > 0 or cm["fp"] > 0 or cm["fn"] > 0:
            print(f"  {cname:12s}: TP={cm['tp']:2d}, FP={cm['fp']:2d}, FN={cm['fn']:2d} | P={cm['precision']:.4f}, R={cm['recall']:.4f}, F1={cm['f1']:.4f}, MeanIoU={cm['mean_bbox_iou']:.4f}")

    # 4. Multi-threshold sweep for raw YOLO11n for benchmark comparison
    print("\nRunning confidence threshold sweep on raw model...")
    sweep_results = {}
    for th in [0.20, 0.25, 0.35, 0.45, 0.55]:
        raw_sweep_preds = {}
        for fmeta in gt_data["frames"]:
            fid = fmeta["frame_id"]
            img_path = EVAL_DIR / fmeta["file"]
            img = cv2.imread(str(img_path))
            res = model.predict(img, conf=th, iou=0.50, imgsz=640, verbose=False)[0]
            plist = []
            if res.boxes is not None:
                for b in res.boxes:
                    plist.append({
                        "class_id": int(b.cls[0]),
                        "class_name": str(model.names[int(b.cls[0])]),
                        "confidence": float(b.conf[0]),
                        "bbox": [int(round(v)) for v in b.xyxy[0].tolist()],
                    })
            raw_sweep_preds[fid] = plist
        ev = evaluate_detector_predictions(raw_sweep_preds, gt_data["frames"], iou_match_thresh=0.45, allow_bag_cup_alias=False)
        sweep_results[f"{th:.2f}"] = {
            "overall": ev["overall"],
            "person_detection": ev["person_detection"],
            "common_object_detection": ev["common_object_detection"],
            "small_object_recall": ev["small_object_detection"]["recall"],
            "occluded_object_recall": ev["partially_occluded_detection"]["recall"],
        }

    # 5. Evaluate ByteTrack multi-frame tracking
    print("\nRunning ByteTrack multi-frame tracking evaluation across 3 real 60-frame sequences + occlusion/lost-track stress tests...")
    tracking_eval = evaluate_bytetrack_sequences(gt_data["tracking_sequences"])
    print(f"[ByteTrack] Overall ID Stability: {tracking_eval['overall_id_stability_ratio']:.4f}")
    print(f"  ID Switches:              {tracking_eval['total_id_switches']}")
    print(f"  Track Fragmentations:     {tracking_eval['total_fragmentations']}")
    print(f"  Duplicate Track Frames:   {tracking_eval['total_duplicate_track_frames']}")
    print(f"  Out-of-Bounds Boxes:      {tracking_eval['total_out_of_bounds_boxes']}")
    print(f"  Mean Step Displacement:   {tracking_eval['trajectory_metrics']['mean_step_displacement_px']:.2f} px (P95={tracking_eval['trajectory_metrics']['p95_step_displacement_px']:.2f} px)")
    print(f"  Occlusion Recovery (8f):  recovered_same_id={tracking_eval['occlusion_recovery_test']['recovered_same_id']} (pre={tracking_eval['occlusion_recovery_test']['pre_occlusion_track_id']} -> post={tracking_eval['occlusion_recovery_test']['post_occlusion_track_id']})")
    print(f"  Lost-Track Expiry (105f): expired_cleanly={tracking_eval['lost_track_handling_test']['expired_and_reallocated_cleanly']} (init={tracking_eval['lost_track_handling_test']['initial_track_id']} -> reentry={tracking_eval['lost_track_handling_test']['reentry_track_id_after_expiry']}, phantoms={tracking_eval['lost_track_handling_test']['phantom_emissions_while_lost']})")

    report = {
        "suite": "P0_DETECTION_AND_TRACKING_EVALUATION",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {
            "path": str(GT_PATH.relative_to(ROOT_DIR).as_posix()),
            "static_frames_count": len(gt_data["frames"]),
            "total_ground_truth_boxes": sum(len(f["objects"]) for f in gt_data["frames"]),
            "tracking_sequences_count": len(gt_data["tracking_sequences"]),
            "total_sequence_frames": sum(s["num_frames"] for s in gt_data["tracking_sequences"]),
        },
        "class_mapping": {
            "total_classes": len(model.names),
            "valid": class_mapping_valid,
            "verified_classes": mapping_checks,
        },
        "performance": {
            "cold_start_ms": cold_start_ms,
            "average_steady_state_latency_ms": avg_latency_ms,
            "p95_steady_state_latency_ms": p95_latency_ms,
            "achieved_fps": achieved_fps,
            "device": "CPU",
        },
        "production_calibrated_strict_coco": prod_eval_strict,
        "production_calibrated_aliased": prod_eval_aliased,
        "production_calibrated_iou50": prod_eval_iou50["overall"],
        "confidence_threshold_sweep": sweep_results,
        "bytetrack_evaluation": tracking_eval,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("-" * 76)
    print(f"Saved P0 detection & tracking report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
