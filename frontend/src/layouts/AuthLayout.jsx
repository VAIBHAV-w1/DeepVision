import React from 'react';

export function AuthLayout({ children }) {
  return (
    <div className="auth-page-wrap">
      {/* Enterprise Security Brand Header */}
      <a href="#login" className="brand-link" style={{ marginBottom: '1.5rem', textDecoration: 'none', flexDirection: 'column', gap: '0.75rem', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className="brand-emblem" style={{ width: '38px', height: '38px', borderRadius: '8px', background: '#0f172a', border: '1px solid rgba(16, 185, 129, 0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" stroke="#10b981" strokeWidth="1.8" />
              <circle cx="12" cy="12" r="4" fill="#10b981" />
              <line x1="12" y1="2" x2="12" y2="5" />
              <line x1="12" y1="19" x2="12" y2="22" />
              <line x1="2" y1="12" x2="5" y2="12" />
              <line x1="19" y1="12" x2="22" y2="22" />
            </svg>
          </div>
          <div className="brand-title-wrap">
            <span className="brand-title" style={{ fontSize: '1.3rem', letterSpacing: '0.06em', fontWeight: 800 }}>DEEPVISION</span>
            <span className="brand-tagline" style={{ fontSize: '0.62rem', letterSpacing: '0.08em', color: 'var(--text-muted)', fontWeight: 600 }}>SURVEILLANCE SOC</span>
          </div>
        </div>
      </a>

      {/* Centered Enterprise Security Card */}
      <div className="auth-card-clean" style={{ border: '1px solid var(--border-color)', borderRadius: '8px', boxShadow: '0 8px 24px -4px rgba(0, 0, 0, 0.6)' }}>
        {children}
      </div>

      {/* Minimal Operator Security Notice */}
      <div style={{ marginTop: '1.75rem', fontSize: '0.74rem', color: 'var(--text-muted)', textAlign: 'center', display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'center' }}>
        <span>Authorized Personnel Only</span>
        <span>&bull;</span>
        <span>Session Audited</span>
        <span>&bull;</span>
        <span>SOC Hardened</span>
      </div>

    </div>
  );
}


export default AuthLayout;
