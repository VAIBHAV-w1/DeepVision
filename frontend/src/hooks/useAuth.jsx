import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = async () => {
    try {
      const res = await authService.me();
      if (res && res.authenticated && res.user) {
        setUser(res.user);
        return;
      }
    } catch (e) {
      // ignore
    }
    try {
      if (localStorage.getItem('deepvision_demo_session') === 'true') {
        setUser({
          id: 9999,
          username: 'soc_operator_demo',
          email: 'operator@deepvision.internal',
          first_name: 'SOC',
          last_name: 'Operator',
          role: 'operator',
          is_staff: false,
        });
      } else {
        setUser(null);
      }
    } catch (e) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();

    const handleUnauthorized = () => {
      setUser(null);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
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
