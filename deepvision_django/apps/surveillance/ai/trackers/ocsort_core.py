"""
Genuine OC-SORT Multi-Object Tracker (Cao et al., CVPR 2023).
Implements Observation-Centric Re-Update (ORU), Observation-Centric Momentum (OCM)
velocity direction consistency, and Observation-Centric Recovery (OCR).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from apps.surveillance.ai.trackers.bytetrack_core import (
    STrack,
    TrackState,
    _joint_stracks,
    _remove_duplicate_stracks,
    _sub_stracks,
    _tlwh_to_xyah,
)
from apps.surveillance.ai.trackers.kalman import KalmanFilterXYAH
from apps.surveillance.ai.trackers.matching import iou_batch, linear_assignment


class OCSortTrack(STrack):
    def __init__(self, xyxy: np.ndarray, score: float, cls_id: int, cls_name: str, delta_t: int = 3):
        super().__init__(xyxy, score, cls_id, cls_name)
        self.last_observation = np.array([-1.0, -1.0, -1.0, -1.0], dtype=np.float32)
        self.observations: Dict[int, np.ndarray] = {}
        self.velocity: Optional[np.ndarray] = None
        self.delta_t = int(delta_t)
        self._saved_mean: Optional[np.ndarray] = None
        self._saved_cov: Optional[np.ndarray] = None

    @staticmethod
    def _box_center_xyxy(box: np.ndarray) -> np.ndarray:
        return np.array([0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])], dtype=np.float64)

    def _compute_velocity(self, box_a: np.ndarray, box_b: np.ndarray) -> np.ndarray:
        ca, cb = self._box_center_xyxy(box_a), self._box_center_xyxy(box_b)
        diff = cb - ca
        norm = float(np.linalg.norm(diff)) + 1e-6
        return diff / norm

    def activate(self, kalman_filter: KalmanFilterXYAH, frame_id: int, track_id: int):
        super().activate(kalman_filter, frame_id, track_id)
        obs = self.xyxy
        self.last_observation = obs
        self.observations[frame_id] = obs

    def _record_observation(self, obs_xyxy: np.ndarray, frame_id: int):
        prev = None
        for dt in range(self.delta_t, 0, -1):
            if (frame_id - dt) in self.observations:
                prev = self.observations[frame_id - dt]
                break
        if prev is None and self.last_observation[0] >= 0:
            prev = self.last_observation
        if prev is not None:
            self.velocity = self._compute_velocity(prev, obs_xyxy)
        self.last_observation = obs_xyxy.copy()
        self.observations[frame_id] = obs_xyxy.copy()
        if len(self.observations) > 30:
            oldest = min(self.observations.keys())
            self.observations.pop(oldest, None)

    def _oru_replay(self, obs_xyxy: np.ndarray, frame_id: int):
        """Observation-Centric Re-Update across missing-frame gap via linear virtual trajectory."""
        gap = frame_id - self.frame_id
        if gap <= 1 or self._saved_mean is None or self.last_observation[0] < 0:
            return
        self.mean = self._saved_mean.copy()
        self.covariance = self._saved_cov.copy()
        start_box = self.last_observation
        for step in range(1, gap):
            frac = step / float(gap)
            interp_xyxy = start_box * (1.0 - frac) + obs_xyxy * frac
            tlwh = np.array([interp_xyxy[0], interp_xyxy[1], max(1.0, interp_xyxy[2] - interp_xyxy[0]), max(1.0, interp_xyxy[3] - interp_xyxy[1])], dtype=np.float32)
            self.mean, self.covariance = self.kalman_filter.predict(self.mean, self.covariance)
            self.mean, self.covariance = self.kalman_filter.update(self.mean, self.covariance, _tlwh_to_xyah(tlwh))

    def mark_lost(self):
        if self.state != TrackState.Lost and self.mean is not None:
            self._saved_mean = self.mean.copy()
            self._saved_cov = self.covariance.copy()
        super().mark_lost()

    def update(self, new_track: OCSortTrack, frame_id: int):
        self._oru_replay(new_track.xyxy, frame_id)
        self._record_observation(new_track.xyxy, frame_id)
        self._saved_mean = None
        self._saved_cov = None
        super().update(new_track, frame_id)

    def re_activate(self, new_track: OCSortTrack, frame_id: int, new_id: Optional[int] = None):
        self._oru_replay(new_track.xyxy, frame_id)
        self._record_observation(new_track.xyxy, frame_id)
        self._saved_mean = None
        self._saved_cov = None
        super().re_activate(new_track, frame_id, new_id=new_id)


class GenuineOCSortTracker:
    """OC-SORT with OCM momentum cost, ORU virtual re-update, and OCR last-observation recovery."""

    def __init__(
        self,
        track_high_thresh: float = 0.45,
        track_low_thresh: float = 0.15,
        new_track_thresh: float = 0.45,
        track_buffer: int = 75,
        match_thresh: float = 0.80,
        inertia: float = 0.20,
        delta_t: int = 3,
    ):
        self.track_high_thresh = float(track_high_thresh)
        self.track_low_thresh = float(track_low_thresh)
        self.new_track_thresh = float(new_track_thresh)
        self.max_time_lost = int(track_buffer)
        self.match_thresh = float(match_thresh)
        self.inertia = float(inertia)
        self.delta_t = int(delta_t)
        self.kalman_filter = KalmanFilterXYAH()
        self.reset()

    def reset(self):
        self.tracked_stracks: List[OCSortTrack] = []
        self.lost_stracks: List[OCSortTrack] = []
        self.removed_stracks: List[OCSortTrack] = []
        self.frame_id = 0
        self._next_id = 1

    def _alloc_id(self) -> int:
        tid = self._next_id
        self._next_id += 1
        return tid

    def _ocm_cost(self, tracks: List[OCSortTrack], dets: List[OCSortTrack]) -> np.ndarray:
        if not tracks or not dets:
            return np.zeros((len(tracks), len(dets)), dtype=np.float32)
        t_boxes = np.asarray([t.xyxy for t in tracks], dtype=np.float32)
        d_boxes = np.asarray([d.xyxy for d in dets], dtype=np.float32)
        ious = iou_batch(t_boxes, d_boxes)
        dists = 1.0 - ious

        # Observation-Centric Momentum (angle alignment bonus)
        for i, trk in enumerate(tracks):
            for j, det in enumerate(dets):
                if trk.cls_id != det.cls_id:
                    dists[i, j] = 1.0
                    continue
                if trk.velocity is not None and trk.last_observation[0] >= 0:
                    d_vec = OCSortTrack._box_center_xyxy(det.xyxy) - OCSortTrack._box_center_xyxy(trk.last_observation)
                    nrm = float(np.linalg.norm(d_vec))
                    if nrm > 1e-3:
                        cos_ang = float(np.clip(np.dot(trk.velocity, d_vec / nrm), -1.0, 1.0))
                        ang_diff = np.arccos(cos_ang) / np.pi  # [0, 1]
                        dists[i, j] = max(0.0, dists[i, j] + self.inertia * (ang_diff - 0.5) * float(det.score))
        return dists

    def update(self, detections: List[Dict[str, Any]], frame: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
        self.frame_id += 1
        activated, refind, lost, removed = [], [], [], []
        high_dets, low_dets = [], []
        for d in detections:
            conf = float(d.get("confidence", 0.0))
            if conf < self.track_low_thresh:
                continue
            tr = OCSortTrack(
                np.array([d["x1"], d["y1"], d["x2"], d["y2"]], dtype=np.float32),
                conf,
                int(d.get("class_id", 0)),
                str(d.get("class_name", "object")),
                delta_t=self.delta_t,
            )
            (high_dets if conf >= self.track_high_thresh else low_dets).append(tr)

        unconfirmed, tracked_stracks = [], []
        for t in self.tracked_stracks:
            (tracked_stracks if t.is_activated else unconfirmed).append(t)

        strack_pool = _joint_stracks(tracked_stracks, self.lost_stracks)
        OCSortTrack.multi_predict(strack_pool)

        # Stage 1: OCM high-confidence association
        dists = self._ocm_cost(strack_pool, high_dets)
        matches, u_track, u_det = linear_assignment(dists, thresh=self.match_thresh)
        for itracked, idet in matches:
            trk = strack_pool[itracked]
            if trk.state == TrackState.Tracked:
                trk.update(high_dets[idet], self.frame_id)
                activated.append(trk)
            else:
                trk.re_activate(high_dets[idet], self.frame_id)
                refind.append(trk)

        # Stage 2: ByteTrack low-conf + OCR (Observation-Centric Recovery via last_observation)
        r_tracked = [strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked]
        rem_high = [high_dets[i] for i in u_det]
        # OCR first tries matching remaining high detections against lost/unmatched last_observation
        if r_tracked and rem_high:
            obs_boxes = np.asarray([t.last_observation if t.last_observation[0] >= 0 else t.xyxy for t in r_tracked], dtype=np.float32)
            det_boxes = np.asarray([d.xyxy for d in rem_high], dtype=np.float32)
            ocr_dists = 1.0 - iou_batch(obs_boxes, det_boxes)
            for i, trk in enumerate(r_tracked):
                for j, det in enumerate(rem_high):
                    if trk.cls_id != det.cls_id:
                        ocr_dists[i, j] = 1.0
            m_ocr, u_tr_ocr, u_det_ocr = linear_assignment(ocr_dists, thresh=0.70)
            for itracked, idet in m_ocr:
                r_tracked[itracked].update(rem_high[idet], self.frame_id)
                activated.append(r_tracked[itracked])
            r_tracked = [r_tracked[i] for i in u_tr_ocr]
            rem_high = [rem_high[i] for i in u_det_ocr]

        if r_tracked and low_dets:
            d2 = self._ocm_cost(r_tracked, low_dets)
            m2, u_tr2, _ = linear_assignment(d2, thresh=0.50)
            for itracked, idet in m2:
                r_tracked[itracked].update(low_dets[idet], self.frame_id)
                activated.append(r_tracked[itracked])
            r_tracked = [r_tracked[i] for i in u_tr2]

        for trk in r_tracked:
            if trk.state != TrackState.Lost:
                trk.mark_lost()
                lost.append(trk)

        d3 = self._ocm_cost(unconfirmed, rem_high)
        m3, u_unconf, u_det3 = linear_assignment(d3, thresh=0.70)
        for itracked, idet in m3:
            unconfirmed[itracked].update(rem_high[idet], self.frame_id)
            activated.append(unconfirmed[itracked])
        for it in u_unconf:
            unconfirmed[it].mark_removed()
            removed.append(unconfirmed[it])

        for inew in u_det3:
            trk = rem_high[inew]
            if trk.score >= self.new_track_thresh:
                trk.activate(self.kalman_filter, self.frame_id, self._alloc_id())
                activated.append(trk)

        for trk in self.lost_stracks:
            if self.frame_id - trk.end_frame > self.max_time_lost:
                trk.mark_removed()
                removed.append(trk)

        self.tracked_stracks = [t for t in self.tracked_stracks if t.state == TrackState.Tracked]
        self.tracked_stracks = _joint_stracks(self.tracked_stracks, activated)
        self.tracked_stracks = _joint_stracks(self.tracked_stracks, refind)
        self.lost_stracks = _sub_stracks(self.lost_stracks, self.tracked_stracks)
        self.lost_stracks.extend(lost)
        self.lost_stracks = _sub_stracks(self.lost_stracks, self.removed_stracks)
        self.tracked_stracks, self.lost_stracks = _remove_duplicate_stracks(self.tracked_stracks, self.lost_stracks)
        self.removed_stracks.extend(removed)
        if len(self.removed_stracks) > 1000:
            self.removed_stracks = self.removed_stracks[-1000:]

        fh, fw = (frame.shape[:2] if frame is not None else (None, None))
        out = []
        for trk in self.tracked_stracks:
            if not trk.is_activated:
                continue
            bx1, by1, bx2, by2 = trk.xyxy
            if fw is not None and fh is not None:
                bx1 = max(0, min(fw, int(round(bx1))))
                by1 = max(0, min(fh, int(round(by1))))
                bx2 = max(0, min(fw, int(round(bx2))))
                by2 = max(0, min(fh, int(round(by2))))
            else:
                bx1, by1, bx2, by2 = int(round(bx1)), int(round(by1)), int(round(bx2)), int(round(by2))
            if (bx2 - bx1) < 4 or (by2 - by1) < 4:
                continue
            out.append({
                "class_id": trk.cls_id,
                "class_name": trk.cls_name,
                "confidence": round(float(trk.score), 4),
                "x1": bx1,
                "y1": by1,
                "x2": bx2,
                "y2": by2,
                "track_id": int(trk.track_id),
                "confirmed": True,
            })
        return out

