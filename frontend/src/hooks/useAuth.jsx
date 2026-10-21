import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = async () => {
    try {
      // 1. Verify active session with backend (with explicit 5-second timeout)
      const res = await authService.me({ timeout: 5000 }).catch(() => null);
      if (res && res.authenticated && res.user) {
        setUser(res.user);
        return;
      }

      // 2. Fall back to demo session if active in localStorage
      try {
        if (typeof localStorage !== 'undefined' && localStorage.getItem('deepvision_demo_session') === 'true') {
          setUser({
            id: 9999,
            username: 'soc_operator_demo',
            email: 'operator@deepvision.internal',
            first_name: 'SOC',
            last_name: 'Operator',
            role: 'operator',
            is_staff: false,
          });
          return;
        }
      } catch (e) {
        // localStorage restricted or disabled
      }

      // 3. Unauthenticated state
      setUser(null);
    } catch (e) {
      setUser(null);
    } finally {
      // Guaranteed execution: loading state always resolves regardless of code path
      setLoading(false);
    }
  };

  useEffect(() => {
    // Hard ceiling: ensure loading state is never stuck longer than 5 seconds under any condition
    const startupTimeout = setTimeout(() => {
      setLoading((prev) => {
        if (prev) {
          console.warn('[DeepVision Auth] Startup timeout ceiling reached; forcing loader resolution.');
          return false;
        }
        return prev;
      });
    }, 5000);

    checkAuth().finally(() => {
      clearTimeout(startupTimeout);
    });

    const handleUnauthorized = () => {
      try {
        if (typeof localStorage !== 'undefined' && localStorage.getItem('deepvision_demo_session') === 'true') {
          return;
        }
      } catch (e) {}
      setUser(null);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      clearTimeout(startupTimeout);
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, []);

  const login = async (email, password) => {
    const res = await authService.login(email, password);
    if (res && res.success && res.user) {
      setUser(res.user);
    }
    return res;
  };

  const loginAsDemo = () => {
    const demoUser = {
      id: 9999,
      username: 'soc_operator_demo',
      email: 'operator@deepvision.internal',
      first_name: 'SOC',
      last_name: 'Operator',
      role: 'operator',
      is_staff: false,
    };
    try {
      localStorage.setItem('deepvision_demo_session', 'true');
    } catch (e) {
      // ignore
    }
    setUser(demoUser);
    return demoUser;
  };

  const logout = async () => {
    try {
      localStorage.removeItem('deepvision_demo_session');
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
        loginAsDemo,
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
