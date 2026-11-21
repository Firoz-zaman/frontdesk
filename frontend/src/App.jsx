import { useState, useEffect, useCallback } from 'react';
import { fetchAgents, fetchTickets, fetchTicket, createTicket, claimTicket, fetchMessages, postMessage, fetchAuditLogs, updatePriority, resolveTicket, reopenTicket, loginAgent, logoutAgent, getMe } from './api.js';
import { useEventStream } from './useEventStream.js';

const FILTERS = [
  { label: 'All', value: '' },
  { label: 'Open', value: 'open' },
  { label: 'In Progress', value: 'in_progress' },
  { label: 'Waiting', value: 'waiting_on_customer' },
  { label: 'Done', value: 'done' },
  { label: 'Closed', value: 'closed' },
];

function priorityClass(p) {
  return `badge badge-${p}`;
}

function statusClass(s) {
  return `badge-status status-${s}`;
}

function statusLabel(s) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// Module 4: SLA chip display helper (INC-0327)
function SlaChip({ slaStatus }) {
  if (!slaStatus) return null;
  return (
    <span className={`sla-chip ${slaStatus.badge_class || 'sla-chip-healthy'}`}>
      {slaStatus.label}
    </span>
  );
}

// ── Login Modal (v2 Auth) ──
function LoginModal({ onClose, onLoggedIn }) {
  const [form, setForm] = useState({ email: '', password: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const data = await loginAgent(form.email, form.password);
      onLoggedIn(data.agent);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal login-modal" onClick={e => e.stopPropagation()}>
        <h2>Agent Login</h2>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input
              required type="email" autoFocus
              value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
              placeholder="meera@arvo.in"
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              required type="password"
              value={form.password}
              onChange={e => setForm({ ...form, password: e.target.value })}
              placeholder="••••••••"
            />
          </div>
          <div className="form-actions">
            <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-submit" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Sign In'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Create Ticket Modal ──
function CreateTicketModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ title: '', description: '', customer_name: '', customer_email: '', priority: 'small' });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await createTicket(form);
      onCreated();
      onClose();
    } catch {
      alert('Failed to create ticket');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>New Ticket</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Title</label>
            <input required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="form-group">
            <label>Customer Name</label>
            <input required value={form.customer_name} onChange={e => setForm({ ...form, customer_name: e.target.value })} />
          </div>
          <div className="form-group">
            <label>Customer Email</label>
            <input required type="email" value={form.customer_email} onChange={e => setForm({ ...form, customer_email: e.target.value })} />
          </div>
          <div className="form-group">
            <label>Priority</label>
            <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>
              <option value="urgent">Urgent</option>
              <option value="medium">Medium</option>
              <option value="small">Small</option>
            </select>
          </div>
          <div className="form-actions">
            <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-submit" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create Ticket'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Ticket Card (Queue Item) ──
function TicketCard({ ticket, selected, onClick }) {
  return (
    <div className={`ticket-card${selected ? ' selected' : ''}`} onClick={onClick}>
      <div className="ticket-card-header">
        <span className="ticket-id">{ticket.id}</span>
        <span className={priorityClass(ticket.priority)}>{ticket.priority}</span>
      </div>
      <div className="ticket-card-title">{ticket.title}</div>
      <div className="ticket-card-meta">
        <span className={statusClass(ticket.status)}>{statusLabel(ticket.status)}</span>
        <span>• {ticket.customer_name}</span>
        {ticket.assigned_agent_name && <span>• 👤 {ticket.assigned_agent_name}</span>}
      </div>
      {ticket.sla_status && <SlaChip slaStatus={ticket.sla_status} />}
    </div>
  );
}

// ── Ticket Detail (Right Pane) ──
function TicketDetail({ ticket, onClaim, claiming, currentAgent, onTicketUpdated }) {
  const [messages, setMessages] = useState([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [msgMode, setMsgMode] = useState('public'); // 'public' | 'private'
  const [msgContent, setMsgContent] = useState('');
  const [sendingMsg, setSendingMsg] = useState(false);

  // Module 3: Audit Trail State (INC-0318)
  const [activeTab, setActiveTab] = useState('conversation'); // 'conversation' | 'audit'
  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  // Module 4: SLA actions state (INC-0327)
  const [resolvingTicket, setResolvingTicket] = useState(false);
  const [updatingPriority, setUpdatingPriority] = useState(false);

  // Module 5: Lifecycle Reopen state (REQ-SLA-05)
  const [reopeningTicket, setReopeningTicket] = useState(false);

  // Load ticket messages whenever active ticket changes
  const loadMessages = useCallback(() => {
    if (!ticket) return;
    setLoadingMessages(true);
    fetchMessages(ticket.id, 'agent')
      .then(setMessages)
      .catch(console.error)
      .finally(() => setLoadingMessages(false));
  }, [ticket?.id]);

  // Load audit logs
  const loadAudit = useCallback(() => {
    if (!ticket) return;
    setLoadingAudit(true);
    fetchAuditLogs(ticket.id)
      .then(setAuditLogs)
      .catch(console.error)
      .finally(() => setLoadingAudit(false));
  }, [ticket?.id]);

  useEffect(() => {
    loadMessages();
    loadAudit();
  }, [loadMessages, loadAudit]);

  // Module 4: Handle priority escalation (INC-0327)
  const handlePriorityChange = async (newPriority) => {
    if (!currentAgent) { alert('Select an agent profile first.'); return; }
    if (newPriority === ticket.priority) return;
    setUpdatingPriority(true);
    try {
      const updated = await updatePriority(ticket.id, newPriority, currentAgent.id);
      if (onTicketUpdated) onTicketUpdated(updated);
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to update priority');
    } finally {
      setUpdatingPriority(false);
    }
  };

  // Module 4: Handle ticket resolution (INC-0327)
  const handleResolve = async () => {
    if (!currentAgent) { alert('Select an agent profile first.'); return; }
    if (!window.confirm(`Mark ${ticket.id} as resolved?`)) return;
    setResolvingTicket(true);
    try {
      const updated = await resolveTicket(ticket.id, currentAgent.id);
      if (onTicketUpdated) onTicketUpdated(updated);
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to resolve ticket');
    } finally {
      setResolvingTicket(false);
    }
  };

  // Module 5: Handle ticket reopening (REQ-SLA-05)
  const handleReopen = async () => {
    if (!currentAgent) { alert('Select an agent profile first.'); return; }
    const reason = window.prompt('Reason for reopening ticket (optional):', '') || '';
    setReopeningTicket(true);
    try {
      const updated = await reopenTicket(ticket.id, currentAgent.id, reason);
      if (onTicketUpdated) onTicketUpdated(updated);
      loadAudit();
      loadMessages();
    } catch (err) {
      alert(err.message || 'Failed to reopen ticket');
    } finally {
      setReopeningTicket(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!msgContent.trim() || !ticket) return;
    if (!currentAgent) {
      alert('Please select an agent profile in the top bar before sending messages.');
      return;
    }

    setSendingMsg(true);
    try {
      await postMessage(ticket.id, {
        content: msgContent.trim(),
        is_private: msgMode === 'private',
        sender_type: 'agent',
        sender_id: currentAgent.id,
        sender_name: currentAgent.name,
      });
      if (onTicketUpdated) onTicketUpdated();
      loadMessages();
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to send message');
    } finally {
      setSendingMsg(false);
    }
  };

  if (!ticket) {
    return (
      <div className="ticket-detail">
        <div className="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p>Select a ticket to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ticket-detail">
      <div className="detail-header">
        <h2>{ticket.id}: {ticket.title}</h2>
        <div className="detail-meta">
          <span className={priorityClass(ticket.priority)}>{ticket.priority}</span>
          <span className={statusClass(ticket.status)}>{statusLabel(ticket.status)}</span>
          {ticket.assigned_agent_name
            ? <span>👤 Assigned to: <strong>{ticket.assigned_agent_name}</strong></span>
            : <span style={{ color: '#dc2626', fontWeight: 600 }}>⚠ Unassigned</span>
          }
          <span>📅 {new Date(ticket.created_at).toLocaleString()}</span>
        </div>
      </div>

      {/* Module 4: SLA Panel (INC-0327) */}
      {ticket.sla_status && (
        <div className="sla-panel">
          <div className="sla-panel-left">
            <span className="sla-panel-label">SLA Status</span>
            <SlaChip slaStatus={ticket.sla_status} />
            {ticket.sla_status.is_paused && (
              <span className="sla-paused-hint">⏸ Timer paused — waiting on customer</span>
            )}
          </div>
          <div className="sla-panel-right">
            {ticket.first_response_due_at && (
              <div className="sla-deadline-item">
                <span className="sla-deadline-label">First Response</span>
                <span className="sla-deadline-value">
                  {ticket.first_responded_at
                    ? <span className="sla-met">✓ {new Date(ticket.first_responded_at).toLocaleString()}</span>
                    : new Date(ticket.first_response_due_at).toLocaleString()
                  }
                </span>
              </div>
            )}
            {ticket.resolution_due_at && (
              <div className="sla-deadline-item">
                <span className="sla-deadline-label">Resolution Due</span>
                <span className="sla-deadline-value">
                  {ticket.resolved_at
                    ? <span className="sla-met">✓ {new Date(ticket.resolved_at).toLocaleString()}</span>
                    : new Date(ticket.resolution_due_at).toLocaleString()
                  }
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Module 4: Priority Escalation + Resolve Actions */}
      {ticket.status !== 'done' && ticket.status !== 'closed' && (
        <div className="sla-action-bar">
          <div className="sla-action-left">
            <label className="sla-action-label">Priority:</label>
            <select
              value={ticket.priority}
              onChange={e => handlePriorityChange(e.target.value)}
              disabled={updatingPriority || !currentAgent}
              className="priority-select"
            >
              <option value="urgent">🔴 Urgent</option>
              <option value="medium">🟡 Medium</option>
              <option value="small">🟢 Small</option>
            </select>
            {updatingPriority && <span className="sla-action-hint">Updating…</span>}
          </div>
          <button
            className="btn-resolve"
            onClick={handleResolve}
            disabled={resolvingTicket || !currentAgent || !ticket.assigned_agent_id}
          >
            {resolvingTicket ? 'Resolving…' : '✅ Mark as Resolved'}
          </button>
        </div>
      )}
      {ticket.status === 'done' && (
        <div className="resolved-banner">
          <div>
            ✅ <strong>Ticket Resolved</strong>
            {ticket.resolved_at && <span> on {new Date(ticket.resolved_at).toLocaleString()}</span>}
          </div>
          <button
            className="btn-reopen"
            onClick={handleReopen}
            disabled={reopeningTicket || !currentAgent}
          >
            {reopeningTicket ? 'Reopening…' : '🔄 Reopen Ticket'}
          </button>
        </div>
      )}
      {ticket.status === 'closed' && (
        <div className="closed-banner">
          <div>
            🔒 <strong>Ticket Closed</strong>
            {ticket.closed_at && <span> on {new Date(ticket.closed_at).toLocaleString()}</span>}
          </div>
          <button
            className="btn-reopen"
            onClick={handleReopen}
            disabled={reopeningTicket || !currentAgent}
          >
            {reopeningTicket ? 'Reopening…' : '🔄 Reopen Ticket'}
          </button>
        </div>
      )}

      {/* Module 1: Claim Action Banner (INC-0291) */}
      {!ticket.assigned_agent_id && (
        <div className="claim-banner">
          <div className="claim-banner-text">
            <strong>Ticket is unassigned</strong>
            <span>Claim this ticket to start working on it and respond to the customer.</span>
          </div>
          <button
            className="btn-claim"
            onClick={() => onClaim(ticket.id)}
            disabled={claiming || !currentAgent}
          >
            {claiming ? 'Claiming…' : `✋ Take this ticket${currentAgent ? ` as ${currentAgent.name}` : ''}`}
          </button>
        </div>
      )}

      {/* Ticket Description */}
      <div className="detail-section">
        <h3>Description</h3>
        <p>{ticket.description || 'No description provided.'}</p>
      </div>

      {/* Customer Information */}
      <div className="detail-section">
        <h3>Customer Information</h3>
        <div className="customer-info">
          <div className="info-item">
            <label>Name</label>
            <span>{ticket.customer_name}</span>
          </div>
          <div className="info-item">
            <label>Email</label>
            <span>{ticket.customer_email}</span>
          </div>
        </div>
      </div>

      {/* Navigation Tabs for Conversation vs Audit Trail */}
      <div className="workspace-tab-bar">
        <button
          type="button"
          className={`workspace-tab-btn ${activeTab === 'conversation' ? 'workspace-tab-active' : ''}`}
          onClick={() => setActiveTab('conversation')}
        >
          💬 Conversation & Notes ({messages.length})
        </button>
        <button
          type="button"
          className={`workspace-tab-btn ${activeTab === 'audit' ? 'workspace-tab-active' : ''}`}
          onClick={() => {
            setActiveTab('audit');
            loadAudit();
          }}
        >
          📋 Audit Trail ({auditLogs.length})
        </button>
      </div>

      {/* Tab 1: Module 2 Conversation & Dual-Mode Messaging */}
      {activeTab === 'conversation' && (
        <div className="detail-section conversation-section">
          {/* Message Timeline */}
          <div className="timeline-container">
            {loadingMessages && <div className="timeline-loading">Loading conversation…</div>}
            {!loadingMessages && messages.length === 0 && (
              <div className="timeline-empty">No replies or notes recorded yet.</div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                className={`message-card ${m.is_private ? 'message-card-private' : 'message-card-public'}`}
              >
                <div className="message-header">
                  <div className="message-sender">
                    <strong>{m.sender_name}</strong>
                    <span className="sender-type-tag">({m.sender_type})</span>
                    {m.is_private && (
                      <span className="private-note-badge">
                        🔒 PRIVATE TEAM NOTE — INTERNAL ONLY
                      </span>
                    )}
                  </div>
                  <span className="message-time">{new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div className="message-content">{m.content}</div>
              </div>
            ))}
          </div>

          {/* Dual-Mode Message Composer */}
          <div className="composer-container">
            <div className="composer-mode-bar">
              <button
                type="button"
                className={`composer-mode-btn ${msgMode === 'public' ? 'mode-public-active' : ''}`}
                onClick={() => setMsgMode('public')}
              >
                💬 Reply to Customer
              </button>
              <button
                type="button"
                className={`composer-mode-btn ${msgMode === 'private' ? 'mode-private-active' : ''}`}
                onClick={() => setMsgMode('private')}
              >
                🔒 Private Team Note (Internal)
              </button>
            </div>

            <form onSubmit={handleSendMessage} className={`composer-form ${msgMode === 'private' ? 'form-private-theme' : 'form-public-theme'}`}>
              {msgMode === 'private' && (
                <div className="composer-warning-banner">
                  🔒 <strong>Internal Team Note:</strong> This note will NEVER be visible to the customer on any screen or API response.
                </div>
              )}
              {msgMode === 'public' && (
                <div className="composer-info-banner">
                  💬 <strong>Customer Reply:</strong> This will be sent directly to <strong>{ticket.customer_name}</strong> and advances ticket status to <em>Waiting on Customer</em>.
                </div>
              )}
              <textarea
                required
                rows={3}
                placeholder={
                  msgMode === 'private'
                    ? 'Write an internal note for team members (visible only to agents)...'
                    : `Draft your response to ${ticket.customer_name}...`
                }
                value={msgContent}
                onChange={(e) => setMsgContent(e.target.value)}
              />
              <div className="composer-actions">
                <button
                  type="submit"
                  disabled={sendingMsg || !msgContent.trim()}
                  className={`btn-send ${msgMode === 'private' ? 'btn-send-private' : 'btn-send-public'}`}
                >
                  {sendingMsg
                    ? 'Saving…'
                    : msgMode === 'private'
                    ? '🔒 Save Internal Note'
                    : '💬 Send Customer Reply'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tab 2: Module 3 Immutable Audit Trail (INC-0318) */}
      {activeTab === 'audit' && (
        <div className="detail-section audit-section">
          <div className="audit-security-header">
            🔒 <strong>Tamper-Proof Audit Trail (INC-0318)</strong>
            <span>Append-only chronological log. Proves exactly what occurred, when it happened, and who executed each action.</span>
          </div>

          <div className="audit-timeline-container">
            {loadingAudit && <div className="timeline-loading">Loading audit records…</div>}
            {!loadingAudit && auditLogs.length === 0 && (
              <div className="timeline-empty">No audit events recorded for this ticket yet.</div>
            )}
            {auditLogs.map((log) => (
              <div key={log.id} className="audit-entry-card">
                <div className="audit-entry-top">
                  <div className="audit-actor-badge">
                    <span className={`actor-type-pill pill-${log.actor_type}`}>
                      {log.actor_type.toUpperCase()}
                    </span>
                    <strong>{log.actor_name}</strong>
                  </div>
                  <span className={`action-badge action-${log.action.toLowerCase()}`}>
                    {log.action}
                  </span>
                  <span className="audit-timestamp">
                    {new Date(log.created_at).toLocaleString([], {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
                {log.details && (
                  <div className="audit-details-box">
                    {Object.entries(log.details).map(([k, v]) => (
                      <span key={k} className="audit-detail-item">
                        <em>{k}:</em> {String(v)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main App ──
export default function App() {
  const [agents, setAgents] = useState([]);
  const [currentAgent, setCurrentAgent] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [filter, setFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [liveConnected, setLiveConnected] = useState(false);

  // Load agents once; also check for existing JWT session
  useEffect(() => {
    fetchAgents().then(data => {
      setAgents(data);
      // Default to Meera (the lead)
      const meera = data.find(a => a.role === 'lead') || data[0];
      if (meera) setCurrentAgent(meera);
    });
    // Restore session from stored JWT
    getMe().then(agent => {
      if (agent) setCurrentAgent(agent);
    });
  }, []);

  // Load tickets when filter changes
  const loadTickets = useCallback(() => {
    fetchTickets(filter).then(setTickets).catch(console.error);
  }, [filter]);

  useEffect(() => { loadTickets(); }, [loadTickets]);

  // Load selected ticket detail
  useEffect(() => {
    if (selectedId) {
      fetchTicket(selectedId).then(setSelectedTicket).catch(() => setSelectedTicket(null));
    } else {
      setSelectedTicket(null);
    }
  }, [selectedId]);

  // SSE real-time event handler (v2)
  const handleEvent = useCallback((eventType, data) => {
    if (eventType === 'CONNECTED') {
      setLiveConnected(true);
      return;
    }
    // Auto-refresh ticket list on relevant events
    if (['TICKET_CLAIMED', 'PUBLIC_REPLY_SENT', 'CUSTOMER_REPLY_RECEIVED', 'TICKET_RESOLVED'].includes(eventType)) {
      loadTickets();
      if (selectedId && data.ticket_id === selectedId) {
        fetchTicket(selectedId).then(setSelectedTicket).catch(console.error);
      }
    }
  }, [loadTickets, selectedId]);

  useEventStream(handleEvent);

  // Handle claiming ticket atomically (INC-0291)
  const handleClaim = async (ticketId) => {
    if (!currentAgent) {
      alert('Please select an agent profile in the top bar before claiming.');
      return;
    }
    setClaiming(true);
    try {
      const updated = await claimTicket(ticketId, currentAgent.id);
      setSelectedTicket(updated);
      loadTickets();
    } catch (err) {
      alert(err.message);
      // Immediately reload to show current assignee state
      fetchTicket(ticketId).then(setSelectedTicket).catch(console.error);
      loadTickets();
    } finally {
      setClaiming(false);
    }
  };

  const handleLogout = () => {
    logoutAgent();
    // Revert to default agent (dev mode)
    const meera = agents.find(a => a.role === 'lead') || agents[0];
    if (meera) setCurrentAgent(meera);
  };

  const isLoggedInWithJwt = !!localStorage.getItem('frontdesk_token');

  return (
    <>
      {/* Navbar */}
      <nav className="navbar">
        <h1>FRONTDESK</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* v2: Live connection status pill */}
          <span className={`connection-pill ${liveConnected ? 'live' : 'offline'}`}>
            {liveConnected ? '🟢 Live' : '⚪ Connecting…'}
          </span>

          {/* Agent switcher (dev mode fallback when not JWT-authenticated) */}
          {currentAgent && !isLoggedInWithJwt && (
            <select
              value={currentAgent.id}
              onChange={e => {
                const a = agents.find(a => a.id === e.target.value);
                setCurrentAgent(a);
              }}
            >
              {agents.map(a => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.role})
                </option>
              ))}
            </select>
          )}

          {/* v2: JWT auth controls */}
          {isLoggedInWithJwt ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.85rem', color: '#d1fae5' }}>
                {currentAgent?.name}
              </span>
              <button className="btn-logout" onClick={handleLogout}>Sign Out</button>
            </div>
          ) : (
            <button className="btn-login" onClick={() => setShowLogin(true)}>Sign In</button>
          )}
        </div>
      </nav>

      {/* Split Layout */}
      <div className="app-layout">
        {/* Left: Ticket Queue */}
        <div className="ticket-queue">
          <div className="queue-header">
            <h2>Tickets ({tickets.length})</h2>
            <button className="create-btn" onClick={() => setShowCreate(true)}>+ New</button>
          </div>
          <div className="queue-filters">
            {FILTERS.map(f => (
              <button
                key={f.value}
                className={`filter-btn${filter === f.value ? ' active' : ''}`}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="queue-list">
            {tickets.map(t => (
              <TicketCard
                key={t.id}
                ticket={t}
                selected={t.id === selectedId}
                onClick={() => setSelectedId(t.id)}
              />
            ))}
            {tickets.length === 0 && (
              <div style={{ padding: '24px', textAlign: 'center', color: '#9ca3af' }}>No tickets found</div>
            )}
          </div>
        </div>

        {/* Right: Ticket Detail */}
        <TicketDetail
          ticket={selectedTicket}
          onClaim={handleClaim}
          claiming={claiming}
          currentAgent={currentAgent}
          onTicketUpdated={() => {
            loadTickets();
            if (selectedId) fetchTicket(selectedId).then(setSelectedTicket);
          }}
        />
      </div>

      {/* Create Modal */}
      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={loadTickets}
        />
      )}

      {/* Login Modal (v2) */}
      {showLogin && (
        <LoginModal
          onClose={() => setShowLogin(false)}
          onLoggedIn={(agent) => setCurrentAgent(agent)}
        />
      )}
    </>
  );
}
