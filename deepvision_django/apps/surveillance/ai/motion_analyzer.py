"""
Independent Motion Detection & Scene Dynamics Analyzer (Phase 4).

Strictly decoupled from object identity / person classification:
  - Evaluates background subtraction (KNN / MOG2), dense optical flow magnitude,
    and temporal scene difference with automatic global illumination/exposure-shift
    filtering so lights turning on/off, shadows, reflections, and curtains never
    produce synthetic person detections.
  - Supplies movement evidence (`motion_active`, `motion_score`, `motion_regions`,
    `mean_flow_px`, `lighting_shift`) alongside object detections & tracking.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


class IndependentMotionAnalyzer:
    """Computes scene motion evidence independently of object classification."""

    def __init__(self, method: str = "mog2", downscale_width: int = 320):
        self.method = (method or "mog2").strip().lower()
        self.downscale_width = max(120, int(downscale_width))
        self._bg_knn = cv2.createBackgroundSubtractorKNN(history=200, dist2Threshold=400.0, detectShadows=True) if cv2 else None
        self._bg_mog2 = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=16, detectShadows=True) if cv2 else None
        self._prev_gray: Optional[np.ndarray] = None
        self._last_result: Dict[str, Any] = {
            "motion_active": False,
            "motion_ratio": 0.0,
            "mean_flow_px": 0.0,
            "lighting_shift": False,
            "motion_regions": [],
            "backend": self.method,
            "process_ms": 0.0,
        }

    def reset(self):
        self._prev_gray = None
        if cv2 is not None:
            self._bg_knn = cv2.createBackgroundSubtractorKNN(history=250, dist2Threshold=450.0, detectShadows=True)
            self._bg_mog2 = cv2.createBackgroundSubtractorMOG2(history=250, varThreshold=22, detectShadows=True)

    def analyze(self, bgr_frame: Optional[np.ndarray]) -> Dict[str, Any]:
        if bgr_frame is None or cv2 is None or getattr(bgr_frame, "size", 0) == 0:
            return dict(self._last_result)

        t0 = time.perf_counter()
        orig_h, orig_w = bgr_frame.shape[:2]
        scale = min(1.0, self.downscale_width / float(max(1, orig_w)))
        sw = max(64, int(round(orig_w * scale)))
        sh = max(48, int(round(orig_h * scale)))
        small = cv2.resize(bgr_frame, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 0.99 else bgr_frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        lighting_shift = False
        temporal_ratio = 0.0
        mean_flow_px = 0.0

        if self._prev_gray is not None and self._prev_gray.shape == blurred.shape:
            # Global illumination/exposure step detector: uniform median jump across whole frame
            signed_diff = blurred.astype(np.int16) - self._prev_gray.astype(np.int16)
            med_shift = abs(float(np.median(signed_diff)))
            abs_diff = np.abs(signed_diff)
            temporal_ratio = float(np.count_nonzero(abs_diff > 20)) / float(max(1, sw * sh))
            if med_shift >= 12.0 or temporal_ratio >= 0.62:
                lighting_shift = True

        if self.method == "mog2":
            raw_fg = self._bg_mog2.apply(blurred)
            fg_mask = (raw_fg == 255).astype(np.uint8) * 255
        elif self.method == "optical_flow":
            fg_mask = np.zeros((sh, sw), dtype=np.uint8)
            if self._prev_gray is not None and self._prev_gray.shape == blurred.shape:
                flow = cv2.calcOpticalFlowFarneback(self._prev_gray, blurred, None, 0.5, 2, 11, 2, 5, 1.1, 0)
                mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                mean_flow_px = float(np.mean(mag))
                fg_mask = (mag > 1.4).astype(np.uint8) * 255
        elif self.method == "temporal_diff":
            fg_mask = np.zeros((sh, sw), dtype=np.uint8)
            if self._prev_gray is not None and self._prev_gray.shape == blurred.shape:
                diff = cv2.absdiff(self._prev_gray, blurred)
                _, fg_mask = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)
        else:
            # Default: KNN with shadow rejection (gray shadow pixel value 127 discarded, only 255 kept)
            raw_fg = self._bg_knn.apply(blurred)
            fg_mask = (raw_fg == 255).astype(np.uint8) * 255

        self._prev_gray = blurred

        if lighting_shift:
            fg_mask[:] = 0

        k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        cleaned = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, k_open)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, k_close)

        motion_ratio = float(np.count_nonzero(cleaned)) / float(max(1, sw * sh))
        regions: List[Dict[str, Any]] = []
        if not lighting_shift and motion_ratio > 0.0012:
            contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            min_area = max(18.0, (sw * sh) * 0.0012)
            inv_scale = 1.0 / scale
            for cnt in contours:
                area = float(cv2.contourArea(cnt))
                if area < min_area:
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                regions.append({
                    "x1": max(0, int(round(x * inv_scale))),
                    "y1": max(0, int(round(y * inv_scale))),
                    "x2": min(orig_w, int(round((x + w) * inv_scale))),
                    "y2": min(orig_h, int(round((y + h) * inv_scale))),
                    "area_ratio": round(area / float(max(1, sw * sh)), 4),
                })

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self._last_result = {
            "motion_active": bool(len(regions) > 0 and not lighting_shift),
            "motion_ratio": round(motion_ratio, 4),
            "mean_flow_px": round(mean_flow_px, 3),
            "lighting_shift": lighting_shift,
            "motion_regions": regions[:12],
            "backend": self.method,
            "process_ms": round(elapsed_ms, 3),
        }
        return dict(self._last_result)
