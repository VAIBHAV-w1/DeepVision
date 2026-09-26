import React from 'react';

export function Footer() {
  return (
    <footer className="app-footer">
      <div className="app-footer-inner">
        <div className="app-footer-center">
          <div className="app-footer-brand">DeepVision</div>
          <div className="app-footer-tagline">AI-Powered Intelligent Surveillance &bull; Django Engine</div>
          <div className="app-footer-copyright">&copy; {new Date().getFullYear()} DeepVision</div>
          <div className="app-footer-links">
            <a href="#help" className="app-footer-link">Help &amp; Support</a>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
