import React, { useState } from 'react';
import { api } from '../services/api';
import AuthLayout from '../layouts/AuthLayout';

export function Signup({ onNavigate, onSignedUp }) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Password strength calculation matching original signup.html
  const getStrength = (pw) => {
    if (!pw) return null;
    let score = 0;
    if (pw.length >= 8) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[a-z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;

    const levels = [
      { pct: '20%', color: '#ef4444', text: 'Very weak' },
      { pct: '40%', color: '#f97316', text: 'Weak' },
      { pct: '60%', color: '#eab308', text: 'Fair' },
      { pct: '80%', color: '#3b82f6', text: 'Strong' },
      { pct: '100%', color: '#10b981', text: 'Very strong' },
    ];
    return levels[score - 1] || levels[0];
  };

  const strength = getStrength(password);
  const passwordsMatch = confirmPassword ? password === confirmPassword : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.auth.signup({
        full_name: fullName,
        email,
        password,
        confirm_password: confirmPassword,
      });

      if (res && res.success) {
        onSignedUp(email);
      } else {
        setError(res?.error || 'Registration failed.');
      }
    } catch (err) {
      setError(err.message || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className="auth-header">
        <h2 className="auth-title">Create Your Account</h2>
        <p className="auth-subtitle">Register as a new surveillance operator.</p>
      </div>

      {error && (
        <div className="auth-alert-banner alert-danger" style={{ marginBottom: '1.25rem' }}>
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} id="signup-form" noValidate>
        {/* Full Name */}
        <div className="form-group">
          <label className="form-label" htmlFor="full_name">Full Name</label>
          <input
            type="text"
            id="full_name"
            name="full_name"
            className="form-control"
            placeholder="Jane Doe"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            autoFocus
            autoComplete="name"
          />
        </div>

        {/* Email */}
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
            autoComplete="email"
          />
        </div>

        {/* Password with toggle */}
        <div className="form-group">
          <label className="form-label" htmlFor="password">Password</label>
          <div style={{ position: 'relative' }}>
            <input
              type={showPassword ? 'text' : 'password'}
              id="password"
              name="password"
              className="form-control"
              placeholder="Min. 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
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
              aria-label="Toggle password visibility"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            </button>
          </div>
          {/* Password strength bar */}
          {strength && (
            <div style={{ height: '3px', borderRadius: '2px', marginTop: '0.4rem', background: 'var(--border-color)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: strength.pct, backgroundColor: strength.color, transition: 'width 0.3s, background-color 0.3s' }}></div>
            </div>
          )}
          {strength && (
            <div style={{ fontSize: '0.75rem', marginTop: '0.25rem', color: strength.color }}>
              {strength.text}
            </div>
          )}
        </div>

        {/* Confirm Password with toggle */}
        <div className="form-group">
          <label className="form-label" htmlFor="confirm_password">Confirm Password</label>
          <div style={{ position: 'relative' }}>
            <input
              type={showConfirmPassword ? 'text' : 'password'}
              id="confirm_password"
              name="confirm_password"
              className="form-control"
              placeholder="Re-enter password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
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
              aria-label="Toggle confirm password visibility"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            </button>
          </div>
          {passwordsMatch !== null && (
            <div style={{ fontSize: '0.75rem', marginTop: '0.25rem', color: passwordsMatch ? '#10b981' : '#ef4444' }}>
              {passwordsMatch ? 'Passwords match' : 'Passwords do not match'}
            </div>
          )}
        </div>

        {/* Password requirements hint */}
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1rem', padding: '0.6rem 0.75rem', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
          Password must be at least <strong>8 characters</strong> and include uppercase, lowercase, a number, and a special character.
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary btn-lg"
          style={{ width: '100%' }}
        >
          {loading ? 'Creating Account...' : 'Create Account'}
        </button>

        <div className="auth-footer-text">
          Already have an account?{' '}
          <a
            href="#login"
            onClick={(e) => { e.preventDefault(); onNavigate('login'); }}
            style={{ fontWeight: 600 }}
          >
            Sign in
          </a>
        </div>
      </form>
    </AuthLayout>
  );
}

export default Signup;
