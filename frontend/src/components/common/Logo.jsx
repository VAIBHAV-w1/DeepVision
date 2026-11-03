import React from 'react';

/**
 * DeepVision camera-viewfinder identity mark
 * Elegant interlocking dynamic curves, precision focal core, and crisp typography.
 */
export function Logo({
  size = 'md',
  withText = true,
  monochrome = false,
  className = '',
  subtext = 'SURVEILLANCE OPERATIONS',
}) {
  const pixelSizes = {
    xs: 20,
    sm: 24,
    md: 32,
    lg: 42,
    xl: 54,
  };

  const px = pixelSizes[size] || 32;

  return (
    <div
      className={`deepvision-brand-logo ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: size === 'sm' || size === 'xs' ? '8px' : '10px',
        userSelect: 'none',
        textDecoration: 'none',
      }}
    >
      {/* Precision Vector Optical Symbol */}
      <svg
        width={px}
        height={px}
        viewBox="0 0 56 56"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0 }}
        aria-label="DeepVision Logo Symbol"
      >
        <path
          d="M 19 7 H 12 A 5 5 0 0 0 7 12 V 19 M 37 7 H 44 A 5 5 0 0 1 49 12 V 19 M 7 37 V 44 A 5 5 0 0 0 12 49 H 19 M 37 49 H 44 A 5 5 0 0 0 49 44 V 37"
          stroke={monochrome ? 'currentColor' : '#00AFC4'}
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
        />
        <circle cx="28" cy="28" r="10" stroke={monochrome ? 'currentColor' : '#00AFC4'} strokeWidth="3" fill="none" />
        <circle cx="28" cy="28" r="3.5" fill={monochrome ? 'currentColor' : '#00AFC4'} />
      </svg>

      {/* Typography Wordmark */}
      {withText && (
        <div className="brand-text-block" style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.05 }}>
          <span
            className="brand-title"
            style={{
              fontFamily: 'var(--dv-font-sans, system-ui, sans-serif)',
              fontSize: size === 'xs' ? '0.82rem' : size === 'sm' ? '0.94rem' : size === 'lg' ? '1.32rem' : size === 'xl' ? '1.55rem' : '1.12rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              color: monochrome ? 'currentColor' : 'var(--text-main, #F8FAFC)',
            }}
          >
            DEEP<span style={{ color: monochrome ? 'currentColor' : '#00D2FF', fontWeight: 900 }}>VISION</span>
          </span>
          {subtext && (
            <span
              className="brand-subtext"
              style={{
                fontFamily: 'var(--dv-font-mono, monospace)',
                fontSize: size === 'xs' || size === 'sm' ? '0.54rem' : '0.62rem',
                fontWeight: 600,
                letterSpacing: '0.18em',
                color: monochrome ? 'currentColor' : 'var(--text-muted, #64748B)',
                marginTop: '2px',
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

export default Logo;
