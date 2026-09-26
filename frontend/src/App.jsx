import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './hooks/useAuth';
import ToastProvider from './components/common/Toast';
import AppLayout from './layouts/AppLayout';

import Dashboard from './pages/Dashboard';
import Cameras from './pages/Cameras';
import CameraPreview from './pages/CameraPreview';
import Recordings from './pages/Recordings';
import Evidence from './pages/Evidence';
import Alerts from './pages/Alerts';
import Cases from './pages/Cases';
import Notifications from './pages/Notifications';
import Help from './pages/Help';
import Login from './pages/Login';
import Signup from './pages/Signup';
import ForgotPassword from './pages/ForgotPassword';
import VerifyEmail from './pages/VerifyEmail';

import ErrorBoundary from './components/common/ErrorBoundary';

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
    if (unverifiedEmail) {
      return (
        <VerifyEmail
          email={unverifiedEmail}
          onVerified={() => { setUnverifiedEmail(''); checkAuth(); navigate('dashboard'); }}
          onNavigate={(p) => { setUnverifiedEmail(''); navigate(p); }}
        />
      );
    }
    if (activePage === 'signup') {
      return (
        <Signup
          onNavigate={navigate}
          onSignedUp={(email) => setUnverifiedEmail(email)}
        />
      );
    }
    if (activePage === 'forgot-password' || activePage === 'reset-password') {
      return <ForgotPassword onNavigate={navigate} />;
    }
    return (
      <Login
        onNavigate={navigate}
        onNeedsVerification={(email) => setUnverifiedEmail(email)}
      />
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
        {renderActivePage()}
      </ErrorBoundary>
    </AppLayout>
  );
}

export function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <MainApp />
      </AuthProvider>
    </ToastProvider>
  );
}

export default App;
