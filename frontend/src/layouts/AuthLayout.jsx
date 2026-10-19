import React from 'react';
import Logo from '../components/common/Logo';

export function AuthLayout({ children }) {
  return (
    <div className="auth-page-wrap">
      {/* Enterprise Security Brand Header */}
      <a href="#login" className="brand-link" style={{ marginBottom: '1.5rem', textDecoration: 'none', display: 'flex', justifyContent: 'center' }}>
        <Logo size="lg" subtext="INTELLIGENT SURVEILLANCE SOC" />
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
