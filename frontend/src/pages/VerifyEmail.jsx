import React, { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import AuthLayout from '../layouts/AuthLayout';
import { useToast } from '../components/common/Toast';

export function VerifyEmail({ email, onVerified, onNavigate }) {
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [cooldown, setCooldown] = useState(60);
  const [error, setError] = useState(null);
  const inputRefs = useRef([]);
  const { addToast } = useToast();

  useEffect(() => {
    inputRefs.current[0]?.focus();
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((c) => c - 1);
    }, 1000);
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

  const otpCode = digits.join('');

  const handleVerify = async (e) => {
    e.preventDefault();
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
        addToast('Email verified successfully!', 'success');
        onVerified();
      } else {
        setError(res?.error || 'Verification failed.');
      }
    } catch (err) {
      setError(err.message || 'Verification failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (cooldown > 0) return;
    try {
      setResending(true);
      setError(null);
      const res = await api.auth.resendOtp(email);
      addToast(res.message || 'New verification code sent', 'info');
      setCooldown(60);
    } catch (err) {
      setError(err.message || 'Failed to resend code');
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout>
      <div className="auth-header">
        <h2 className="auth-title">Verify Your Email</h2>
        <p className="auth-subtitle">
          Enter the 6-digit code sent to<br />
          <strong style={{ color: 'var(--text-main)', fontFamily: 'var(--font-mono)', fontSize: '0.95rem' }}>
            {email}
          </strong>
        </p>
      </div>

      {error && (
        <div className="auth-alert-banner alert-danger" style={{ marginBottom: '1.25rem' }}>
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleVerify} id="otp-form" noValidate>
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
          disabled={loading || otpCode.length < 6}
          className="btn btn-primary btn-lg"
          id="btn-verify"
          style={{ width: '100%', marginTop: '0.25rem' }}
        >
          {loading ? 'Verifying...' : 'Verify Code'}
        </button>
      </form>

      {/* Resend OTP Action with Cooldown Timer */}
      <div style={{ marginTop: '1.5rem', textAlign: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Didn't receive it? </span>
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

      <div className="auth-footer-text" style={{ marginTop: '1.25rem' }}>
        Wrong email address?{' '}
        <a
          href="#signup"
          onClick={(e) => { e.preventDefault(); onNavigate('signup'); }}
          style={{ fontWeight: 600 }}
        >
          Sign up with another email
        </a>
      </div>
    </AuthLayout>
  );
}

export default VerifyEmail;
