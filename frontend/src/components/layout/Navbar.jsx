import React from 'react';
import { useAuth } from '../../hooks/useAuth.js';
import { StatusPill, Button, ThemeToggle } from '../common/index.js';

export function Navbar({ liveConnected = false }) {
  const { user, logout } = useAuth();

  return (
    <nav className="navbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div className="v3-nav-brand">
          <div className="v3-nav-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="18" height="18">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1>FRONTDESK</h1>
        </div>
        <StatusPill live={liveConnected} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <ThemeToggle />
        {user && (
          <div className="v3-nav-user">
            <div className="v3-nav-avatar">
              {user.name.charAt(0)}
            </div>
            <div className="v3-nav-user-info">
              <span className="v3-nav-user-name">{user.name}</span>
              <span className={`v3-nav-role-badge ${user.role}`}>
                {user.role === 'lead' ? 'Team Lead' : 'Agent'}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="v3-btn-signout"
              title="Sign out of workspace"
            >
              Sign Out
            </Button>
          </div>
        )}
      </div>
    </nav>
  );
}
