"""
Linear Assignment, Vectorized IoU, Re-ID Appearance Extraction & Distance Fusion Helpers.
"""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np


def linear_sum_assignment(cost_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Pure-NumPy modified Jonker-Volgenant rectangular linear sum assignment
    (Crouse 2016 / SciPy equivalent). Supports +inf forbidden edges cleanly.
    """
    cost = np.asarray(cost_matrix, dtype=np.float64)
    if cost.ndim != 2:
        raise ValueError(f"Expected 2D cost matrix, got {cost.shape}")
    nr, nc = cost.shape
    if nr == 0 or nc == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    transposed = nc < nr
    if transposed:
        cost = cost.T
        nr, nc = cost.shape

    # Exact Crouse (2016) modified Jonker-Volgenant dual shortest-path solver
    u = np.zeros(nr, dtype=np.float64)
    v = np.zeros(nc, dtype=np.float64)
    path = np.full(nc, -1, dtype=np.int64)
    col4row = np.full(nr, -1, dtype=np.int64)
    row4col = np.full(nc, -1, dtype=np.int64)

    for cur_row in range(nr):
        min_val = 0.0
        i = cur_row
        remaining = np.arange(nc, dtype=np.int64)
        SR = np.zeros(nr, dtype=bool)
        SC = np.zeros(nc, dtype=bool)
        shortest_path_costs = np.full(nc, np.inf, dtype=np.float64)
        sink = -1

        while sink == -1:
            SR[i] = True
            r = min_val + cost[i, remaining] - u[i] - v[remaining]
            better = r < shortest_path_costs[remaining]
            if np.any(better):
                upd_cols = remaining[better]
                shortest_path_costs[upd_cols] = r[better]
                path[upd_cols] = i

            rem_costs = shortest_path_costs[remaining]
            lowest = np.min(rem_costs)
            if not np.isfinite(lowest):
                raise ValueError("cost matrix is infeasible")
            min_val = float(lowest)

            min_mask = rem_costs == min_val
            min_cols = remaining[min_mask]
            # Prefer unassigned column to terminate early
            unassigned = [c for c in min_cols if row4col[c] == -1]
            if unassigned:
                j = int(unassigned[0])
                sink = j
                SC[j] = True
            else:
                j = int(min_cols[0])
                SC[j] = True
                i = int(row4col[j])
            remaining = remaining[remaining != j]

        # Standard Crouse dual variable update
        si = np.where(SR)[0]
        u[cur_row] += min_val
        for ri in si:
            if ri != cur_row:
                cj = col4row[ri]
                if cj >= 0 and SC[cj]:
                    u[ri] += min_val - shortest_path_costs[cj]
        sj = np.where(SC)[0]
        v[sj] -= min_val - shortest_path_costs[sj]

        # Augment path
        j = sink
        while True:
            i = int(path[j])
            row4col[j] = i
            j, col4row[i] = int(col4row[i]), j
            if i == cur_row:
                break

    rows = np.arange(nr, dtype=np.int64)
    cols = col4row
    if transposed:
        order = np.argsort(cols)
        return cols[order], rows[order]
    return rows, cols


def linear_assignment(cost_matrix: np.ndarray, thresh: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Matches pairs with cost <= thresh; returns (matches [K,2], unmatched_a, unmatched_b)."""
    if cost_matrix.size == 0:
        return (
            np.empty((0, 2), dtype=np.int64),
            np.arange(cost_matrix.shape[0], dtype=np.int64),
            np.arange(cost_matrix.shape[1], dtype=np.int64),
        )
    safe_cost = np.where(np.isfinite(cost_matrix), np.minimum(cost_matrix, 1e6), 1e6)
    r, c = linear_sum_assignment(safe_cost)
    matches = np.asarray(
        [[r[i], c[i]] for i in range(len(r)) if cost_matrix[r[i], c[i]] <= thresh],
        dtype=np.int64,
    )
    if len(matches) == 0:
        return (
            np.empty((0, 2), dtype=np.int64),
            np.arange(cost_matrix.shape[0], dtype=np.int64),
            np.arange(cost_matrix.shape[1], dtype=np.int64),
        )
    matched_a = set(matches[:, 0].tolist())
    matched_b = set(matches[:, 1].tolist())
    unmatched_a = np.asarray([i for i in range(cost_matrix.shape[0]) if i not in matched_a], dtype=np.int64)
    unmatched_b = np.asarray([j for j in range(cost_matrix.shape[1]) if j not in matched_b], dtype=np.int64)
    return matches, unmatched_a, unmatched_b


def iou_batch(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """Computes pairwise IoU [N, M] for xyxy arrays."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)
    a = np.asarray(boxes_a, dtype=np.float32)
    b = np.asarray(boxes_b, dtype=np.float32)
    x1 = np.maximum(a[:, 0:1], b[:, 0:1].T)
    y1 = np.maximum(a[:, 1:2], b[:, 1:2].T)
    x2 = np.minimum(a[:, 2:3], b[:, 2:3].T)
    y2 = np.minimum(a[:, 3:4], b[:, 3:4].T)
    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_a = np.maximum(1.0, (a[:, 2:3] - a[:, 0:1]) * (a[:, 3:4] - a[:, 1:2]))
    area_b = np.maximum(1.0, (b[:, 2:3] - b[:, 0:1]) * (b[:, 3:4] - b[:, 1:2]))
    return inter / np.maximum(1e-6, area_a + area_b.T - inter)


def extract_reid_embedding(bgr_frame: Optional[np.ndarray], xyxy: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """
    Extracts an L2-normalized upper/lower-body spatial HSV+gradient appearance descriptor
    (pure OpenCV + NumPy, signed-SAC-safe). Distinguishes subjects crossing or re-entering.
    """
    if bgr_frame is None or cv2 is None:
        return None
    fh, fw = bgr_frame.shape[:2]
    x1 = max(0, min(fw - 1, int(xyxy[0])))
    y1 = max(0, min(fh - 1, int(xyxy[1])))
    x2 = max(0, min(fw, int(xyxy[2])))
    y2 = max(0, min(fh, int(xyxy[3])))
    if (x2 - x1) < 12 or (y2 - y1) < 12:
        return None
    crop = bgr_frame[y1:y2, x1:x2]
    if (x2 - x1) > 48 or (y2 - y1) > 96:
        crop = cv2.resize(crop, (48, 96), interpolation=cv2.INTER_NEAREST)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    ch = hsv.shape[0]
    mid = max(1, ch // 2)
    top_hsv = hsv[:mid, :]
    bot_hsv = hsv[mid:, :]

    # Coarse 8x4 hue-sat histogram on top half + bottom half (capturing shirt vs trousers)
    h_top = cv2.calcHist([top_hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).flatten()
    h_bot = cv2.calcHist([bot_hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).flatten()
    # Aspect ratio cue
    ar = np.array([(x2 - x1) / float(max(1, y2 - y1))], dtype=np.float32)
    feat = np.concatenate([h_top.astype(np.float32), h_bot.astype(np.float32), ar])
    norm = float(np.linalg.norm(feat))
    if norm <= 1e-6:
        return None
    return feat / norm


def cosine_distance_matrix(tracks, dets) -> np.ndarray:
    """Computes cosine distance [N, M] clipped to [0, 1] using smooth_feat."""
    n, m = len(tracks), len(dets)
    if n == 0 or m == 0:
        return np.zeros((n, m), dtype=np.float32)
    cost = np.ones((n, m), dtype=np.float32)
    for i, trk in enumerate(tracks):
        tf = getattr(trk, "smooth_feat", None)
        if tf is None:
            continue
        for j, det in enumerate(dets):
            df = getattr(det, "curr_feat", None)
            if df is None:
                continue
            sim = float(np.dot(tf, df))
            cost[i, j] = float(np.clip(1.0 - sim, 0.0, 1.0))
    return cost
