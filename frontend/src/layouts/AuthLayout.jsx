import React from 'react';
import Logo from '../components/common/Logo';
import LanguageSelector from '../components/common/LanguageSelector';
import ThemeToggle from '../components/common/ThemeToggle';

export function AuthLayout({ children }) {
  return (
    <div className="auth-page-wrap" style={{ position: 'relative' }}>
      {/* Top Utility Bar for Theme & Language */}
      <div style={{ position: 'absolute', top: '1.25rem', right: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px', zIndex: 100 }}>
        <LanguageSelector compact />
        <ThemeToggle compact />
      </div>

      {/* Enterprise Security Brand Header */}
      <a href="#login" className="brand-link" style={{ marginBottom: '1.5rem', textDecoration: 'none', display: 'flex', justifyContent: 'center' }}>
        <Logo size="lg" subtext="INTELLIGENT SURVEILLANCE SOC" />
      </a>

      {/* Centered Enterprise Security Card */}
      <div className="auth-card-clean" style={{ border: '1px solid var(--border-color)', borderRadius: '8px', boxShadow: '0 8px 24px -4px rgba(0, 0, 0, 0.6)' }}>
        {children}
      </div>

      {/* Minimal Operator Security Notice & Legal Links */}
      <div style={{ marginTop: '1.75rem', fontSize: '0.74rem', color: 'var(--text-muted)', textAlign: 'center', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
        <span>Authorized Personnel Only</span>
        <span>&bull;</span>
        <a href="#privacy" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Privacy Policy</a>
        <span>&bull;</span>
        <a href="#terms" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>Terms &amp; Conditions</a>
      </div>

    </div>
  );
}


export default AuthLayout;
