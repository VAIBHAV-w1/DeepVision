import React from 'react';

export function AuthLayout({ children }) {
  return (
    <div className="auth-page-wrap">
      {/* Brand Emblem Header */}
      <a href="#login" className="brand-link" style={{ marginBottom: '2rem', textDecoration: 'none' }}>
        <div className="brand-emblem" style={{ width: '44px', height: '44px', borderRadius: '12px' }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M 23 7 l -7 5 7 5 V 7 z"></path>
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
          </svg>
        </div>
        <div className="brand-title-wrap">
          <span className="brand-title" style={{ fontSize: '1.35rem' }}>DEEPVISION</span>
          <span className="brand-tagline">INTELLIGENT SURVEILLANCE</span>
        </div>
      </a>

      {/* Centered Card Container */}
      <div className="auth-card-clean">
        {children}
      </div>

      {/* Minimal Clean Footer */}
      <div style={{ marginTop: '2rem', fontSize: '0.80rem', color: 'var(--text-muted)', textAlign: 'center' }}>
        DeepVision &bull; Real-time Camera Ingestion &amp; Security Monitoring
      </div>
    </div>
  );
}

export default AuthLayout;
