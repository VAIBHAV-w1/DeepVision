import React from 'react';

export function Help() {
  const handleOpenAssistant = () => {
    const launcher = document.getElementById('btn-chatbot-launcher');
    if (launcher) launcher.click();
  };

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', paddingBottom: '3rem' }}>
      {/* Editorial Header */}
      <div className="hero-editorial-wrap" style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
        <div className="editorial-badge-pill" style={{ marginBottom: '0.75rem' }}>
          <span>Documentation &amp; Guides</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: 'clamp(2.2rem, 4.5vw, 3.5rem)', marginBottom: '0.6rem' }}>
          How can we help?
        </h1>
        <p className="editorial-hero-subtitle" style={{ margin: '0 auto', maxWidth: '540px', color: 'var(--text-secondary)' }}>
          Simple setup guides, camera connection instructions, and troubleshooting documentation for DeepVision operators.
        </p>
      </div>

      {/* Editorial Topic Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.25rem', marginBottom: '3rem' }}>
        {/* 1. Adding a camera */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-card, var(--bg-surface))', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-sm)', background: 'var(--color-primary-subtle, rgba(37, 99, 235, 0.1))', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.35rem' }}>Adding a Camera</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.45, margin: 0 }}>
            Connect phone cameras (IP Webcam), USB webcams, network IP streams, or RTSP feeds in 4 easy steps.
          </p>
        </div>

        {/* 2. Connecting a phone */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-card, var(--bg-surface))', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-sm)', background: 'var(--color-primary-subtle, rgba(37, 99, 235, 0.1))', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect>
              <line x1="12" y1="18" x2="12.01" y2="18"></line>
            </svg>
          </div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.35rem' }}>Connecting a Phone</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.45, margin: 0 }}>
            Use the free Android IP Webcam app to stream high-definition video over Wi-Fi without cables.
          </p>
        </div>

        {/* 3. Using detection mode */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-card, var(--bg-surface))', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-sm)', background: 'var(--color-primary-subtle, rgba(37, 99, 235, 0.1))', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M 3 7 V 5 a 2 2 0 0 1 2 -2 h 2"></path>
              <path d="M 17 3 h 2 a 2 2 0 0 1 2 2 v 2"></path>
              <path d="M 21 17 v 2 a 2 2 0 0 1 -2 2 h -2"></path>
              <path d="M 7 21 H 5 a 2 2 0 0 1 -2 -2 v -2"></path>
            </svg>
          </div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.35rem' }}>Smart Detection &amp; Tracking</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.45, margin: 0 }}>
            DeepVision automatically runs YOLO11n object detection paired with ByteTrack trajectory tracking.
          </p>
        </div>
      </div>

      {/* DeepVision Assistant Card */}
      <div className="card" style={{ padding: '2rem', background: 'var(--bg-card, var(--bg-surface))', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
        <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
          Need Instant Answers?
        </h3>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto 1.25rem auto' }}>
          Use the DeepVision Assistant launcher in the bottom-right corner to ask questions about camera setup, tracking, alerts, and system usage.
        </p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleOpenAssistant}
        >
          Open DeepVision Assistant
        </button>
      </div>
    </div>
  );
}

export default Help;
