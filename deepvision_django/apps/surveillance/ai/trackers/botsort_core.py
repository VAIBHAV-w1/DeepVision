"""
Genuine BoT-SORT Multi-Object Tracker with GMC + Appearance Re-ID (Aharon et al., 2022).
Uses KalmanFilterXYWH, Sparse Optical Flow Global Motion Compensation, and
EMA cosine appearance affinity fused with IoU proximity gating.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

import numpy as np

from apps.surveillance.ai.trackers.bytetrack_core import (
    TrackState,
    _BaseTrack,
    _joint_stracks,
    _remove_duplicate_stracks,
    _sub_stracks,
)
from apps.surveillance.ai.trackers.gmc import SparseOptFlowGMC
from apps.surveillance.ai.trackers.kalman import KalmanFilterXYWH
from apps.surveillance.ai.trackers.matching import (
    cosine_distance_matrix,
    extract_reid_embedding,
    iou_batch,
    linear_assignment,
)


def _xyxy_to_tlwh(box: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
    return np.array([x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)], dtype=np.float32)


def _tlwh_to_xywh(tlwh: np.ndarray) -> np.ndarray:
    ret = np.asarray(tlwh, dtype=np.float64).copy()
    ret[:2] += ret[2:] / 2.0
    return ret


class BOTrack(_BaseTrack):
    shared_kalman = KalmanFilterXYWH()

    def __init__(self, xyxy: np.ndarray, score: float, cls_id: int, cls_name: str, feat: Optional[np.ndarray] = None, feat_history: int = 30):
        super().__init__()
        self._tlwh = _xyxy_to_tlwh(xyxy)
        self.score = float(score)
        self.cls_id = int(cls_id)
        self.cls_name = str(cls_name)
        self.kalman_filter: Optional[KalmanFilterXYWH] = None
        self.mean: Optional[np.ndarray] = None
        self.covariance: Optional[np.ndarray] = None
        self.alpha = 0.9
        self.smooth_feat: Optional[np.ndarray] = None
        self.curr_feat: Optional[np.ndarray] = None
        self.total_hits: int = 1
        self.features = deque(maxlen=feat_history)
        if feat is not None:
            self.update_features(feat)

    def update_features(self, feat: Optional[np.ndarray]):
        if feat is None:
            return
        n = float(np.linalg.norm(feat))
        if n <= 1e-6:
            return
        feat = feat / n
        self.curr_feat = feat
        if self.smooth_feat is None:
            self.smooth_feat = feat
        else:
            self.smooth_feat = self.alpha * self.smooth_feat + (1.0 - self.alpha) * feat
            sn = float(np.linalg.norm(self.smooth_feat))
            if sn > 1e-6:
                self.smooth_feat /= sn
        self.features.append(feat)

    @property
    def tlwh(self) -> np.ndarray:
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[:2] -= ret[2:] / 2.0
        return ret.astype(np.float32)

    @property
    def xyxy(self) -> np.ndarray:
        t = self.tlwh
        return np.array([t[0], t[1], t[0] + t[2], t[1] + t[3]], dtype=np.float32)

    @staticmethod
    def multi_predict(tracks: List[BOTrack]):
        if not tracks:
            return
        means = np.asarray([t.mean.copy() for t in tracks], dtype=np.float64)
        covs = np.asarray([t.covariance for t in tracks], dtype=np.float64)
        for i, t in enumerate(tracks):
            if t.state != TrackState.Tracked:
                means[i][6] = 0.0
                means[i][7] = 0.0
        means, covs = BOTrack.shared_kalman.multi_predict(means, covs)
        for i, t in enumerate(tracks):
            t.mean = means[i]
            t.covariance = covs[i]

    @staticmethod
    def multi_gmc(tracks: List[BOTrack], H: np.ndarray):
        if not tracks or H is None:
            return
        R = H[:2, :2].astype(np.float64)
        R8x8 = np.kron(np.eye(4, dtype=np.float64), R)
        t = H[:2, 2].astype(np.float64)
        for trk in tracks:
            if trk.mean is None:
                continue
            mean = R8x8 @ trk.mean
            mean[:2] += t
            trk.mean = mean
            trk.covariance = R8x8 @ trk.covariance @ R8x8.T

    def activate(self, kf: KalmanFilterXYWH, frame_id: int, track_id: int):
        self.kalman_filter = kf
        self.track_id = int(track_id)
        self.mean, self.covariance = self.kalman_filter.initiate(_tlwh_to_xywh(self._tlwh))
        self.tracklet_len = 0
        self.state = TrackState.Tracked
        self.is_activated = frame_id == 1
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track: BOTrack, frame_id: int):
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, _tlwh_to_xywh(new_track.tlwh)
        )
        if new_track.curr_feat is not None:
            self.update_features(new_track.curr_feat)
        self.tracklet_len = 0
        self.total_hits += 1
        self.state = TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        self.score = new_track.score

    def update(self, new_track: BOTrack, frame_id: int):
        self.frame_id = frame_id
        self.tracklet_len += 1
        self.total_hits += 1
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, _tlwh_to_xywh(new_track.tlwh)
        )
        if new_track.curr_feat is not None:
            self.update_features(new_track.curr_feat)
        self.state = TrackState.Tracked
        self.is_activated = True
        self.score = new_track.score


class GenuineBotSortTracker:
    """BoT-SORT with GMC camera stabilization + appearance Re-ID cosine-IoU fusion."""

    def __init__(
        self,
        track_high_thresh: float = 0.45,
        track_low_thresh: float = 0.15,
        new_track_thresh: float = 0.45,
        track_buffer: int = 75,
        match_thresh: float = 0.80,
        proximity_thresh: float = 0.50,
        appearance_thresh: float = 0.25,
        with_reid: bool = True,
        use_gmc: bool = True,
    ):
        self.track_high_thresh = float(track_high_thresh)
        self.track_low_thresh = float(track_low_thresh)
        self.new_track_thresh = float(new_track_thresh)
        self.max_time_lost = int(track_buffer)
        self.match_thresh = float(match_thresh)
        self.proximity_thresh = float(proximity_thresh)
        self.appearance_thresh = float(appearance_thresh)
        self.with_reid = bool(with_reid)
        self.use_gmc = bool(use_gmc)
        self.kalman_filter = KalmanFilterXYWH()
        self.gmc = SparseOptFlowGMC(downscale=4) if self.use_gmc else None
        self.reset()

    def reset(self):
        self.tracked_stracks: List[BOTrack] = []
        self.lost_stracks: List[BOTrack] = []
        self.removed_stracks: List[BOTrack] = []
        self.frame_id = 0
        self._next_id = 1
        if self.gmc is not None:
            self.gmc.reset()

    def _alloc_id(self) -> int:
        tid = self._next_id
        self._next_id += 1
        return tid

    def _fused_cost(self, atracks: List[BOTrack], btracks: List[BOTrack], use_reid: bool = True) -> np.ndarray:
        if not atracks or not btracks:
            return np.zeros((len(atracks), len(btracks)), dtype=np.float32)
        ious = iou_batch(
            np.asarray([t.xyxy for t in atracks], dtype=np.float32),
            np.asarray([t.xyxy for t in btracks], dtype=np.float32),
        )
        iou_dists = 1.0 - ious
        iou_mask = iou_dists > self.proximity_thresh

        if use_reid and self.with_reid:
            emb_dists = cosine_distance_matrix(atracks, btracks) / 2.0
            emb_dists[emb_dists > self.appearance_thresh] = 1.0
            emb_dists[iou_mask] = 1.0
            dists = np.minimum(iou_dists, emb_dists)
        else:
            dists = iou_dists

        for i, a in enumerate(atracks):
            for j, b in enumerate(btracks):
                if a.cls_id != b.cls_id:
                    dists[i, j] = 1.0
        return dists

    def update(self, detections: List[Dict[str, Any]], frame: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
        self.frame_id += 1
        activated, refind, lost, removed = [], [], [], []

        high_dets: List[BOTrack] = []
        low_dets: List[BOTrack] = []
        for d in detections:
            conf = float(d.get("confidence", 0.0))
            if conf < self.track_low_thresh:
                continue
            cid = int(d.get("class_id", 0))
            box = np.array([d["x1"], d["y1"], d["x2"], d["y2"]], dtype=np.float32)
            # Extract Re-ID embeddings on people and carried luggage (0, 24, 26, 28) at high conf
            feat = (
                extract_reid_embedding(frame, (int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"])))
                if (self.with_reid and conf >= self.track_high_thresh and cid in (0, 24, 26, 28))
                else None
            )
            tr = BOTrack(box, conf, cid, str(d.get("class_name", "object")), feat=feat)
            if conf >= self.track_high_thresh:
                high_dets.append(tr)
            else:
                low_dets.append(tr)

        unconfirmed, tracked_stracks = [], []
        for t in self.tracked_stracks:
            (tracked_stracks if t.is_activated else unconfirmed).append(t)

        strack_pool = _joint_stracks(tracked_stracks, self.lost_stracks)
        BOTrack.multi_predict(strack_pool)
        if self.use_gmc and self.gmc is not None and frame is not None and strack_pool:
            warp = self.gmc.apply(frame)
            BOTrack.multi_gmc(strack_pool, warp)
            BOTrack.multi_gmc(unconfirmed, warp)

        dists = self._fused_cost(strack_pool, high_dets, use_reid=True)
        matches, u_track, u_det = linear_assignment(dists, thresh=self.match_thresh)
        for itracked, idet in matches:
            trk = strack_pool[itracked]
            det = high_dets[idet]
            if trk.state == TrackState.Tracked:
                trk.update(det, self.frame_id)
                activated.append(trk)
            else:
                trk.re_activate(det, self.frame_id)
                refind.append(trk)

        r_tracked = [strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked]
        dists2 = self._fused_cost(r_tracked, low_dets, use_reid=False)
        matches2, u_track2, u_low2 = linear_assignment(dists2, thresh=0.50)
        for itracked, idet in matches2:
            trk = r_tracked[itracked]
            if trk.state == TrackState.Tracked:
                trk.update(low_dets[idet], self.frame_id)
                activated.append(trk)
        for it in u_track2:
            trk = r_tracked[it]
            if trk.state != TrackState.Lost:
                trk.mark_lost()
                lost.append(trk)

        # Stage 2b: Recover recently lost established tracks against moderate low-conf detections (>= 0.30)
        rem_low_dets = [low_dets[i] for i in u_low2 if low_dets[i].score >= 0.30]
        rec_lost_tracks = [
            strack_pool[i] for i in u_track
            if strack_pool[i].state == TrackState.Lost
            and strack_pool[i].is_activated
            and (self.frame_id - strack_pool[i].end_frame) <= 10
            and strack_pool[i].total_hits >= 4
        ]
        if rec_lost_tracks and rem_low_dets:
            dists2b = self._fused_cost(rec_lost_tracks, rem_low_dets, use_reid=False)
            matches2b, _, _ = linear_assignment(dists2b, thresh=0.45)
            for itracked, idet in matches2b:
                trk = rec_lost_tracks[itracked]
                trk.re_activate(rem_low_dets[idet], self.frame_id)
                refind.append(trk)

        rem_dets = [high_dets[i] for i in u_det]
        dists3 = self._fused_cost(unconfirmed, rem_dets, use_reid=True)
        matches3, u_unconf, u_det3 = linear_assignment(dists3, thresh=0.70)
        for itracked, idet in matches3:
            unconfirmed[itracked].update(rem_dets[idet], self.frame_id)
            activated.append(unconfirmed[itracked])
        for it in u_unconf:
            unconfirmed[it].mark_removed()
            removed.append(unconfirmed[it])

        for inew in u_det3:
            trk = rem_dets[inew]
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
