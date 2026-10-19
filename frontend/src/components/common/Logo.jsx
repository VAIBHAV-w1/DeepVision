import React from 'react';

/**
 * DeepVision Professional Surveillance & SOC Brand Logo
 * Clean, modern, scalable vector mark suitable for dark & light backgrounds.
 */
export function Logo({ size = 'md', withText = true, className = '', subtext = 'INTELLIGENT SURVEILLANCE' }) {
  const pixelSizes = {
    sm: 24,
    md: 32,
    lg: 44,
    xl: 56,
  };

  const px = pixelSizes[size] || 32;

  return (
    <div className={`deepvision-brand-logo ${className}`} style={{ display: 'inline-flex', alignItems: 'center', gap: size === 'sm' ? '8px' : '12px' }}>
      <svg
        width={px}
        height={px}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0 }}
        aria-label="DeepVision Logo"
      >
        {/* Outer Hexagonal Surveillance Target Boundary */}
        <polygon
          points="24,3 41,13 41,35 24,45 7,35 7,13"
          stroke="var(--color-primary, #10b981)"
          strokeWidth="2.5"
          strokeLinejoin="round"
          fill="none"
          opacity="0.9"
        />

        {/* Optical Sensor Ring */}
        <circle
          cx="24"
          cy="24"
          r="13"
          stroke="var(--text-secondary, #94a3b8)"
          strokeWidth="1.8"
          strokeDasharray="4 2"
          opacity="0.65"
        />

        {/* Inner Precision Aperture Ring */}
        <circle
          cx="24"
          cy="24"
          r="7.5"
          stroke="var(--color-primary, #10b981)"
          strokeWidth="2"
          fill="rgba(16, 185, 129, 0.15)"
        />

        {/* Central Iris Focal Point */}
        <circle
          cx="24"
          cy="24"
          r="3.5"
          fill="var(--color-primary, #10b981)"
        />

        {/* Surveillance Crosshair Reticles (Compass Ticks) */}
        <line x1="24" y1="5" x2="24" y2="9" stroke="var(--color-primary, #10b981)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="24" y1="39" x2="24" y2="43" stroke="var(--color-primary, #10b981)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="9" y1="24" x2="13" y2="24" stroke="var(--color-primary, #10b981)" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="35" y1="24" x2="39" y2="24" stroke="var(--color-primary, #10b981)" strokeWidth="2.5" strokeLinecap="round" />
      </svg>

      {withText && (
        <div className="brand-text-block" style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
          <span
            className="brand-title"
            style={{
              fontFamily: 'var(--font-display, inherit)',
              fontSize: size === 'sm' ? '0.95rem' : size === 'lg' ? '1.35rem' : '1.15rem',
              fontWeight: 800,
              letterSpacing: '0.04em',
              color: 'var(--text-main)',
            }}
          >
            DEEP<span style={{ color: 'var(--color-primary, #10b981)' }}>VISION</span>
          </span>
          {subtext && (
            <span
              className="brand-subtext"
              style={{
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: size === 'sm' ? '0.62rem' : '0.68rem',
                fontWeight: 600,
                letterSpacing: '0.1em',
                color: 'var(--text-muted)',
                marginTop: '2px',
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
