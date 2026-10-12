import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../services/api';
import AuthLayout from '../layouts/AuthLayout';
import { useToast } from '../components/common/Toast';

export function Login({ onNavigate, onNeedsVerification }) {
  const { checkAuth } = useAuth();
  const [step, setStep] = useState('credentials'); // 'credentials' | 'otp'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // OTP State
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [cooldown, setCooldown] = useState(60);
  const [resending, setResending] = useState(false);
  const inputRefs = useRef([]);
  const { addToast } = useToast();

  useEffect(() => {
    if (step === 'otp') {
      inputRefs.current[0]?.focus();
    }
  }, [step]);

  useEffect(() => {
    if (step !== 'otp' || cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((c) => c - 1);
    }, 1000);
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
    } else if (e.key === 'ArrowLeft' && idx > 0) {
      inputRefs.current[idx - 1]?.focus();
    } else if (e.key === 'ArrowRight' && idx < 5) {
      inputRefs.current[idx + 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const paste = e.clipboardData.getData('text').replace(/[^0-9]/g, '').slice(0, 6);
    if (!paste) return;
    const newDigits = [...digits];
    paste.split('').forEach((d, i) => {
      if (i < 6) newDigits[i] = d;
    });
    setDigits(newDigits);
    const nextIdx = Math.min(paste.length, 5);
    inputRefs.current[nextIdx]?.focus();
  };

  // Step 1: Submit Credentials
  const handleCredentialsSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Email and password are required.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.login(email, password);

      if (res && res.requires_otp) {
        setStep('otp');
        setCooldown(60);
        addToast('Verification code dispatched to your email.', 'info');
      } else if (res && res.needs_verification) {
        onNeedsVerification(res.email || email);
      } else if (res && res.success && res.user) {
        await checkAuth();
        onNavigate('dashboard');
      } else {
        setError(res?.error || 'Invalid email or password.');
      }
    } catch (err) {
      if (err.data && err.data.needs_verification) {
        onNeedsVerification(err.data.email || email);
      } else {
        setError(err.message || 'Login failed. Please check credentials.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify Login OTP
  const handleOtpSubmit = async (e) => {
    e.preventDefault();
    const otpCode = digits.join('');
    if (otpCode.length !== 6) {
      setError('Please enter the complete 6-digit code.');
      const firstEmpty = digits.findIndex((d) => !d);
      if (firstEmpty !== -1) inputRefs.current[firstEmpty]?.focus();
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.verifyOtp(email, otpCode);
      if (res && res.success) {
        addToast('Authentication verified. Welcome to DeepVision!', 'success');
        await checkAuth();
        onNavigate('dashboard');
      } else {
        setError(res?.error || 'Verification failed. Code may be invalid or expired.');
      }
    } catch (err) {
      setError(err.message || 'Invalid or expired verification code.');
    } finally {
      setLoading(false);
    }
  };

  // Resend Login OTP
  const handleResendOtp = async () => {
    if (cooldown > 0 || resending) return;
    try {
      setResending(true);
      setError(null);
      const res = await api.auth.resendOtp(email);
      addToast(res.message || 'A new verification code has been dispatched.', 'info');
      setCooldown(60);
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } catch (err) {
      setError(err.message || 'Failed to resend code.');
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout>
      {step === 'credentials' ? (
        <>
          <div className="auth-header" style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
            <h2 className="auth-title" style={{ fontSize: '1.55rem', fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--text-main)', marginBottom: '6px' }}>
              Surveillance Operations Center
            </h2>
            <p className="auth-subtitle" style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: 0 }}>
              Hardware Camera Ingestion &amp; Optical AI Control
            </p>
          </div>

          <div style={{ marginBottom: '1.25rem', padding: '8px 12px', background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: '#10b981' }}></span>
            <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>Operator Workstation &bull; Two-Factor Authentication</span>
          </div>


          {error && (
            <div className="auth-alert-banner alert-danger" style={{ marginBottom: '1.25rem' }}>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleCredentialsSubmit} id="login-form" noValidate>
            {/* Email Input */}
            <div className="form-group">
              <label className="form-label" htmlFor="email">Email Address</label>
              <input
                type="email"
                id="email"
                name="email"
                className="form-control"
                placeholder="operator@deepvision.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                autoComplete="email"
              />
            </div>

            {/* Password Input with Eye Toggle */}
            <div className="form-group">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <label className="form-label" htmlFor="password" style={{ marginBottom: 0 }}>Password</label>
                <a
                  href="#forgot-password"
                  onClick={(e) => { e.preventDefault(); onNavigate('forgot-password'); }}
                  style={{ fontSize: '0.8rem', color: 'var(--color-primary)', textDecoration: 'none' }}
                >
                  Forgot password?
                </a>
              </div>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  name="password"
                  className="form-control"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  style={{ paddingRight: '2.75rem' }}
                />
                <button
                  type="button"
                  id="toggle-password"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '0.75rem',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-secondary)',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center',
                  }}
                  title="Show/hide password"
                  aria-label="Toggle password visibility"
                >
                  {showPassword ? (
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                      <line x1="1" y1="1" x2="23" y2="23"></line>
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                      <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Remember Me */}
            <div className="form-group">
              <label className="form-check" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  name="remember"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Remember this workstation for 30 days</span>
              </label>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary btn-lg"
              style={{ width: '100%', marginTop: '0.5rem' }}
            >
              {loading ? 'Signing In...' : 'Sign In'}
            </button>

            <div className="auth-footer-text">
              No account yet?{' '}
              <a
                href="#signup"
                onClick={(e) => { e.preventDefault(); onNavigate('signup'); }}
                style={{ fontWeight: 600 }}
              >
                Create account
              </a>
            </div>
          </form>
        </>
      ) : (
        /* STEP 2: TWO-FACTOR AUTHENTICATION / LOGIN OTP */
        <>
          <div className="auth-header">
            <h2 className="auth-title">Two-Factor Authentication</h2>
            <p className="auth-subtitle">
              Enter Sign-In Code sent to <strong style={{ color: 'var(--text-main)' }}>{email}</strong>
            </p>
          </div>

          {error && (
            <div className="auth-alert-banner alert-danger" style={{ marginBottom: '1.25rem' }}>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleOtpSubmit} id="login-otp-form" noValidate>
            <div className="form-group" style={{ textAlign: 'center' }}>
              <label className="form-label" style={{ marginBottom: '0.75rem' }}>
                Verification Code
              </label>

              {/* 6 Digit Input Boxes */}
              <div
                id="otpBoxes"
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  gap: '8px',
                  marginBottom: '1rem',
                }}
              >
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
                    onPaste={idx === 0 ? handlePaste : undefined}
                    style={{
                      width: '46px',
                      height: '52px',
                      fontSize: '1.4rem',
                      fontWeight: 700,
                      textAlign: 'center',
                      borderRadius: '8px',
                      border: '1px solid var(--border-color)',
                      background: 'var(--bg-surface-raised, #182232)',
                      color: 'var(--text-main)',
                      outline: 'none',
                    }}
                  />
                ))}
              </div>

              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Security check: Code expires in 15 minutes.
              </span>
            </div>

            {/* Verify Button */}
            <button
              type="submit"
              id="btn-verify-login"
              disabled={loading || digits.join('').length !== 6}
              className="btn btn-primary btn-lg"
              style={{ width: '100%', marginTop: '0.75rem' }}
            >
              {loading ? 'Verifying Code...' : 'Verify Sign-In Code'}
            </button>

            {/* Resend & Back controls */}
            <div style={{ marginTop: '1.25rem', textAlign: 'center', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <span>Didn't receive it? </span>
              <button
                type="button"
                onClick={handleResendOtp}
                disabled={cooldown > 0 || resending}
                style={{
                  background: 'none',
                  border: 'none',
                  color: cooldown > 0 ? 'var(--text-muted)' : 'var(--color-primary)',
                  fontWeight: 600,
                  cursor: cooldown > 0 ? 'default' : 'pointer',
                  padding: 0,
                }}
              >
                {resending ? 'Sending...' : cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend Code'}
              </button>
            </div>

            <div style={{ marginTop: '1rem', textAlign: 'center' }}>
              <button
                type="button"
                onClick={() => { setStep('credentials'); setError(null); }}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '0.8rem', cursor: 'pointer' }}
              >
                &larr; Back to Email &amp; Password
              </button>
            </div>
          </form>
        </>
      )}
    </AuthLayout>
  );
}

export default Login;
