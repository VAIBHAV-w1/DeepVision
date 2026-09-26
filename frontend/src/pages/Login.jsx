import React, { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import AuthLayout from '../layouts/AuthLayout';

export function Login({ onNavigate, onNeedsVerification }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Email and password are required.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await login(email, password, remember);
      if (res && res.success) {
        onNavigate('dashboard');
      } else if (res && res.needs_verification) {
        onNeedsVerification(res.email || email);
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

  return (
    <AuthLayout>
      <div className="auth-header">
        <h2 className="auth-title">Sign In to DeepVision</h2>
        <p className="auth-subtitle">Access your surveillance control panel.</p>
      </div>

      {error && (
        <div className="auth-alert-banner alert-danger" style={{ marginBottom: '1.25rem' }}>
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} id="login-form" noValidate>
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
    </AuthLayout>
  );
}

export default Login;
