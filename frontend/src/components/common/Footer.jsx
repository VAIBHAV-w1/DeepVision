import React from 'react';
import { useTranslation } from '../../i18n/i18nContext';

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="app-footer">
      <div className="app-footer-inner">
        <div className="app-footer-center">
          <div className="app-footer-brand">{t('brand.name', 'DeepVision')}</div>
          <div className="app-footer-tagline">{t('app.tagline', 'AI-Powered Intelligent Surveillance • Django Engine')}</div>
          <div className="app-footer-copyright">&copy; {new Date().getFullYear()} {t('brand.name', 'DeepVision')}</div>
          <div className="app-footer-links" style={{ display: 'flex', gap: '14px', alignItems: 'center', justifyContent: 'center' }}>
            <a href="#help" className="app-footer-link">{t('help.badgeGuidance', 'Operator Guidance')}</a>
            <span style={{ color: 'var(--text-muted)' }}>&bull;</span>
            <a href="#privacy" className="app-footer-link">{t('legal.privacyTab', 'Privacy Policy')}</a>
            <span style={{ color: 'var(--text-muted)' }}>&bull;</span>
            <a href="#terms" className="app-footer-link">{t('legal.termsTab', 'Terms & Conditions')}</a>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
