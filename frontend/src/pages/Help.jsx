import React from 'react';

export function Help() {
  return (

    <div style={{ maxWidth: '1080px', margin: '0 auto', paddingBottom: '3rem' }}>
      {/* Operational Header */}
      <div className="hero-editorial-wrap" style={{ marginBottom: '1.75rem' }}>
        <div className="editorial-badge-pill" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#10b981', padding: '4px 12px', borderRadius: '9999px', fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.06em', marginBottom: '8px' }}>
          <span>OPERATOR GUIDANCE</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: '1.6rem', fontWeight: 700, margin: '2px 0 6px 0', letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
          Surveillance Documentation &amp; Setup Guides
        </h1>
        <p className="editorial-hero-subtitle" style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: 0 }}>
          Technical guidance for hardware camera connection, neural stream modes, forensic archiving, and incident management.
        </p>
      </div>

      {/* Guide Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem', marginBottom: '2.5rem' }}>
        {/* 1. Camera Ingestion & Setup */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 23 7 l -7 5 7 5 V 7 z"></path>
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
            </svg>
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>Hardware Camera Ingestion</h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
            DeepVision ingests video streams through native DirectShow capture (webcams indexed at <code>dshow://0</code>), RTSP network streams (<code>rtsp://user:pass@ip:port/stream</code>), and Wi-Fi phone cameras (IP Webcam app).
          </p>
        </div>

        {/* 2. Feed Modes */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M 3 7 V 5 a 2 2 0 0 1 2 -2 h 2"></path>
              <path d="M 17 3 h 2 a 2 2 0 0 1 2 2 v 2"></path>
              <path d="M 21 17 v 2 a 2 2 0 0 1 -2 2 h -2"></path>
              <path d="M 7 21 H 5 a 2 2 0 0 1 -2 -2 v -2"></path>
            </svg>
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>Stream Modes: Original vs AI</h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
            <strong>ORIGINAL</strong> delivers the raw, unprocessed CCTV camera feed with zero added inference latency. <strong>TRACKING + DETECTION</strong> runs the YOLO11n neural engine to detect persons and overlay persistent ByteTrack trajectory IDs in real time.
          </p>
        </div>

        {/* 3. Recording & Media Delivery */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>Video Archiving &amp; Playback</h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
            Recordings are encoded into standard MP4 files using OpenCV VideoWriter. Clips are streamed via HTTP 206 Partial Content range requests, allowing operators to scrub smoothly through recorded video timelines.
          </p>
        </div>

        {/* 4. Incident Response & Evidence */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 12 22 s 8 -4 8 -10 V 5 l -8 -3 -8 3 v 7 c 0 6 8 10 8 10 z"></path>
            </svg>
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>Incident Forensics &amp; Cases</h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
            Security alerts allow operators to isolate anomalies, view preserved evidence snapshots, attach investigation notes, and escalate alerts into tracked Incident Cases.
          </p>
        </div>

        {/* 5. Troubleshooting & Health */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>Signal Diagnostics &amp; Recovery</h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
            If a hardware camera drops signal, the CameraWorker thread attempts automatic reconnection. Health status can be verified through the <code>/api/health/</code> and <code>/api/surveillance/health/</code> diagnostics endpoints.
          </p>
        </div>

        {/* 6. Hardware Limitations Notice */}
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <path d="M 9.09 9 a 3 3 0 0 1 5.83 1 c 0 2 -3 3 -3 3"></path>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>Hardware Controls &amp; Capabilities</h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
            Physical webcams do not support motorized mechanical PTZ or two-way audio talkback. The live player provides client-side digital zoom (1x, 1.5x, 2x) with digital frame panning.
          </p>
        </div>
      </div>

      {/* System Technical Support & Diagnostic Logs */}
      <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', margin: '0 0 0.25rem 0' }}>
            System Technical Support &amp; Architecture Diagnostics
          </h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: 0, maxWidth: '600px' }}>
            Access real-time engine telemetry, verify database connection status, and review active YOLO11n singleton health directly through the API endpoint.
          </p>
        </div>
        <a
          href="/api/health/"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-sm"
          style={{ padding: '8px 16px', fontSize: '0.82rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <span>View Health Diagnostics</span>
          <span>&rarr;</span>
        </a>
      </div>
    </div>
  );
}


export default Help;
