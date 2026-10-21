import React from 'react';

export function Footer() {
  return (
    <footer className="app-footer">
      <div className="app-footer-inner">
        <div className="app-footer-center">
          <div className="app-footer-brand">DeepVision</div>
          <div className="app-footer-tagline">AI-Powered Intelligent Surveillance &bull; Django Engine</div>
          <div className="app-footer-copyright">&copy; {new Date().getFullYear()} DeepVision</div>
          <div className="app-footer-links" style={{ display: 'flex', gap: '14px', alignItems: 'center', justifyContent: 'center' }}>
            <a href="#help" className="app-footer-link">Operator Guidance</a>
            <span style={{ color: 'var(--text-muted)' }}>&bull;</span>
            <a href="#privacy" className="app-footer-link">Privacy Policy</a>
            <span style={{ color: 'var(--text-muted)' }}>&bull;</span>
            <a href="#terms" className="app-footer-link">Terms &amp; Conditions</a>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
