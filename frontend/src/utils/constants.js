/**
 * DeepVision Constants
 */

export const STREAM_MODES = {
  ORIGINAL: 'raw',
  TRACKING_DETECTION: 'tracking',
};

export const STREAM_MODE_LABELS = {
  raw: 'ORIGINAL',
  tracking: 'TRACKING + DETECTION',
};

export const SEVERITY_COLORS = {
  low: 'info',
  medium: 'warning',
  high: 'danger',
  critical: 'critical',
};

export const STATUS_COLORS = {
  online: 'success',
  offline: 'danger',
  active: 'success',
  inactive: 'secondary',
  new: 'danger',
  acknowledged: 'warning',
  resolved: 'success',
  open: 'primary',
  closed: 'secondary',
};
