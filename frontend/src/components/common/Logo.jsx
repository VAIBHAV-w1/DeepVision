import React from 'react';
import { useTranslation } from '../../i18n/i18nContext';

/**
 * DeepVision 4.0 — Canonical Brand Identity Logo Component
 * Renders the approved surveillance camera emblem with optical reticle and
 * language-responsive brand typography across English, Hindi, and Kannada.
 */
export function Logo({
  size = 'md',
  withText = true,
  monochrome = false,
  className = '',
  subtext = '',
  style = {},
}) {
  let t = (k, d) => d;
  try {
    const ctx = useTranslation();
    if (ctx && ctx.t) {
      t = ctx.t;
    }
  } catch (_) {
    // Graceful fallback when outside i18n context
  }

  const sizes = {
    xs: { box: 22, icon: 14, text: '0.85rem', sub: '0.55rem', gap: '6px' },
    sm: { box: 28, icon: 16, text: '1.0rem', sub: '0.60rem', gap: '8px' },
    md: { box: 34, icon: 20, text: '1.2rem', sub: '0.65rem', gap: '10px' },
    lg: { box: 42, icon: 24, text: '1.45rem', sub: '0.72rem', gap: '12px' },
    xl: { box: 52, icon: 30, text: '1.85rem', sub: '0.80rem', gap: '14px' },
  };

  const dim = sizes[size] || sizes.md;

  return (
    <div
      className={`deepvision-brand-logo ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: dim.gap,
        userSelect: 'none',
        textDecoration: 'none',
        ...style,
      }}
    >
      {/* Canonical DeepVision Surveillance Camera Emblem */}
      <div
        style={{
          width: `${dim.box}px`,
          height: `${dim.box}px`,
          borderRadius: size === 'xs' || size === 'sm' ? '6px' : '8px',
          background: monochrome
            ? 'currentColor'
            : 'linear-gradient(135deg, #00C9FF 0%, #0072FF 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: monochrome ? 'none' : '0 0 14px rgba(0, 201, 255, 0.45)',
          flexShrink: 0,
        }}
      >
        <svg
          width={dim.icon}
          height={dim.icon}
          viewBox="0 0 24 24"
          fill="none"
          aria-label="DeepVision Surveillance Camera Emblem"
        >
          <path
            d="M4 17.5v3.5h5"
            stroke={monochrome ? '#0B0F19' : '#FFFFFF'}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M2.5 7.5h13l4.5 3"
            stroke={monochrome ? '#0B0F19' : '#00F5D4'}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M2.5 9h11.5l4 3v3l-4 3H2.5a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 2.5 9z"
            stroke={monochrome ? '#0B0F19' : '#FFFFFF'}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle
            cx="7.5"
            cy="13.5"
            r="2.2"
            stroke={monochrome ? '#0B0F19' : '#00F5D4'}
            strokeWidth="1.8"
          />
          <circle
            cx="7.5"
            cy="13.5"
            r="0.8"
            fill={monochrome ? '#0B0F19' : '#00F5D4'}
          />
          <line
            x1="19.5"
            y1="13.5"
            x2="22.5"
            y2="13.5"
            stroke={monochrome ? '#0B0F19' : '#00F5D4'}
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Typography Wordmark (Language Responsive) */}
      {withText && (
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
          <span
            className="brand-title"
            style={{
              fontFamily: 'var(--dv-font-sans, system-ui, -apple-system, sans-serif)',
              fontSize: dim.text,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: monochrome ? 'currentColor' : '#FFFFFF',
            }}
          >
            {t('brand.name', 'DeepVision')}
          </span>
          {subtext && (
            <span
              className="brand-subtext"
              style={{
                fontFamily: 'var(--dv-font-mono, monospace)',
                fontSize: dim.sub,
                fontWeight: 600,
                letterSpacing: '0.12em',
                color: monochrome ? 'currentColor' : '#94A3B8',
                marginTop: '1px',
                opacity: 0.85,
              }}
            >
              {subtext}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export const DeepVisionLogo = Logo;

/**
 * Shared standalone SVG surveillance camera emblem for DeepVision 4.0
 */
export function SurveillanceCameraEmblemIcon({ size = 20, monochrome = false, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-label="DeepVision Surveillance Camera Emblem"
    >
      <path
        d="M4 17.5v3.5h5"
        stroke={monochrome ? 'currentColor' : '#FFFFFF'}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M2.5 7.5h13l4.5 3"
        stroke={monochrome ? 'currentColor' : '#00F5D4'}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M2.5 9h11.5l4 3v3l-4 3H2.5a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 2.5 9z"
        stroke={monochrome ? 'currentColor' : '#FFFFFF'}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx="7.5"
        cy="13.5"
        r="2.2"
        stroke={monochrome ? 'currentColor' : '#00F5D4'}
        strokeWidth="1.8"
      />
      <circle
        cx="7.5"
        cy="13.5"
        r="0.8"
        fill={monochrome ? 'currentColor' : '#00F5D4'}
      />
      <line
        x1="19.5"
        y1="13.5"
        x2="22.5"
        y2="13.5"
        stroke={monochrome ? 'currentColor' : '#00F5D4'}
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default Logo;
