import React from 'react';

export function StatusBadge({ status, type = 'status' }) {
  const norm = String(status || '').toLowerCase().trim();

  let badgeClass = 'badge-secondary';
  let dotClass = '';
  let label = status;

  if (['online', 'active', 'healthy', 'resolved', 'completed'].includes(norm)) {
    badgeClass = 'badge-live';
    dotClass = 'status-indicator live';
    label = norm === 'online' ? 'LIVE' : status;
  } else if (['offline', 'inactive', 'unhealthy', 'failed', 'critical'].includes(norm)) {
    badgeClass = 'badge-offline';
    dotClass = 'status-indicator offline';
    label = norm === 'offline' ? 'OFFLINE' : status;
  } else if (['new', 'open', 'high'].includes(norm)) {
    badgeClass = 'badge-danger';
    dotClass = 'status-indicator offline';
  } else if (['acknowledged', 'warning', 'medium', 'recording'].includes(norm)) {
    badgeClass = 'badge-warn';
    dotClass = 'status-indicator warn';
  } else if (['low', 'info'].includes(norm)) {
    badgeClass = 'badge-info';
  }

  return (
    <span className={`cctv-status-badge ${badgeClass}`}>
      {dotClass && <span className={dotClass}></span>}
      <span className="badge-text">{label}</span>
    </span>
  );
}

export default StatusBadge;
