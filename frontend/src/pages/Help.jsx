import React from 'react';
import { useTranslation } from '../i18n/i18nContext';

/**
 * DeepVision Help — Clear, practical guidance written for everyday operators
 */
export function Help({ onNavigate }) {
  const { t } = useTranslation();

  const cards = [
    {
      title: t('help.monitorGuide', 'How to Monitor Live Cameras'),
      body: t(
        'help.monitorGuideText',
        'Open Cameras and choose a camera to view its live feed. Switch between RAW STREAM and DETECTION & TRACKING from the camera controls.'
      ),
      actionLabel: 'Open Cameras →',
      targetPage: 'cameras',
      accentBg: 'rgba(0, 229, 255, 0.12)',
      accentColor: 'var(--dv-cyan-500, #00E5FF)',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
          <line x1="8" y1="21" x2="16" y2="21" />
          <line x1="12" y1="17" x2="12" y2="21" />
        </svg>
      ),
    },
    {
      title: 'Managing Hardware & IP Cameras',
      body: 'Open Cameras to register USB/DirectShow webcams, RTSP/ONVIF cameras, or mobile IP streams, run live connection diagnostics, edit locations, or remove retired sensors.',
      actionLabel: 'Manage Cameras →',
      targetPage: 'cameras',
      accentBg: 'rgba(56, 189, 248, 0.12)',
      accentColor: '#38BDF8',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
      ),
    },
    {
      title: t('help.recordingsGuide', 'Finding Recordings & Evidence'),
      body: t(
        'help.recordingsGuideText',
        'Open Recordings for archived MP4 video clips and manual captures, or Evidence for forensic snapshots and SHA-256 verified artifacts. Filter by camera, type, or search terms.'
      ),
      actionLabel: 'Browse Recordings →',
      targetPage: 'recordings',
      accentBg: 'rgba(0, 230, 118, 0.12)',
      accentColor: 'var(--dv-status-online, #00E676)',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="5 3 19 12 5 21 5 3" />
        </svg>
      ),
    },
    {
      title: t('help.alertsGuide', 'Responding to Security Alerts & Cases'),
      body: t(
        'help.alertsGuideText',
        'Open Notifications and choose View Incident to inspect the event, camera, and available evidence. From the incident, create or review its linked investigation case.'
      ),
      actionLabel: 'Open Notifications →',
      targetPage: 'notifications',
      accentBg: 'rgba(255, 179, 0, 0.12)',
      accentColor: 'var(--dv-status-warning, #FFB300)',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
    },
    {
      title: 'Drawing Restricted Perimeter Zones',
      body: 'In Cameras, choose a camera and switch to DETECTION & TRACKING. Use its zone controls to define restricted boundaries for that camera.',
      actionLabel: 'Open Cameras →',
      targetPage: 'cameras',
      accentBg: 'rgba(244, 63, 94, 0.12)',
      accentColor: '#F43F5E',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="4 2" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      ),
    },
    {
      title: 'Detection Sensitivity, Themes & Languages',
      body: 'Open Settings to adjust YOLO11n detection confidence thresholds, toggle active behavior rules (loitering, restricted entry, crowding, rapid motion, unattended object), or switch between Dark/Light themes and English, Hindi, or Kannada.',
      actionLabel: 'Open Settings →',
      targetPage: 'settings',
      accentBg: 'rgba(168, 85, 247, 0.12)',
      accentColor: '#A855F7',
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9" />
        </svg>
      ),
    },
  ];

  return (
    <div
      className="deepvision-help-page"
      style={{
        maxWidth: '1200px',
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '18px',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '18px 22px',
          background: 'var(--bg-surface, #0C121D)',
          border: '1px solid var(--border-color, #1A2436)',
          borderRadius: 'var(--radius-lg, 8px)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(0, 229, 255, 0.12)', border: '1px solid rgba(0, 229, 255, 0.28)', color: 'var(--dv-cyan-500, #00E5FF)', padding: '3px 10px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.06em' }}>
            <span>OPERATOR GUIDANCE</span>
          </div>
          <a
            href="/api/health/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: '0.78rem', color: 'var(--dv-cyan-500, #00E5FF)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}
          >
            <span>View Health Diagnostics</span>
            <span>&rarr;</span>
          </a>
        </div>
        <h1 style={{ fontSize: '1.35rem', fontWeight: 800, margin: '2px 0 6px 0', color: 'var(--text-main, #F8FAFC)' }}>
          {t('help.subtitle', 'Simple instructions for operating the DeepVision surveillance platform')}
        </h1>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary, #94A3B8)', margin: 0, lineHeight: 1.5 }}>
          Practical reference for watching live cameras, recording clips, managing perimeter zones, investigating alerts, and configuring system preferences.
        </p>
      </div>

      {/* Guide Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))', gap: '14px' }}>
        {cards.map((card) => (
          <div
            key={card.title}
            style={{
              padding: '18px',
              background: 'var(--bg-surface, #0C121D)',
              border: '1px solid var(--border-color, #1A2436)',
              borderRadius: 'var(--radius-lg, 8px)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '6px', background: card.accentBg, color: card.accentColor, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  {card.icon}
                </div>
                <h2 style={{ fontSize: '0.96rem', fontWeight: 700, margin: 0, color: 'var(--text-main, #F8FAFC)' }}>
                  {card.title}
                </h2>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary, #94A3B8)', lineHeight: 1.55, margin: 0 }}>
                {card.body}
              </p>
            </div>

            {onNavigate && (
              <div>
                <button
                  type="button"
                  onClick={() => onNavigate(card.targetPage)}
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: '0.76rem', fontWeight: 600 }}
                >
                  {card.actionLabel}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default Help;
