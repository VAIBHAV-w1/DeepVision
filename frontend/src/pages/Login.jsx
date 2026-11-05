import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useTranslation } from '../i18n/i18nContext';
import LanguageSelector from '../components/common/LanguageSelector';
import ThemeToggle from '../components/common/ThemeToggle';

/**
 * DeepVision 4.0 — User Login Interface
 * Exact visual reconstruction of Figure 7.1.1: DeepVision User Login Interface.
 */
export function Login({ onNavigate, onNeedsVerification }) {
  const { t } = useTranslation();
  const { checkAuth } = useAuth();
  const { addToast } = useToast();

  const [step, setStep] = useState('credentials'); // 'credentials' | 'otp'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // 6-Digit OTP State
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [cooldown, setCooldown] = useState(60);
  const inputRefs = useRef([]);

  useEffect(() => {
    if (step === 'otp') {
      inputRefs.current[0]?.focus();
    }
  }, [step]);

  useEffect(() => {
    if (step !== 'otp' || cooldown <= 0) return;
    const timer = setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => clearInterval(timer);
  }, [step, cooldown]);

  const handleDigitChange = (idx, value) => {
    const clean = value.replace(/[^0-9]/g, '');
    const newDigits = [...digits];
    newDigits[idx] = clean ? clean[clean.length - 1] : '';
    setDigits(newDigits);
    if (clean && idx < 5) {
      inputRefs.current[idx + 1]?.focus();
    }
  };

  const handleKeyDown = (idx, e) => {
    if (e.key === 'Backspace' && !digits[idx] && idx > 0) {
      inputRefs.current[idx - 1]?.focus();
    }
  };

  const handleCredentialsSubmit = async (e) => {
    e.preventDefault();
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError(t('auth.emailRequired', 'Email is required.'));
      return;
    }
    if (!password) {
      setError(t('auth.passwordRequired', 'Password is required.'));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.login(trimmedEmail, password);

      if (res && res.requires_otp) {
        setStep('otp');
        setCooldown(60);
        addToast(t('auth.otpDispatched', 'Verification code dispatched to your email.'), 'info');
      } else if (res && res.needs_verification) {
        if (onNeedsVerification) onNeedsVerification(res.email || trimmedEmail);
      } else if (res && res.success) {
        await checkAuth();
        if (onNavigate) onNavigate('dashboard');
        else window.location.hash = '#dashboard';
      } else {
        const errorMsg = res?.error || res?.message || t('auth.invalidCredentials', 'Invalid email or password.');
        setError(errorMsg);
        addToast(errorMsg, 'error');
      }
    } catch (err) {
      const errorMsg = err?.data?.error || err?.message || t('auth.serviceUnavailable', 'Unable to reach authentication service. Please check your credentials or network status.');
      setError(errorMsg);
      addToast(errorMsg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleOtpSubmit = async (e) => {
    e.preventDefault();
    const otpCode = digits.join('');
    if (otpCode.length !== 6) {
      setError(t('auth.incompleteOtp', 'Please enter the complete 6-digit code.'));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.verifyLoginOtp(email.trim(), otpCode);
      if (res && res.success) {
        await checkAuth();
        if (onNavigate) onNavigate('dashboard');
        else window.location.hash = '#dashboard';
      } else {
        const errorMsg = res?.error || t('auth.invalidOtp', 'Invalid verification code.');
        setError(errorMsg);
        addToast(errorMsg, 'error');
      }
    } catch (err) {
      const errorMsg = err?.data?.error || err.message || t('auth.otpFailed', 'OTP verification failed.');
      setError(errorMsg);
      addToast(errorMsg, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="deepvision-auth-page"
      style={{
        minHeight: '100vh',
        display: 'flex',
        backgroundColor: '#060913',
        color: '#F8FAFC',
        fontFamily: 'var(--font-sans, system-ui, -apple-system, sans-serif)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Top Right Controls (Language & Theme) */}
      <div
        style={{
          position: 'absolute',
          top: '1.25rem',
          right: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          zIndex: 50,
        }}
      >
        <LanguageSelector compact />
        <ThemeToggle compact />
      </div>

      {/* Main Dual-Column Content */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          gap: '4rem',
          flexWrap: 'wrap',
          maxWidth: '1300px',
          margin: '0 auto',
        }}
      >
        {/* Left Column: Brand, 3D CCTV Camera Artwork & 4 Features (Figure 7.1.1) */}
        <div
          style={{
            flex: '1 1 480px',
            maxWidth: '560px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}
        >
          {/* Logo Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '2rem' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #00C9FF 0%, #0072FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 16px rgba(0, 201, 255, 0.5)',
              }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.2">
                <path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z" />
                <circle cx="12" cy="12" r="3" stroke="#00F5D4" strokeWidth="2" />
              </svg>
            </div>
            <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
              DeepVision
            </span>
          </div>

          {/* 3D Optical CCTV Bullet Surveillance Camera SVG Art */}
          <div
            style={{
              width: '100%',
              height: '240px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
              marginBottom: '1.5rem',
            }}
          >
            <svg
              width="360"
              height="220"
              viewBox="0 0 360 220"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              style={{ filter: 'drop-shadow(0 20px 30px rgba(0,0,0,0.7))' }}
            >
              <defs>
                <linearGradient id="bodyGrad" x1="60" y1="50" x2="260" y2="150" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#2A3852" />
                  <stop offset="50%" stopColor="#1E283A" />
                  <stop offset="100%" stopColor="#101726" />
                </linearGradient>
                <linearGradient id="hoodGrad" x1="120" y1="40" x2="300" y2="120" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#384968" />
                  <stop offset="100%" stopColor="#182234" />
                </linearGradient>
                <radialGradient id="lensAperture" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#00F5D4" stopOpacity="0.9" />
                  <stop offset="40%" stopColor="#0072FF" stopOpacity="0.8" />
                  <stop offset="70%" stopColor="#0B132B" />
                  <stop offset="100%" stopColor="#000000" />
                </radialGradient>
              </defs>
              {/* Wall Mount Bracket */}
              <path d="M40 70 L90 90 L90 130 L40 150 Z" fill="#131B2B" stroke="#25354F" strokeWidth="2" />
              <rect x="35" y="60" width="10" height="100" rx="4" fill="#0E1624" stroke="#1E2B3E" strokeWidth="2" />
              <path d="M85 105 L130 115 L130 135 L85 125 Z" fill="#1B263B" />
              {/* Swivel Joint */}
              <circle cx="130" cy="125" r="14" fill="#2A3952" stroke="#3E5478" strokeWidth="2" />
              {/* Main Camera Cylindrical Body */}
              <path d="M125 90 L270 55 L285 130 L140 165 Z" fill="url(#bodyGrad)" stroke="#384C6D" strokeWidth="2" />
              {/* Top Sunshield Hood */}
              <path d="M115 80 L310 35 L315 50 L125 95 Z" fill="url(#hoodGrad)" stroke="#4A648F" strokeWidth="1.5" />
              {/* Front Camera Bezel & Lens */}
              <ellipse cx="280" cy="95" rx="22" ry="42" fill="#0E1726" stroke="#00C9FF" strokeWidth="2.5" />
              <ellipse cx="280" cy="95" rx="15" ry="28" fill="url(#lensAperture)" />
              <circle cx="278" cy="92" r="5" fill="#FFFFFF" opacity="0.6" />
              {/* IR LED Ring */}
              <circle cx="280" cy="65" r="2" fill="#00F5D4" />
              <circle cx="280" cy="125" r="2" fill="#00F5D4" />
              <circle cx="265" cy="80" r="2" fill="#00F5D4" />
              <circle cx="265" cy="110" r="2" fill="#00F5D4" />
              <circle cx="295" cy="80" r="2" fill="#00F5D4" />
              <circle cx="295" cy="110" r="2" fill="#00F5D4" />
              {/* Status Power LED */}
              <circle cx="288" cy="132" r="3" fill="#10B981" boxShadow="0 0 6px #10B981" />
            </svg>
          </div>

          {/* Heading & Subtitle matching Figure 7.1.1 */}
          <h1
            style={{
              fontSize: '2rem',
              fontWeight: 800,
              lineHeight: 1.2,
              color: '#FFFFFF',
              letterSpacing: '-0.025em',
              margin: '0 0 10px 0',
            }}
          >
            AI-Based Intelligent Surveillance System
          </h1>
          <p
            style={{
              fontSize: '0.95rem',
              color: '#94A3B8',
              lineHeight: 1.5,
              margin: '0 0 2rem 0',
            }}
          >
            Real-time monitoring, object detection, tracking and intelligent security.
          </p>

          {/* 4 Feature Badges in horizontal row matching Figure 7.1.1 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '12px',
              paddingTop: '1rem',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {[
              {
                title: 'Live Monitoring',
                icon: (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" strokeWidth="2">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                    <line x1="8" y1="21" x2="16" y2="21" />
                    <line x1="12" y1="17" x2="12" y2="21" />
                  </svg>
                ),
              },
              {
                title: 'Object Detection',
                icon: (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="22" y1="12" x2="18" y2="12" />
                    <line x1="6" y1="12" x2="2" y2="12" />
                    <line x1="12" y1="6" x2="12" y2="2" />
                    <line x1="12" y1="22" x2="12" y2="18" />
                  </svg>
                ),
              },
              {
                title: 'Anomaly Detection',
                icon: (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" strokeWidth="2">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                ),
              },
              {
                title: 'Security Alerts',
                icon: (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" strokeWidth="2">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
                ),
              },
            ].map((f, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: '8px' }}>
                <div
                  style={{
                    width: '42px',
                    height: '42px',
                    borderRadius: '50%',
                    backgroundColor: 'rgba(15, 23, 42, 0.8)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {f.icon}
                </div>
                <span style={{ fontSize: '0.75rem', color: '#94A3B8', fontWeight: 600 }}>{f.title}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Floating Dark Login Card (Figure 7.1.1) */}
        <div
          style={{
            flex: '0 0 420px',
            backgroundColor: 'rgba(15, 23, 42, 0.88)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '16px',
            padding: '2.5rem 2rem',
            boxShadow: '0 24px 60px rgba(0, 0, 0, 0.65)',
            backdropFilter: 'blur(16px)',
          }}
        >
          {/* Top Shield Emblem */}
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.25rem' }}>
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #00C9FF 0%, #0072FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 20px rgba(0, 201, 255, 0.45)',
              }}
            >
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.2">
                <path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z" />
                <circle cx="12" cy="12" r="3" stroke="#00F5D4" strokeWidth="2" />
              </svg>
            </div>
          </div>

          <h2
            style={{
              fontSize: '1.5rem',
              fontWeight: 800,
              color: '#FFFFFF',
              textAlign: 'center',
              margin: '0 0 6px 0',
              letterSpacing: '-0.02em',
            }}
          >
            Welcome to DeepVision
          </h2>
          <p
            style={{
              fontSize: '0.88rem',
              color: '#94A3B8',
              textAlign: 'center',
              margin: '0 0 1.75rem 0',
            }}
          >
            {step === 'credentials' ? 'Sign in to your account' : 'Enter 6-digit verification code'}
          </p>

          {error && (
            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                borderRadius: '8px',
                padding: '10px 14px',
                fontSize: '0.84rem',
                color: '#FCA5A5',
                marginBottom: '1.25rem',
              }}
            >
              {error}
            </div>
          )}

          {step === 'credentials' ? (
            <form onSubmit={handleCredentialsSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Email Input with Mail Icon */}
              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    backgroundColor: '#090E1A',
                    border: '1px solid #1E293B',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="2">
                    <rect x="2" y="4" width="20" height="16" rx="2" />
                    <path d="M22 6l-10 7L2 6" />
                  </svg>
                  <input
                    id="input-login-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="vaibhav@deepvision.ai"
                    required
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#F8FAFC',
                      fontSize: '0.9rem',
                      width: '100%',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              {/* Password Input with Lock Icon & Eye Toggle */}
              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    backgroundColor: '#090E1A',
                    border: '1px solid #1E293B',
                    borderRadius: '8px',
                    padding: '10px 14px',
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                  <input
                    id="input-login-password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#F8FAFC',
                      fontSize: '0.9rem',
                      width: '100%',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#64748B',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    {showPassword ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {/* Remember Me & Forgot Password Row */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.84rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#94A3B8' }}>
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                    style={{ accentColor: '#2563EB', cursor: 'pointer' }}
                  />
                  <span>Remember me</span>
                </label>
                <a
                  href="#forgot-password"
                  onClick={(e) => {
                    e.preventDefault();
                    if (onNavigate) onNavigate('forgot-password');
                    else window.location.hash = '#forgot-password';
                  }}
                  style={{ color: '#38BDF8', textDecoration: 'none', fontWeight: 600 }}
                >
                  Forgot password?
                </a>
              </div>

              {/* Primary Sign In Button matching Figure 7.1.1 */}
              <button
                type="submit"
                id="btn-sign-in"
                disabled={loading}
                style={{
                  marginTop: '0.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  backgroundColor: '#2563EB',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '12px 20px',
                  fontSize: '0.92rem',
                  fontWeight: 700,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  boxShadow: '0 4px 14px rgba(37, 99, 235, 0.45)',
                  transition: 'background-color 0.15s',
                }}
                onMouseEnter={(e) => {
                  if (!loading) e.currentTarget.style.backgroundColor = '#1D4ED8';
                }}
                onMouseLeave={(e) => {
                  if (!loading) e.currentTarget.style.backgroundColor = '#2563EB';
                }}
              >
                <span>{loading ? 'Signing In...' : 'Sign In'}</span>
                <span style={{ fontSize: '1.1rem', lineHeight: 1 }}>→</span>
              </button>

              {/* Create Account Link Footer */}
              <div style={{ textAlign: 'center', marginTop: '1rem', fontSize: '0.84rem', color: '#94A3B8' }}>
                <span>Don't have an account? </span>
                <a
                  href="#signup"
                  onClick={(e) => {
                    e.preventDefault();
                    if (onNavigate) onNavigate('signup');
                    else window.location.hash = '#signup';
                  }}
                  style={{ color: '#38BDF8', textDecoration: 'none', fontWeight: 700 }}
                >
                  Create Account
                </a>
              </div>
            </form>
          ) : (
            /* 6-Digit OTP Form */
            <form onSubmit={handleOtpSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '8px' }}>
                {digits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (inputRefs.current[idx] = el)}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleDigitChange(idx, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(idx, e)}
                    style={{
                      width: '44px',
                      height: '52px',
                      borderRadius: '8px',
                      backgroundColor: '#090E1A',
                      border: '1px solid #1E293B',
                      color: '#F8FAFC',
                      fontSize: '1.4rem',
                      fontWeight: 700,
                      textAlign: 'center',
                      outline: 'none',
                    }}
                  />
                ))}
              </div>
              <button
                type="submit"
                disabled={loading}
                style={{
                  backgroundColor: '#2563EB',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '12px 20px',
                  fontSize: '0.92rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  marginTop: '0.5rem',
                }}
              >
                {loading ? 'Verifying...' : 'Verify Code'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default Login;
