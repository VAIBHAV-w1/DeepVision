"""
Genuine ByteTrack Multi-Object Tracker (Zhang et al., ECCV 2022).
Per-instance ID counter guarantees isolated track namespaces across multiple cameras.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from apps.surveillance.ai.trackers.kalman import KalmanFilterXYAH
from apps.surveillance.ai.trackers.matching import iou_batch, linear_assignment


class TrackState:
    New = 0
    Tracked = 1
    Lost = 2
    Removed = 3


class _BaseTrack:
    def __init__(self):
        self.track_id = 0
        self.is_activated = False
        self.state = TrackState.New
        self.frame_id = 0
        self.start_frame = 0
        self.tracklet_len = 0

    @property
    def end_frame(self) -> int:
        return self.frame_id

    def mark_lost(self):
        self.state = TrackState.Lost

    def mark_removed(self):
        self.state = TrackState.Removed


def _xyxy_to_tlwh(box: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
    return np.array([x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)], dtype=np.float32)


def _tlwh_to_xyah(tlwh: np.ndarray) -> np.ndarray:
    ret = np.asarray(tlwh, dtype=np.float64).copy()
    ret[:2] += ret[2:] / 2.0
    ret[2] = ret[2] / max(1.0, ret[3])
    return ret


class STrack(_BaseTrack):
    shared_kalman = KalmanFilterXYAH()

    def __init__(self, xyxy: np.ndarray, score: float, cls_id: int, cls_name: str):
        super().__init__()
        self._tlwh = _xyxy_to_tlwh(xyxy)
        self.score = float(score)
        self.cls_id = int(cls_id)
        self.cls_name = str(cls_name)
        self.kalman_filter: Optional[KalmanFilterXYAH] = None
        self.mean: Optional[np.ndarray] = None
        self.covariance: Optional[np.ndarray] = None

    @property
    def tlwh(self) -> np.ndarray:
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[2] *= ret[3]
        ret[:2] -= ret[2:] / 2.0
        return ret.astype(np.float32)

    @property
    def xyxy(self) -> np.ndarray:
        t = self.tlwh
        return np.array([t[0], t[1], t[0] + t[2], t[1] + t[3]], dtype=np.float32)

    @staticmethod
    def multi_predict(stracks: List[STrack]):
        if not stracks:
            return
        means = np.asarray([st.mean.copy() for st in stracks], dtype=np.float64)
        covs = np.asarray([st.covariance for st in stracks], dtype=np.float64)
        for i, st in enumerate(stracks):
            if st.state != TrackState.Tracked:
                means[i][7] = 0.0
        means, covs = STrack.shared_kalman.multi_predict(means, covs)
        for i, st in enumerate(stracks):
            st.mean = means[i]
            st.covariance = covs[i]

    def activate(self, kalman_filter: KalmanFilterXYAH, frame_id: int, track_id: int):
        self.kalman_filter = kalman_filter
        self.track_id = int(track_id)
        self.mean, self.covariance = self.kalman_filter.initiate(_tlwh_to_xyah(self._tlwh))
        self.tracklet_len = 0
        self.state = TrackState.Tracked
        self.is_activated = frame_id == 1
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track: STrack, frame_id: int, new_id: Optional[int] = None):
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, _tlwh_to_xyah(new_track.tlwh)
        )
        self.tracklet_len = 0
        self.state = TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        if new_id is not None:
            self.track_id = int(new_id)
        self.score = new_track.score
        self.cls_id = new_track.cls_id
        self.cls_name = new_track.cls_name

    def update(self, new_track: STrack, frame_id: int):
        self.frame_id = frame_id
        self.tracklet_len += 1
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, _tlwh_to_xyah(new_track.tlwh)
        )
        self.state = TrackState.Tracked
        self.is_activated = True
        self.score = new_track.score
        self.cls_id = new_track.cls_id
        self.cls_name = new_track.cls_name


def _joint_stracks(tlista: List[STrack], tlistb: List[STrack]) -> List[STrack]:
    exists = {t.track_id: True for t in tlista}
    res = list(tlista)
    for t in tlistb:
        if t.track_id not in exists:
            exists[t.track_id] = True
            res.append(t)
    return res


def _sub_stracks(tlista: List[STrack], tlistb: List[STrack]) -> List[STrack]:
    b_ids = {t.track_id for t in tlistb}
    return [t for t in tlista if t.track_id not in b_ids]


def _remove_duplicate_stracks(stracksa: List[STrack], stracksb: List[STrack]):
    if not stracksa or not stracksb:
        return stracksa, stracksb
    pdist = 1.0 - iou_batch(
        np.asarray([t.xyxy for t in stracksa]),
        np.asarray([t.xyxy for t in stracksb]),
    )
    pairs = np.where(pdist < 0.15)
    dupa, dupb = set(), set()
    for p, q in zip(*pairs):
        if stracksa[p].cls_id != stracksb[q].cls_id:
            continue
        timep = stracksa[p].frame_id - stracksa[p].start_frame
        timeq = stracksb[q].frame_id - stracksb[q].start_frame
        if timep >= timeq:
            dupb.add(q)
        else:
            dupa.add(p)
    return [t for i, t in enumerate(stracksa) if i not in dupa], [t for i, t in enumerate(stracksb) if i not in dupb]


def _iou_distance_class_gated(atracks: List[STrack], btracks: List[STrack], fuse_score: bool = False) -> np.ndarray:
    if not atracks or not btracks:
        return np.zeros((len(atracks), len(btracks)), dtype=np.float32)
    ious = iou_batch(
        np.asarray([t.xyxy for t in atracks], dtype=np.float32),
        np.asarray([t.xyxy for t in btracks], dtype=np.float32),
    )
    if fuse_score:
        scores = np.asarray([b.score for b in btracks], dtype=np.float32)[None, :]
        ious = ious * scores
    dists = 1.0 - ious
    for i, a in enumerate(atracks):
        for j, b in enumerate(btracks):
            if a.cls_id != b.cls_id:
                dists[i, j] = 1.0
    return dists


class GenuineByteTracker:
    """Two-stage ByteTrack association with per-tracker track ID namespace."""

    def __init__(
        self,
        track_high_thresh: float = 0.45,
        track_low_thresh: float = 0.15,
        new_track_thresh: float = 0.45,
        track_buffer: int = 75,
        match_thresh: float = 0.80,
        fuse_score: bool = True,
    ):
        self.track_high_thresh = float(track_high_thresh)
        self.track_low_thresh = float(track_low_thresh)
        self.new_track_thresh = float(new_track_thresh)
        self.max_time_lost = int(track_buffer)
        self.match_thresh = float(match_thresh)
        self.fuse_score = bool(fuse_score)
        self.kalman_filter = KalmanFilterXYAH()
        self.reset()

    def reset(self):
        self.tracked_stracks: List[STrack] = []
        self.lost_stracks: List[STrack] = []
        self.removed_stracks: List[STrack] = []
        self.frame_id = 0
        self._next_id = 1

    def _alloc_id(self) -> int:
        tid = self._next_id
        self._next_id += 1
        return tid

    def update(self, detections: List[Dict[str, Any]], frame: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
        self.frame_id += 1
        activated, refind, lost, removed = [], [], [], []

        high_dets: List[STrack] = []
        low_dets: List[STrack] = []
        for d in detections:
            conf = float(d.get("confidence", 0.0))
            if conf < self.track_low_thresh:
                continue
            st = STrack(
                np.array([d["x1"], d["y1"], d["x2"], d["y2"]], dtype=np.float32),
                conf,
                int(d.get("class_id", 0)),
                str(d.get("class_name", "object")),
            )
            if conf >= self.track_high_thresh:
                high_dets.append(st)
            else:
                low_dets.append(st)

        unconfirmed: List[STrack] = []
        tracked_stracks: List[STrack] = []
        for trk in self.tracked_stracks:
            if not trk.is_activated:
                unconfirmed.append(trk)
            else:
                tracked_stracks.append(trk)

        strack_pool = _joint_stracks(tracked_stracks, self.lost_stracks)
        STrack.multi_predict(strack_pool)

        # Stage 1: High-confidence association
        dists = _iou_distance_class_gated(strack_pool, high_dets, fuse_score=self.fuse_score)
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

        # Stage 2: Low-confidence ByteTrack rescue on active tracks only
        r_tracked = [strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked]
        dists2 = _iou_distance_class_gated(r_tracked, low_dets, fuse_score=False)
        matches2, u_track2, _ = linear_assignment(dists2, thresh=0.50)
        for itracked, idet in matches2:
            trk = r_tracked[itracked]
            det = low_dets[idet]
            if trk.state == TrackState.Tracked:
                trk.update(det, self.frame_id)
                activated.append(trk)

        for it in u_track2:
            trk = r_tracked[it]
            if trk.state != TrackState.Lost:
                trk.mark_lost()
                lost.append(trk)

        # Unconfirmed match
        rem_dets = [high_dets[i] for i in u_det]
        dists3 = _iou_distance_class_gated(unconfirmed, rem_dets, fuse_score=self.fuse_score)
        matches3, u_unconf, u_det3 = linear_assignment(dists3, thresh=0.70)
        for itracked, idet in matches3:
            unconfirmed[itracked].update(rem_dets[idet], self.frame_id)
            activated.append(unconfirmed[itracked])
        for it in u_unconf:
            trk = unconfirmed[it]
            trk.mark_removed()
            removed.append(trk)

        # Spawn new tracks
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

