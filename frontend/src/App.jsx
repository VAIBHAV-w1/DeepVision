import React, { useState, useEffect } from 'react';
import { LanguageProvider } from './i18n/i18nContext';
import { AuthProvider, useAuth } from './hooks/useAuth';
import ToastProvider from './components/common/Toast';
import AppLayout from './layouts/AppLayout';

import ErrorBoundary from './components/common/ErrorBoundary';

const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Cameras = React.lazy(() => import('./pages/Cameras'));
const CameraPreview = React.lazy(() => import('./pages/CameraPreview'));
const Recordings = React.lazy(() => import('./pages/Recordings'));
const Evidence = React.lazy(() => import('./pages/Evidence'));
const Alerts = React.lazy(() => import('./pages/Alerts'));
const Cases = React.lazy(() => import('./pages/Cases'));
const Notifications = React.lazy(() => import('./pages/Notifications'));
const Help = React.lazy(() => import('./pages/Help'));
const Login = React.lazy(() => import('./pages/Login'));
const Signup = React.lazy(() => import('./pages/Signup'));
const ForgotPassword = React.lazy(() => import('./pages/ForgotPassword'));
const VerifyEmail = React.lazy(() => import('./pages/VerifyEmail'));

const PageLoader = () => (
  <div style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '14px' }}>
    <div style={{ width: '32px', height: '32px', border: '3px solid var(--border-color)', borderTopColor: 'var(--color-primary)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    <span style={{ fontSize: '0.84rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>Loading DeepVision module...</span>
  </div>
);

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [route, queryString] = raw.split('?');
  const params = new URLSearchParams(queryString || '');
  return {
    page: route || 'dashboard',
    params: Object.fromEntries(params.entries()),
  };
}

function MainApp() {
  const { isAuthenticated, loading, checkAuth } = useAuth();
  const [{ page: activePage, params: pageParams }, setRoute] = useState(parseHash);
  const [unverifiedEmail, setUnverifiedEmail] = useState('');

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(parseHash());
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigate = (page, params = {}) => {
    const query = new URLSearchParams(params).toString();
    const hash = `#${page}${query ? '?' + query : ''}`;
    window.location.hash = hash;
    setRoute({ page, params });
  };

  if (loading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'var(--bg-canvas)',
          color: 'var(--text-main)',
          gap: '16px',
        }}
      >
        <div style={{ width: '40px', height: '40px', border: '3px solid var(--border-color)', borderTopColor: 'var(--color-primary)', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
        <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Initializing DeepVision SOC...</div>
      </div>
    );
  }

  // Unauthenticated routing
  if (!isAuthenticated) {
    let unauthContent;
    if (unverifiedEmail) {
      unauthContent = (
        <VerifyEmail
          email={unverifiedEmail}
          onVerified={() => { setUnverifiedEmail(''); checkAuth(); navigate('login'); }}
          onNavigate={(p) => { setUnverifiedEmail(''); navigate(p); }}
        />
      );
    } else if (activePage === 'signup') {
      unauthContent = (
        <Signup
          onNavigate={navigate}
          onSignedUp={(email) => setUnverifiedEmail(email)}
        />
      );
    } else if (activePage === 'forgot-password' || activePage === 'reset-password') {
      unauthContent = <ForgotPassword onNavigate={navigate} />;
    } else {
      unauthContent = (
        <Login
          onNavigate={navigate}
          onNeedsVerification={(email) => setUnverifiedEmail(email)}
        />
      );
    }
    return (
      <React.Suspense fallback={<PageLoader />}>
        {unauthContent}
      </React.Suspense>
    );
  }

  // Authenticated SOC App Routing
  const renderActivePage = () => {
    switch (activePage) {
      case 'cameras':
        return <Cameras onNavigate={navigate} />;
      case 'camera-preview':
        return (
          <CameraPreview
            cameraId={pageParams.id ? Number(pageParams.id) : 1}
            onNavigate={navigate}
          />
        );
      case 'recordings':
        return (
          <Recordings
            initialCameraId={pageParams.camera_id}
            selectedId={pageParams.selectedId}
            onNavigate={navigate}
          />
        );
      case 'evidence':
        return (
          <Evidence
            initialCameraId={pageParams.camera_id}
            initialAlertId={pageParams.alertId}
            selectedId={pageParams.selectedId}
            onNavigate={navigate}
          />
        );
      case 'alerts':
        return (
          <Alerts
            initialCameraId={pageParams.camera_id}
            selectedId={pageParams.selectedId}
            initialHasVideo={pageParams.has_video}
            initialHasCase={pageParams.has_case}
            onNavigate={navigate}
          />
        );
      case 'cases':
        return (
          <Cases
            selectedId={pageParams.selectedId}
            initialAlertId={pageParams.alertId}
            onNavigate={navigate}
          />
        );
      case 'notifications':
        return <Notifications onNavigate={navigate} />;
      case 'help':
        return <Help onNavigate={navigate} />;
      case 'dashboard':
      default:
        return <Dashboard onNavigate={navigate} />;
    }
  };

  return (
    <AppLayout
      activePage={activePage === 'camera-preview' ? 'cameras' : activePage}
      setActivePage={navigate}
    >
      <ErrorBoundary onReset={() => navigate('dashboard')}>
        <React.Suspense fallback={<PageLoader />}>
          {renderActivePage()}
        </React.Suspense>
      </ErrorBoundary>
    </AppLayout>
  );
}

export function App() {
  return (
    <LanguageProvider>
      <ToastProvider>
        <AuthProvider>
          <MainApp />
        </AuthProvider>
      </ToastProvider>
    </LanguageProvider>
  );
}

export default App;
