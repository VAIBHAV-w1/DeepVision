import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const userRef = React.useRef(null);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const checkAuth = async () => {
    try {
      // Verify active session with backend (allows bounded retries during Render cold-start wakeup)
      const res = await authService.me({ timeout: 22000, maxRetries: 2 }).catch(() => null);
      if (res && res.authenticated && res.user) {
        setUser(res.user);
        return;
      }
      setUser(null);
    } catch (e) {
      setUser(null);
    } finally {
      // Guaranteed execution: loading state always resolves regardless of code path
      setLoading(false);
    }
  };

  useEffect(() => {
    // Hard ceiling: ensure loading state is never stuck longer than 28 seconds under any condition
    const startupTimeout = setTimeout(() => {
      setLoading((prev) => {
        if (prev) {
          console.warn('[DeepVision Auth] Startup timeout ceiling reached; forcing loader resolution.');
          return false;
        }
        return prev;
      });
    }, 28000);

    checkAuth().finally(() => {
      clearTimeout(startupTimeout);
    });

    const handleUnauthorized = () => {
      setUser(null);
    };

    let syncingMe = false;
    const handleBackendStatus = (ev) => {
      if (ev?.detail?.available === true && !syncingMe && !userRef.current) {
        // Edge-triggered recovery: re-verify session silently at most once per recovery transition
        syncingMe = true;
        authService.me({ timeout: 10000, maxRetries: 0 })
          .then((res) => {
            if (res && res.authenticated && res.user) {
              setUser(res.user);
            }
          })
          .catch(() => {})
          .finally(() => { syncingMe = false; });
      }
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    window.addEventListener('backend:status', handleBackendStatus);
    return () => {
      clearTimeout(startupTimeout);
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
      window.removeEventListener('backend:status', handleBackendStatus);
    };
  }, []);

  const login = async (email, password) => {
    const res = await authService.login(email, password);
    if (res && res.success && res.user) {
      setUser(res.user);
    }
    return res;
  };

  const logout = async () => {
    try {
      await authService.logout();
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        loading,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}

export default useAuth;
