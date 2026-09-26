import React, { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import AuthLayout from '../layouts/AuthLayout';
import { useToast } from '../components/common/Toast';

export function ForgotPassword({ onNavigate }) {
  // Step 1: email, Step 2: otp, Step 3: new password
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [error, setError] = useState(null);
  const inputRefs = useRef([]);
  const { addToast } = useToast();

  useEffect(() => {
    if (step === 2) {
      inputRefs.current[0]?.focus();
    }
  }, [step]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

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

  // Password strength
  const getStrength = (pw) => {
    if (!pw) return null;
    let score = 0;
    if (pw.length >= 8) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[a-z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;

    const levels = [
      { w: '20%', c: '#ef4444', l: 'Very Weak' },
      { w: '40%', c: '#f97316', l: 'Weak' },
      { w: '60%', c: '#eab308', l: 'Medium' },
      { w: '80%', c: '#3b82f6', l: 'Strong' },
      { w: '100%', c: '#10b981', l: 'Very Strong' },
    ];
    return levels[score - 1] || levels[0];
  };

  const strength = getStrength(newPassword);
  const passwordsMatch = confirmPassword ? newPassword === confirmPassword : null;

  // Step 1: Submit email
  const handleEmailSubmit = async (e) => {
    e.preventDefault();
    if (!email) return;
    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.forgotPassword(email);
      addToast(res.message || 'Verification code sent to your email', 'info');
      setStep(2);
      setCooldown(60);
    } catch (err) {
      setError(err.message || 'Failed to request password reset');
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify OTP
  const handleOtpSubmit = (e) => {
    e.preventDefault();
    const code = digits.join('');
    if (code.length !== 6) {
      setError('Please enter the full 6-digit recovery code.');
      return;
    }
    setError(null);
    setStep(3);
  };

  // Resend OTP
  const handleResend = async () => {
    if (cooldown > 0) return;
    try {
      setResending(true);
      setError(null);
      const res = await api.auth.forgotPassword(email);
      addToast(res.message || 'New recovery code sent', 'info');
      setCooldown(60);
    } catch (err) {
      setError(err.message || 'Failed to resend code');
    } finally {
      setResending(false);
    }
  };

  // Step 3: Reset password
  const handleResetSubmit = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.resetPassword(email, digits.join(''), newPassword, confirmPassword);
      if (res && res.success) {
        addToast('Password successfully reset! You can now sign in.', 'success');
        onNavigate('login');
      } else {
        setError(res?.error || 'Password reset failed.');
      }
    } catch (err) {
      setError(err.message || 'Password reset failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      {error && (
        <div className="auth-alert-banner alert-danger" style={{ marginBottom: '1.25rem' }}>
          <span>{error}</span>
        </div>
      )}

      {step === 1 && (
        <>
          <div className="auth-header">
            <h2 className="auth-title">Reset Your Password</h2>
            <p className="auth-subtitle">Enter your registered email address to receive password recovery instructions.</p>
          </div>

          <form onSubmit={handleEmailSubmit} noValidate>
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
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary btn-lg"
              style={{ width: '100%', marginTop: '0.5rem' }}
            >
              {loading ? 'Sending...' : 'Send Recovery Email'}
            </button>

            <div className="auth-footer-text">
              Remember your credentials?{' '}
              <a
                href="#login"
                onClick={(e) => { e.preventDefault(); onNavigate('login'); }}
                style={{ fontWeight: 600 }}
              >
                Back to sign in
              </a>
            </div>
          </form>
        </>
      )}

      {step === 2 && (
        <>
          <div className="auth-header">
            <h2 className="auth-title">Reset Verification Code</h2>
            <p className="auth-subtitle">
              Enter the 6-digit recovery code sent to<br />
              <strong style={{ color: 'var(--text-main)', fontFamily: 'var(--font-mono)', fontSize: '0.95rem' }}>
                {email}
              </strong>
            </p>
          </div>

          <form onSubmit={handleOtpSubmit} id="reset-otp-form" noValidate>
            <div className="form-group" style={{ marginBottom: '0.75rem' }}>
              <label className="form-label" style={{ textAlign: 'center', display: 'block', marginBottom: '0.25rem' }}>
                Enter 6-Digit Code
              </label>

              <div className="otp-boxes-grid" id="otpBoxes">
                {digits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (inputRefs.current[idx] = el)}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={1}
                    className={`otp-box-digit ${digit ? 'is-filled' : ''}`}
                    data-idx={idx}
                    value={digit}
                    onChange={(e) => handleDigitChange(idx, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(idx, e)}
                    onPaste={handlePaste}
                    required
                    autoComplete="off"
                  />
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={digits.join('').length < 6}
              className="btn btn-primary btn-lg"
              id="btn-verify"
              style={{ width: '100%', marginTop: '0.25rem' }}
            >
              Verify Code
            </button>
          </form>

          {/* Resend Action with Cooldown Timer */}
          <div style={{ marginTop: '1.5rem', textAlign: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Didn't receive code? </span>
            {cooldown > 0 ? (
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Please wait <strong style={{ color: 'var(--color-primary)' }}>{cooldown}s</strong> before requesting another code
              </span>
            ) : (
              <button
                type="button"
                onClick={handleResend}
                disabled={resending}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-primary)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  fontSize: '0.85rem',
                  padding: '0 0.35rem',
                }}
              >
                {resending ? 'Sending...' : 'Resend Code'}
              </button>
            )}
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <div className="auth-header">
            <h2 className="auth-title">Set New Password</h2>
            <p className="auth-subtitle">Create a secure new password for your account.</p>
          </div>

          <form onSubmit={handleResetSubmit} id="reset-pw-form" noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="password">New Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  name="password"
                  className="form-control"
                  placeholder="••••••••"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  autoFocus
                  style={{ paddingRight: '2.75rem' }}
                />
                <button
                  type="button"
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
                  title="Toggle password visibility"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                  </svg>
                </button>
              </div>

              {strength && (
                <div style={{ height: '4px', borderRadius: '2px', background: 'var(--border-color)', marginTop: '0.4rem', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: strength.w, backgroundColor: strength.c, transition: 'width 0.3s ease, background-color 0.3s ease' }}></div>
                </div>
              )}
              {strength && (
                <span style={{ fontSize: '0.74rem', color: strength.c, marginTop: '0.2rem', display: 'block' }}>
                  Strength: {strength.l}
                </span>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="confirm_password">Confirm New Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  id="confirm_password"
                  name="confirm_password"
                  className="form-control"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  style={{ paddingRight: '2.75rem' }}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
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
                  title="Toggle confirm password visibility"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                  </svg>
                </button>
              </div>
              {passwordsMatch !== null && (
                <span style={{ fontSize: '0.74rem', marginTop: '0.2rem', display: 'block', color: passwordsMatch ? '#10b981' : '#ef4444' }}>
                  {passwordsMatch ? '✓ Passwords match' : '✕ Passwords do not match'}
                </span>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !newPassword || newPassword !== confirmPassword}
              className="btn btn-primary btn-lg"
              style={{ width: '100%', marginTop: '0.5rem' }}
            >
              {loading ? 'Updating Password...' : 'Update Password & Sign In'}
            </button>
          </form>
        </>
      )}
    </AuthLayout>
  );
}

export default ForgotPassword;
