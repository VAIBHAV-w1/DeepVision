import React from 'react';
import LanguageSelector from '../components/common/LanguageSelector';
import ThemeToggle from '../components/common/ThemeToggle';
import { useTranslation } from '../i18n/i18nContext';

export function AuthLayout({ children }) {
  const { t } = useTranslation();

  React.useEffect(() => {
    const brand = t('brand.name', 'DeepVision');
    document.title = `${brand} — ${t('brand.tagline', 'AI-Based Intelligent Surveillance System')}`;
  }, [t]);

  return (
    <div
      className="auth-split-wrapper"
      style={{
        minHeight: '100vh',
        display: 'flex',
        backgroundColor: '#070b13',
        color: '#f8fafc',
        fontFamily: 'var(--font-sans, system-ui, sans-serif)',
        position: 'relative',
        flexWrap: 'wrap',
      }}
    >
      {/* Top right language/theme bar */}
      <div
        style={{
          position: 'absolute',
          top: '1.25rem',
          right: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          zIndex: 100,
        }}
      >
        <LanguageSelector compact />
        <ThemeToggle compact />
      </div>

      {/* Left Hero Visual Column (matches Figure 7.1.1) */}
      <div
        className="auth-hero-col"
        style={{
          flex: '1 1 520px',
          background: 'linear-gradient(135deg, #070B14 0%, #0B1325 50%, #060911 100%)',
          borderRight: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '3rem 2.5rem',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Subtle background glows */}
        <div
          style={{
            position: 'absolute',
            top: '15%',
            left: '15%',
            width: '400px',
            height: '400px',
            background: 'radial-gradient(circle, rgba(37, 99, 235, 0.22) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: '10%',
            right: '10%',
            width: '300px',
            height: '300px',
            background: 'radial-gradient(circle, rgba(56, 189, 248, 0.12) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />

        {/* Content Container */}
        <div style={{ maxWidth: '460px', width: '100%', textAlign: 'left', zIndex: 2 }}>
          {/* Logo Brand Header matching canonical DeepVision surveillance camera identity */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '2.5rem' }}>
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #00C9FF 0%, #0072FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 16px rgba(0, 201, 255, 0.45)',
                flexShrink: 0,
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-label="DeepVision Surveillance Camera Emblem">
                <path d="M4 17.5v3.5h5" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2.5 7.5h13l4.5 3" stroke="#00F5D4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2.5 9h11.5l4 3v3l-4 3H2.5a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 2.5 9z" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="7.5" cy="13.5" r="2.2" stroke="#00F5D4" strokeWidth="1.8" />
                <circle cx="7.5" cy="13.5" r="0.8" fill="#00F5D4" />
                <line x1="19.5" y1="13.5" x2="22.5" y2="13.5" stroke="#00F5D4" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <span style={{ fontSize: '1.85rem', fontWeight: 800, letterSpacing: '-0.03em', color: '#FFFFFF' }}>
              {t('brand.name', 'DeepVision')}
            </span>
          </div>

          {/* High-Tech CCTV Security Camera Artwork matching Figure 7.1.1 */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '220px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.5rem',
            }}
          >
            {/* Sleek Bullet Security Camera Graphic */}
            <svg
              width="320"
              height="200"
              viewBox="0 0 320 200"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              style={{ filter: 'drop-shadow(0 14px 28px rgba(0,0,0,0.6))' }}
            >
              <defs>
                <linearGradient id="bodyGrad" x1="40" y1="50" x2="220" y2="130" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#334155" />
                  <stop offset="0.5" stopColor="#1E293B" />
                  <stop offset="1" stopColor="#0F172A" />
                </linearGradient>
                <linearGradient id="lensGrad" x1="190" y1="60" x2="250" y2="140" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#38BDF8" />
                  <stop offset="0.6" stopColor="#0284C7" />
                  <stop offset="1" stopColor="#0369A1" />
                </linearGradient>
                <radialGradient id="lensGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.9" />
                  <stop offset="50%" stopColor="#0284C7" stopOpacity="0.5" />
                  <stop offset="100%" stopColor="#0369A1" stopOpacity="0" />
                </radialGradient>
                <linearGradient id="mountGrad" x1="20" y1="120" x2="80" y2="170" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#475569" />
                  <stop offset="1" stopColor="#1E293B" />
                </linearGradient>
              </defs>

              {/* Wall Mount Base */}
              <rect x="25" y="115" width="22" height="60" rx="4" fill="url(#mountGrad)" stroke="#64748B" strokeWidth="1.5" />
              {/* Articulated Arm */}
              <path d="M47 135 L95 110 L115 125 L65 150 Z" fill="#334155" stroke="#475569" strokeWidth="1.5" />
              <circle cx="105" cy="118" r="10" fill="#1E293B" stroke="#64748B" strokeWidth="2" />
              <circle cx="105" cy="118" r="4" fill="#38BDF8" />

              {/* Camera Sunshield Housing */}
              <path d="M70 70 L235 60 L245 75 L75 88 Z" fill="#475569" stroke="#64748B" strokeWidth="1" />
              {/* Main Camera Body (Cylindrical Wedge) */}
              <path d="M80 82 L220 74 L225 142 L80 132 Z" fill="url(#bodyGrad)" stroke="#475569" strokeWidth="1.5" />

              {/* Front Bezel & Infrared Ring */}
              <ellipse cx="222" cy="108" rx="14" ry="34" fill="#0F172A" stroke="#64748B" strokeWidth="2" />
              {/* Glowing Optical Lens Ring with Blue Glow */}
              <ellipse cx="223" cy="108" rx="10" ry="26" fill="url(#lensGrad)" />
              <circle cx="224" cy="108" r="12" fill="url(#lensGlow)" />
              {/* Inner Lens Reflection */}
              <ellipse cx="225" cy="104" rx="4" ry="9" fill="#E0F2FE" opacity="0.75" />
              <circle cx="221" cy="114" r="2.5" fill="#38BDF8" />

              {/* Status Indicator LED (Live Green) */}
              <circle cx="195" cy="132" r="3" fill="#10B981" />
              <circle cx="195" cy="132" r="6" fill="#10B981" opacity="0.3" />

              {/* Accent Trim Lines */}
              <line x1="100" y1="90" x2="200" y2="84" stroke="#38BDF8" strokeWidth="1.5" strokeOpacity="0.7" />
              <line x1="100" y1="126" x2="200" y2="132" stroke="#1E293B" strokeWidth="2" />
            </svg>
          </div>

          {/* Heading matching Figure 7.1.1 */}
          <h2
            style={{
              fontSize: '1.45rem',
              fontWeight: 800,
              color: '#F8FAFC',
              margin: '0 0 1.25rem 0',
              lineHeight: 1.3,
              letterSpacing: '-0.02em',
            }}
          >
            {t('login.brandSubtitle1', 'AI-Based Intelligent')}
            <br />
            {t('login.brandSubtitle2', 'Surveillance System')}
          </h2>

          {/* Four feature pills matching Figure 7.1.1 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '0.82rem',
                color: '#E2E8F0',
                fontWeight: 600,
              }}
            >
              <span style={{ color: '#38BDF8' }}>📷</span> {t('login.featureLiveMonitoring', 'Live Monitoring')}
            </div>
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '0.82rem',
                color: '#E2E8F0',
                fontWeight: 600,
              }}
            >
              <span style={{ color: '#10B981' }}>🔍</span> {t('login.featureObjectDetection', 'Object Detection')}
            </div>
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '0.82rem',
                color: '#E2E8F0',
                fontWeight: 600,
              }}
            >
              <span style={{ color: '#F59E0B' }}>⚡</span> {t('login.featureAnomalyDetection', 'Anomaly Detection')}
            </div>
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '0.82rem',
                color: '#E2E8F0',
                fontWeight: 600,
              }}
            >
              <span style={{ color: '#EF4444' }}>🚨</span> {t('login.featureSecurityAlerts', 'Security Alerts')}
            </div>
          </div>
        </div>
      </div>

      {/* Right Form Column */}
      <div
        className="auth-form-col"
        style={{
          flex: '1 1 420px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '2.5rem 2rem',
          backgroundColor: '#070B13',
        }}
      >
        <div style={{ maxWidth: '400px', width: '100%' }}>{children}</div>
      </div>
    </div>
  );
}

export default AuthLayout;
