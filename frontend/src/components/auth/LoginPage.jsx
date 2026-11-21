import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth.js';
import { Button, Input } from '../common/index.js';

const DEMO_CUSTOMERS = [
  {
    name: 'Rahul Sharma',
    email: 'customer@acmecorp.com',
    role: 'customer',
    desc: 'Acme Corporation (Customer Portal)',
  },
];

const DEMO_AGENTS = [
  {
    name: 'Meera',
    email: 'meera@arvo.in',
    role: 'lead',
    desc: 'Team Lead (Full supervisory override)',
  },
  {
    name: 'Ravi',
    email: 'ravi@arvo.in',
    role: 'agent',
    desc: 'Support Agent (Owns assigned tickets)',
  },
  {
    name: 'Priya',
    email: 'priya@arvo.in',
    role: 'agent',
    desc: 'Support Agent',
  },
  {
    name: 'Arjun',
    email: 'arjun@arvo.in',
    role: 'agent',
    desc: 'Support Agent (Tests 403 Forbidden)',
  },
  {
    name: 'Sneha',
    email: 'sneha@arvo.in',
    role: 'agent',
    desc: 'Support Agent',
  },
];

export function LoginPage() {
  const { login, loginAs } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) return;
    setSubmitting(true);
    setError('');
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message || 'Invalid email or password');
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickLogin = async (agentEmail) => {
    setSubmitting(true);
    setError('');
    try {
      await loginAs(agentEmail);
    } catch (err) {
      setError(err.message || 'Failed to sign in');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="v3-auth-page">
      {/* Left Column: Brand Hero & Platform Capabilities */}
      <div className="v3-auth-hero">
        <div className="v3-hero-brand">
          <div className="v3-hero-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="v3-hero-brand-name">FRONTDESK</span>
        </div>

        <div className="v3-hero-center">
          <div className="v3-hero-badge">
            <span>🛡 Enterprise Support Workspace</span>
          </div>
          <h1 className="v3-hero-title">
            Deterministic Ticketing & SLA Engine.
          </h1>
          <p className="v3-hero-description">
            High-integrity support operations designed for Indian business hours (09:30 - 18:30 IST),
            featuring atomic claim locking, strict note isolation, and real-time push streaming.
          </p>

          <div className="v3-hero-features">
            <div className="v3-feature-item">
              <div className="v3-feature-icon">⚡</div>
              <div>
                <div className="v3-feature-title">Real-Time Event Streaming</div>
                <div className="v3-feature-desc">Immediate SSE broadcasts for claims, replies, and status transitions.</div>
              </div>
            </div>
            <div className="v3-feature-item">
              <div className="v3-feature-icon">🔒</div>
              <div>
                <div className="v3-feature-title">Ticket Ownership RBAC</div>
                <div className="v3-feature-desc">Restricts modifications strictly to the assigned agent and team leads.</div>
              </div>
            </div>
            <div className="v3-feature-item">
              <div className="v3-feature-icon">📜</div>
              <div>
                <div className="v3-feature-title">Immutable Audit Sourcing</div>
                <div className="v3-feature-desc">Append-only chronological trail proving non-repudiation for every action.</div>
              </div>
            </div>
          </div>
        </div>

        <div className="v3-hero-footer">
          <span>Secured with Argon2id Password Hashing & HMAC-SHA256 JWTs</span>
        </div>
      </div>

      {/* Right Column: Sign-In Card & Quick Switcher */}
      <div className="v3-auth-content">
        <div className="v3-auth-card">
          <div className="v3-auth-header">
            <h2 className="v3-auth-title">Agent Workspace</h2>
            <p className="v3-auth-subtitle">Sign in to your account or pick a quick profile below</p>
          </div>

          {error && (
            <div className="v3-auth-error">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="v3-auth-form">
            <Input
              label="Agent Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. meera@arvo.in"
              required
              autoFocus
            />

            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={submitting}
              className="v3-auth-submit"
            >
              Sign In to Workspace
            </Button>
          </form>

          {/* 1-Click Customer Profile */}
          <div className="v3-demo-divider">
            <span>Customer Portal Access (1-Click)</span>
          </div>

          <div className="v3-demo-grid" style={{ marginBottom: '14px' }}>
            {DEMO_CUSTOMERS.map((cust) => (
              <button
                key={cust.email}
                type="button"
                className="v3-demo-chip"
                style={{ borderColor: '#bfdbfe', background: '#f8fafc' }}
                onClick={() => handleQuickLogin(cust.email)}
                disabled={submitting}
              >
                <div className="v3-demo-chip-left">
                  <div className="v3-demo-avatar" style={{ background: '#2563eb', color: '#fff' }}>
                    {cust.name.charAt(0)}
                  </div>
                  <div>
                    <div className="v3-demo-name" style={{ color: '#1e3a8a', fontWeight: 600 }}>
                      {cust.name}
                    </div>
                    <div className="v3-demo-email">{cust.desc}</div>
                  </div>
                </div>
                <span
                  className="v3-demo-role"
                  style={{ background: '#dbeafe', color: '#1e40af', fontWeight: 600 }}
                >
                  Customer
                </span>
              </button>
            ))}
          </div>

          {/* 1-Click Demo Agent Profiles */}
          <div className="v3-demo-divider">
            <span>Support Team Profiles (1-Click)</span>
          </div>

          <div className="v3-demo-grid">
            {DEMO_AGENTS.map((agent) => (
              <button
                key={agent.email}
                type="button"
                className="v3-demo-chip"
                onClick={() => handleQuickLogin(agent.email)}
                disabled={submitting}
              >
                <div className="v3-demo-chip-left">
                  <div className="v3-demo-avatar">
                    {agent.name.charAt(0)}
                  </div>
                  <div>
                    <div className="v3-demo-name">{agent.name}</div>
                    <div className="v3-demo-email">{agent.desc}</div>
                  </div>
                </div>
                <span className={`v3-demo-role ${agent.role}`}>
                  {agent.role === 'lead' ? 'Team Lead' : 'Agent'}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
