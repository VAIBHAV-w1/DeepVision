"""
Standard 8-State Constant-Velocity Kalman Filters for ByteTrack (XYAH) and BoT-SORT (XYWH).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


class _BaseKalmanFilter:
    """Shared constant-velocity 8-D Kalman predict/update primitives."""

    def __init__(self, ndim: int = 4):
        self.ndim = ndim
        self._motion_mat = np.eye(2 * ndim, dtype=np.float64)
        for i in range(ndim):
            self._motion_mat[i, ndim + i] = 1.0
        self._update_mat = np.eye(ndim, 2 * ndim, dtype=np.float64)
        self._std_weight_position = 1.0 / 20.0
        self._std_weight_velocity = 1.0 / 160.0

    def _init_std(self, measurement: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def _step_std(self, mean: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def _meas_std(self, mean: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def initiate(self, measurement: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        mean_pos = np.asarray(measurement, dtype=np.float64)
        mean = np.r_[mean_pos, np.zeros_like(mean_pos)]
        std_pos, std_vel = self._init_std(mean_pos)
        std = np.r_[std_pos, std_vel]
        return mean, np.diag(np.square(std))

    def predict(self, mean: np.ndarray, covariance: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        std_pos, std_vel = self._step_std(mean)
        motion_cov = np.diag(np.square(np.r_[std_pos, std_vel]))
        next_mean = self._motion_mat @ mean
        next_cov = self._motion_mat @ covariance @ self._motion_mat.T + motion_cov
        return next_mean, next_cov

    def multi_predict(self, means: np.ndarray, covariances: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        if len(means) == 0:
            return means, covariances
        out_m = np.empty_like(means)
        out_c = np.empty_like(covariances)
        for idx in range(len(means)):
            out_m[idx], out_c[idx] = self.predict(means[idx], covariances[idx])
        return out_m, out_c

    def update(self, mean: np.ndarray, covariance: np.ndarray, measurement: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        proj_mean = self._update_mat @ mean
        innovation_cov = self._update_mat @ covariance @ self._update_mat.T + np.diag(np.square(self._meas_std(mean)))
        kalman_gain = np.linalg.solve(innovation_cov.T, (covariance @ self._update_mat.T).T).T
        innovation = np.asarray(measurement, dtype=np.float64) - proj_mean
        new_mean = mean + innovation @ kalman_gain.T
        new_cov = covariance - kalman_gain @ innovation_cov @ kalman_gain.T
        return new_mean, new_cov


class KalmanFilterXYAH(_BaseKalmanFilter):
    """[cx, cy, aspect_ratio, height, vx, vy, va, vh] Kalman filter used by ByteTrack & OC-SORT."""

    def _init_std(self, m: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        h = max(1.0, float(m[3]))
        return (
            np.array([2 * self._std_weight_position * h, 2 * self._std_weight_position * h, 1e-2, 2 * self._std_weight_position * h]),
            np.array([10 * self._std_weight_velocity * h, 10 * self._std_weight_velocity * h, 1e-5, 10 * self._std_weight_velocity * h]),
        )

    def _step_std(self, m: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        h = max(1.0, float(m[3]))
        return (
            np.array([self._std_weight_position * h, self._std_weight_position * h, 1e-2, self._std_weight_position * h]),
            np.array([self._std_weight_velocity * h, self._std_weight_velocity * h, 1e-5, self._std_weight_velocity * h]),
        )

    def _meas_std(self, m: np.ndarray) -> np.ndarray:
        h = max(1.0, float(m[3]))
        return np.array([self._std_weight_position * h, self._std_weight_position * h, 1e-1, self._std_weight_position * h])


class KalmanFilterXYWH(_BaseKalmanFilter):
    """[cx, cy, width, height, vx, vy, vw, vh] Kalman filter used by BoT-SORT."""

    def _init_std(self, m: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        w, h = max(1.0, float(m[2])), max(1.0, float(m[3]))
        return (
            np.array([2 * self._std_weight_position * w, 2 * self._std_weight_position * h, 2 * self._std_weight_position * w, 2 * self._std_weight_position * h]),
            np.array([10 * self._std_weight_velocity * w, 10 * self._std_weight_velocity * h, 10 * self._std_weight_velocity * w, 10 * self._std_weight_velocity * h]),
        )

    def _step_std(self, m: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        w, h = max(1.0, float(m[2])), max(1.0, float(m[3]))
        return (
            np.array([self._std_weight_position * w, self._std_weight_position * h, self._std_weight_position * w, self._std_weight_position * h]),
            np.array([self._std_weight_velocity * w, self._std_weight_velocity * h, self._std_weight_velocity * w, self._std_weight_velocity * h]),
        )

    def _meas_std(self, m: np.ndarray) -> np.ndarray:
        w, h = max(1.0, float(m[2])), max(1.0, float(m[3]))
        return np.array([self._std_weight_position * w, self._std_weight_position * h, self._std_weight_position * w, self._std_weight_position * h])

