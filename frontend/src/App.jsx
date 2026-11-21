import React from 'react';
import { ThemeProvider } from './context/ThemeContext.jsx';
import { AuthProvider, useAuth } from './context/AuthContext.jsx';
import { LoginPage } from './components/auth/LoginPage.jsx';
import { DashboardLayout } from './components/layout/DashboardLayout.jsx';
import { CustomerPortal } from './components/customer/CustomerPortal.jsx';

function AppContent() {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="v3-loading-screen">
        <div className="v3-spinner" style={{ width: '32px', height: '32px', color: '#3b82f6' }} />
        <span style={{ fontSize: '0.9rem', color: '#64748b', fontWeight: 500 }}>
          Initializing Frontdesk workspace…
        </span>
      </div>
    );
  }

  // The very first thing the user sees is the login page if unauthenticated
  if (!isAuthenticated) {
    return <LoginPage />;
  }

  // If customer is authenticated, direct to Customer Portal
  if (user?.role === 'customer') {
    return <CustomerPortal />;
  }

  // Otherwise, direct to Support Agent Workspace
  return <DashboardLayout />;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  );
}
