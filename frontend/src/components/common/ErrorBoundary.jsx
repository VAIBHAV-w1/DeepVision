import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('[DeepVision React ErrorBoundary caught an exception]:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    } else {
      window.location.hash = '#dashboard';
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          className="error-boundary-container"
          style={{
            minHeight: '60vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            textAlign: 'center',
            background: 'var(--bg-surface, #111827)',
            borderRadius: 'var(--radius-lg, 12px)',
            border: '1px solid var(--border-color, #1f2937)',
            margin: '2rem auto',
            maxWidth: '720px',
            color: 'var(--text-main, #f9fafb)',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.25rem',
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 10.29 3.86 L 1.82 18 a 2 2 0 0 0 1.71 3 h 16.94 a 2 2 0 0 0 1.71 -3 L 13.71 3.86 a 2 2 0 0 0 -3.42 0 z"></path>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
          </div>

          <h2 style={{ fontSize: '1.4rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            {this.props.title || 'Component Recovered from Error'}
          </h2>

          <p style={{ color: 'var(--text-muted, #9ca3af)', fontSize: '0.9rem', maxWidth: '480px', marginBottom: '1.5rem', lineHeight: 1.5 }}>
            {this.state.error?.message || 'An unexpected rendering error occurred. The DeepVision security operations platform prevented an application crash.'}
          </p>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'center' }}>
            <button
              type="button"
              onClick={this.handleReset}
              className="btn btn-primary btn-sm"
              style={{ padding: '0.5rem 1.25rem' }}
            >
              Reload View
            </button>
            <button
              type="button"
              onClick={() => { window.location.hash = '#dashboard'; window.location.reload(); }}
              className="btn btn-secondary btn-sm"
              style={{ padding: '0.5rem 1.25rem' }}
            >
              Return to Dashboard
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
