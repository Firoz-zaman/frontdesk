import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { loginAgent, logoutAgent, getMe } from '../api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('frontdesk_token'));
  const [isLoading, setIsLoading] = useState(true);

  // Restore authenticated session on initial mount
  useEffect(() => {
    let mounted = true;
    const storedToken = localStorage.getItem('frontdesk_token');

    if (storedToken) {
      getMe()
        .then((profile) => {
          if (mounted) {
            if (profile) {
              const activeUser = profile.user_type === 'customer' ? profile.customer : (profile.agent || profile);
              setUser(activeUser);
              setToken(storedToken);
            } else {
              logoutAgent();
              setUser(null);
              setToken(null);
            }
          }
        })
        .catch(() => {
          if (mounted) {
            logoutAgent();
            setUser(null);
            setToken(null);
          }
        })
        .finally(() => {
          if (mounted) setIsLoading(false);
        });
    } else {
      setIsLoading(false);
    }

    return () => {
      mounted = false;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await loginAgent(email, password);
    const activeUser = data.user_type === 'customer' ? data.customer : data.agent;
    setUser(activeUser);
    setToken(data.access_token);
    return activeUser;
  }, []);

  const loginAs = useCallback(async (email) => {
    return login(email, 'arvo2026!');
  }, [login]);

  const logout = useCallback(() => {
    logoutAgent();
    setUser(null);
    setToken(null);
  }, []);

  const value = {
    user,
    token,
    isAuthenticated: Boolean(user && token),
    isLoading,
    login,
    loginAs,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
