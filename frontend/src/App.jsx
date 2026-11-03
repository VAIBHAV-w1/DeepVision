import React, { useState, useEffect } from 'react';
import { LanguageProvider } from './i18n/i18nContext';
import { AuthProvider, useAuth } from './hooks/useAuth';
import ToastProvider from './components/common/Toast';
import AppLayout from './layouts/AppLayout';
import ErrorBoundary from './components/common/ErrorBoundary';

// Five primary workspaces
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Cameras = React.lazy(() => import('./pages/Cameras'));
const Notifications = React.lazy(() => import('./pages/Notifications'));
const Settings = React.lazy(() => import('./pages/Settings'));
const Help = React.lazy(() => import('./pages/Help'));
const Legal = React.lazy(() => import('./pages/Legal'));

// Authentication
const Login = React.lazy(() => import('./pages/Login'));
const Signup = React.lazy(() => import('./pages/Signup'));
const ForgotPassword = React.lazy(() => import('./pages/ForgotPassword'));
const VerifyEmail = React.lazy(() => import('./pages/VerifyEmail'));

const PageLoader = () => (
  <div style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '14px' }}>
    <div style={{ width: '32px', height: '32px', border: '3px solid var(--dv-border-subtle, #1A2436)', borderTopColor: 'var(--dv-cyan-500, #00D2FF)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    <span style={{ fontSize: '0.84rem', color: 'var(--dv-text-muted, #64748B)', fontFamily: 'var(--dv-font-mono, monospace)' }}>Loading DeepVision module...</span>
  </div>
);

function parseRoute() {
  const rawHash = window.location.hash.replace(/^#\/?/, '');
  if (rawHash) {
    const [route, queryString] = rawHash.split('?');
    const params = new URLSearchParams(queryString || '');
    const p = (route || 'overview').toLowerCase();
    const paramObj = Object.fromEntries(params.entries());

    // 1. Overview & Dashboard
    if (p === 'overview' || p === 'dashboard') {
      return { page: 'dashboard', params: paramObj };
    }

    // 2. Live Monitoring
    if (p === 'live' || p === 'live-monitoring' || p === 'surveillance' || p === 'monitor' || p === 'live-feeds') {
      return { page: 'cameras', params: { ...paramObj, camera: paramObj.camera || '4' } };
    }

    // 3. Hardware Camera Inventory
    if (p === 'cameras') {
      return { page: 'cameras', params: paramObj };
    }

    if (p === 'camera-preview') {
      const camId = params.get('id') || params.get('camera') || '4';
      return { page: 'cameras', params: { ...paramObj, camera: camId } };
    }

    // 4. Security Events / Alerts
    if (p === 'alerts' || p === 'security-events' || (p === 'security-center' && paramObj.tab === 'alerts')) {
      return { page: 'notifications', params: { ...paramObj, tab: 'incidents', incident: paramObj.incident || paramObj.id || paramObj.alert_id } };
    }

    // 5. Recordings
    if (p === 'recordings' || (p === 'security-center' && paramObj.tab === 'recordings')) {
      return { page: 'notifications', params: { ...paramObj, tab: 'recordings' } };
    }

    // 6. Evidence Vault
    if (p === 'evidence' || (p === 'security-center' && paramObj.tab === 'evidence')) {
      return { page: 'notifications', params: { ...paramObj, tab: 'evidence' } };
    }

    // 7. Incident Cases
    if (p === 'cases' || (p === 'security-center' && paramObj.tab === 'cases')) {
      return { page: 'notifications', params: { ...paramObj, tab: 'cases' } };
    }

    // 8. Notifications
    if (p === 'notifications' || (p === 'security-center' && paramObj.tab === 'notifications')) {
      return { page: 'notifications', params: paramObj };
    }

    // 9. Settings
    if (p === 'settings') {
      return { page: 'settings', params: paramObj };
    }

    // 10. Help & Documentation
    if (p === 'help' || p === 'support') {
      return { page: 'help', params: paramObj };
    }

    return {
      page: p,
      params: paramObj,
    };
  }

  // Parse direct pathname for full URL routes (/overview/, /live/, /cameras/, /alerts/, etc.)
  const path = window.location.pathname.replace(/^\/|\/$/g, '');
  if (path) {
    const parts = path.split('/');
    const p = parts[0].toLowerCase();
    const pathId = parts[1];
    const searchParams = new URLSearchParams(window.location.search);
    const paramObj = Object.fromEntries(searchParams.entries());

    if (p === 'overview' || p === 'dashboard') {
      return { page: 'dashboard', params: paramObj };
    }
    if (p === 'live' || p === 'surveillance' || p === 'monitor') {
      return { page: 'cameras', params: { ...paramObj, camera: paramObj.camera || '4' } };
    }
    if (p === 'cameras') {
      if (parts[1]) {
        return { page: 'cameras', params: { ...paramObj, camera: parts[1] } };
      }
      return { page: 'cameras', params: paramObj };
    }
    if (p === 'alerts' || p === 'security-events') return { page: 'notifications', params: { ...paramObj, tab: 'incidents', incident: paramObj.incident || paramObj.id || paramObj.alert_id || pathId } };
    if (p === 'recordings') return { page: 'notifications', params: { ...paramObj, tab: 'recordings', ...(pathId ? { id: pathId } : {}) } };
    if (p === 'evidence') return { page: 'notifications', params: { ...paramObj, tab: 'evidence', ...(pathId ? { id: pathId } : {}) } };
    if (p === 'cases') return { page: 'notifications', params: { ...paramObj, tab: 'cases', ...(pathId ? { id: pathId } : {}) } };
    if (p === 'notifications') return { page: 'notifications', params: paramObj };
    if (p === 'settings') return { page: 'settings', params: paramObj };
    if (p === 'help') return { page: 'help', params: paramObj };

    return {
      page: p || 'overview',
      params: paramObj,
    };
  }

  return {
    page: 'dashboard',
    params: {},
  };
}

function MainApp() {
  const { isAuthenticated, loading, checkAuth } = useAuth();
  const [{ page: activePage, params: pageParams }, setRoute] = useState(parseRoute);
  const [unverifiedEmail, setUnverifiedEmail] = useState('');
  const [emailDeliveryWarning, setEmailDeliveryWarning] = useState(false);

  useEffect(() => {
    const handleRouteChange = () => {
      const parsed = parseRoute();
      setRoute(parsed);
      const rawHash = (window.location.hash.replace(/^#\/?/, '').split('?')[0] || '').toLowerCase();
      if (['alerts', 'security-events', 'recordings', 'evidence', 'cases', 'security-center', 'live', 'surveillance', 'monitor', 'camera-preview', 'overview'].includes(rawHash)) {
        const query = new URLSearchParams(parsed.params).toString();
        const canonicalHash = `#${parsed.page}${query ? '?' + query : ''}`;
        if (window.location.hash !== canonicalHash) {
          window.history.replaceState(null, '', canonicalHash);
        }
      }
    };
    window.addEventListener('hashchange', handleRouteChange);
    window.addEventListener('popstate', handleRouteChange);
    return () => {
      window.removeEventListener('hashchange', handleRouteChange);
      window.removeEventListener('popstate', handleRouteChange);
    };
  }, []);

  const navigate = (page, params = {}) => {
    let canonicalPage = ['live', 'live-monitoring', 'surveillance', 'monitor', 'camera-preview'].includes(page) ? 'cameras'
      : ['overview', 'dashboard'].includes(page) ? 'dashboard' : page;
    let canonicalParams = params;
    if (['alerts', 'security-events'].includes(page)) { canonicalPage = 'notifications'; canonicalParams = { ...params, tab: 'incidents', incident: params.incident || params.id || params.alert_id }; delete canonicalParams.id; delete canonicalParams.alert_id; }
    if (['recordings', 'evidence', 'cases'].includes(page)) { canonicalPage = 'notifications'; canonicalParams = { ...params, tab: page }; }
    const query = new URLSearchParams(canonicalParams).toString();
    const hash = `#${canonicalPage}${query ? '?' + query : ''}`;
    window.location.hash = hash;
    setRoute({ page: canonicalPage, params: canonicalParams });
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
          backgroundColor: 'var(--bg-canvas, #090d16)',
          color: 'var(--text-main, #f8fafc)',
          gap: '16px',
        }}
      >
        <div style={{ width: '40px', height: '40px', border: '3px solid var(--border-color, #24324A)', borderTopColor: 'var(--dv-cyan-500, #00E5FF)', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
        <div style={{ fontSize: '0.9rem', color: 'var(--text-muted, #64748B)' }}>Initializing DeepVision SOC...</div>
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
          deliveryWarning={emailDeliveryWarning}
          onVerified={() => { setUnverifiedEmail(''); checkAuth(); navigate('login'); }}
          onNavigate={(p) => { setUnverifiedEmail(''); setEmailDeliveryWarning(false); navigate(p); }}
        />
      );
    } else if (activePage === 'signup') {
      unauthContent = (
        <Signup
          onNavigate={navigate}
          onSignedUp={(email, deliveryFailed) => {
            setUnverifiedEmail(email);
            setEmailDeliveryWarning(Boolean(deliveryFailed));
          }}
        />
      );
    } else if (activePage === 'forgot-password' || activePage === 'reset-password') {
      unauthContent = <ForgotPassword onNavigate={navigate} />;
    } else if (activePage === 'privacy' || activePage === 'terms' || activePage === 'legal') {
      unauthContent = (
        <div style={{ minHeight: '100vh', background: 'var(--bg-canvas)', padding: '2rem 1rem' }}>
          <div style={{ maxWidth: '960px', margin: '0 auto 1.5rem auto' }}>
            <button
              type="button"
              onClick={() => navigate('login')}
              className="btn btn-secondary btn-sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            >
              &larr; Back to Login
            </button>
          </div>
          <Legal initialTab={activePage === 'terms' ? 'terms' : 'privacy'} onNavigate={navigate} />
        </div>
      );
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

  // Legacy live routes resolve into the unified Cameras workspace.
  const renderActivePage = () => {
    switch (activePage) {
      case 'dashboard':
      case 'overview':
        return <Dashboard onNavigate={navigate} />;

      case 'live':
      case 'surveillance':
      case 'monitor':
      case 'camera-preview':
        return (
          <Cameras
            initialCameraId={pageParams.camera || pageParams.id || 4}
            pageParams={pageParams}
            onNavigate={navigate}
          />
        );

      case 'cameras':
        return <Cameras initialCameraId={pageParams.camera} pageParams={pageParams} onNavigate={navigate} />;

      case 'notifications':
        return <Notifications onNavigate={navigate} pageParams={pageParams} />;

      case 'settings':
        return <Settings onNavigate={navigate} />;

      case 'help':
      case 'support':
        return <Help onNavigate={navigate} />;

      case 'privacy':
      case 'terms':
      case 'legal':
        return <Legal initialTab={activePage === 'terms' ? 'terms' : 'privacy'} onNavigate={navigate} />;

      default:
        return <Dashboard onNavigate={navigate} />;
    }
  };

  return (
    <AppLayout
      activePage={activePage}
      pageParams={pageParams}
      setActivePage={navigate}
    >
      <ErrorBoundary onReset={() => navigate('overview')}>
        <React.Suspense fallback={<PageLoader />}>
          {renderActivePage()}
        </React.Suspense>
      </ErrorBoundary>
    </AppLayout>
  );
}

export default function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <ToastProvider>
          <MainApp />
        </ToastProvider>
      </AuthProvider>
    </LanguageProvider>
  );
}
