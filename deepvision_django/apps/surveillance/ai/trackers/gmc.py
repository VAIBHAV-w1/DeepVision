"""
Sparse Optical Flow Global Motion Compensation (GMC) for BoT-SORT.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


class SparseOptFlowGMC:
    """Estimates 2x3 affine camera motion matrix between consecutive frames via LK optical flow."""

    def __init__(self, downscale: int = 2):
        self.downscale = max(1, int(downscale))
        self.prev_frame: Optional[np.ndarray] = None
        self.prev_kps: Optional[np.ndarray] = None
        self.initialized = False

    def reset(self):
        self.prev_frame = None
        self.prev_kps = None
        self.initialized = False

    def apply(self, raw_frame: Optional[np.ndarray]) -> np.ndarray:
        eye = np.eye(2, 3, dtype=np.float32)
        if raw_frame is None or cv2 is None:
            return eye
        h, w = raw_frame.shape[:2]
        gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY) if raw_frame.ndim == 3 else raw_frame
        if self.downscale > 1:
            gray = cv2.resize(gray, (max(16, w // self.downscale), max(16, h // self.downscale)))

        kps = cv2.goodFeaturesToTrack(gray, maxCorners=200, qualityLevel=0.01, minDistance=8, blockSize=3)
        if not self.initialized or self.prev_frame is None or self.prev_kps is None or len(self.prev_kps) < 6:
            self.prev_frame = gray
            self.prev_kps = kps
            self.initialized = True
            return eye

        matched_kps, status, _ = cv2.calcOpticalFlowPyrLK(self.prev_frame, gray, self.prev_kps, None)
        if matched_kps is None or status is None:
            self.prev_frame = gray
            self.prev_kps = kps
            return eye

        ok_idx = status.flatten() == 1
        src_pts = self.prev_kps[ok_idx]
        dst_pts = matched_kps[ok_idx]

        self.prev_frame = gray
        self.prev_kps = kps

        if len(src_pts) < 6:
            return eye
        warp, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC)
        if warp is None:
            return eye
        if self.downscale > 1:
            warp[:, 2] *= float(self.downscale)
        return warp.astype(np.float32)

