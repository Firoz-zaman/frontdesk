import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../hooks/useAuth.js';
import {
  fetchMessages,
  postMessage,
  fetchAuditLogs,
  updatePriority,
  resolveTicket,
  reopenTicket,
} from '../../api.js';
import { Badge, Button, EmptyState } from '../common/index.js';
import { SlaPanel } from './SlaPanel.jsx';

export function TicketDetail({
  ticket,
  onClaim,
  claiming,
  onTicketUpdated,
}) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [activeTab, setActiveTab] = useState('conversation');
  const [msgMode, setMsgMode] = useState('public');
  const [msgContent, setMsgContent] = useState('');
  const [sendingMsg, setSendingMsg] = useState(false);
  const [updatingPriority, setUpdatingPriority] = useState(false);
  const [resolvingTicket, setResolvingTicket] = useState(false);
  const [reopeningTicket, setReopeningTicket] = useState(false);
  const [simulatingCustomer, setSimulatingCustomer] = useState(false);

  // Load ticket messages
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

  // RBAC ownership calculation
  const isAssigned = Boolean(ticket?.assigned_agent_id);
  const isOwnerOrLead =
    !isAssigned ||
    ticket?.assigned_agent_id === user?.id ||
    user?.role === 'lead' ||
    user?.role === 'admin';

  // Handle priority escalation
  const handlePriorityChange = async (newPriority) => {
    if (!user) return;
    if (newPriority === ticket.priority) return;
    setUpdatingPriority(true);
    try {
      const updated = await updatePriority(ticket.id, newPriority, user.id);
      if (onTicketUpdated) onTicketUpdated(updated);
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to update priority');
    } finally {
      setUpdatingPriority(false);
    }
  };

  // Handle ticket resolution
  const handleResolve = async () => {
    if (!user) return;
    if (!window.confirm(`Mark ${ticket.id} as resolved?`)) return;
    setResolvingTicket(true);
    try {
      const updated = await resolveTicket(ticket.id, user.id);
      if (onTicketUpdated) onTicketUpdated(updated);
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to resolve ticket');
    } finally {
      setResolvingTicket(false);
    }
  };

  // Handle ticket reopening
  const handleReopen = async () => {
    if (!user) return;
    const reason = window.prompt('Reason for reopening ticket (optional):', '') || '';
    setReopeningTicket(true);
    try {
      const updated = await reopenTicket(ticket.id, user.id, reason);
      if (onTicketUpdated) onTicketUpdated(updated);
      loadAudit();
      loadMessages();
    } catch (err) {
      alert(err.message || 'Failed to reopen ticket');
    } finally {
      setReopeningTicket(false);
    }
  };

  // Handle send message / private note
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!msgContent.trim() || !ticket || !user) return;

    setSendingMsg(true);
    try {
      await postMessage(ticket.id, {
        content: msgContent.trim(),
        is_private: msgMode === 'private',
        sender_type: 'agent',
        sender_id: user.id,
        sender_name: user.name,
      });
      setMsgContent('');
      if (onTicketUpdated) onTicketUpdated();
      loadMessages();
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to send message');
    } finally {
      setSendingMsg(false);
    }
  };

  // Simulate incoming customer response (unfreezes SLA & resumes status to in_progress)
  const handleSimulateCustomerReply = async (customText = null) => {
    if (!ticket) return;
    setSimulatingCustomer(true);
    try {
      const defaultReplies = [
        `Thank you for following up! I checked the configuration and the issue is resolved on our end.`,
        `Here are the additional error screenshots and logs requested. Please let us know the next steps.`,
        `Confirmed, the fix you provided worked perfectly. Thanks for the quick turnaround!`,
      ];
      const content = customText || defaultReplies[Math.floor(Math.random() * defaultReplies.length)];

      await postMessage(ticket.id, {
        content,
        is_private: false,
        sender_type: 'customer',
        sender_id: `cust_${ticket.id.toLowerCase()}`,
        sender_name: ticket.customer_name || 'Customer',
      });

      if (onTicketUpdated) onTicketUpdated();
      loadMessages();
      loadAudit();
    } catch (err) {
      alert(err.message || 'Failed to simulate customer reply');
    } finally {
      setSimulatingCustomer(false);
    }
  };

  if (!ticket) {
    return (
      <div className="ticket-detail">
        <EmptyState
          title="No ticket selected"
          description="Select a ticket from the queue on the left to inspect details, SLAs, and message feeds."
        />
      </div>
    );
  }

  return (
    <div className="ticket-detail">
      {/* Header */}
      <div className="detail-header">
        <h2>{ticket.id}: {ticket.title}</h2>
        <div className="detail-meta">
          <Badge type="priority" value={ticket.priority} />
          <Badge type="status" value={ticket.status} />
          {ticket.assigned_agent_name ? (
            <span>👤 Assigned to: <strong>{ticket.assigned_agent_name}</strong></span>
          ) : (
            <span style={{ color: '#ef4444', fontWeight: 600 }}>⚠ Unassigned</span>
          )}
          <span>📅 {new Date(ticket.created_at).toLocaleString()}</span>
        </div>
      </div>

      {/* Ownership RBAC Warning Banner */}
      {isAssigned && !isOwnerOrLead && (
        <div className="ownership-warning">
          🔒 Assigned to <strong>{ticket.assigned_agent_name}</strong>. Only the assigned agent or a team lead can change priority, resolve, or reply.
        </div>
      )}

      {/* SLA Panel */}
      <SlaPanel ticket={ticket} />

      {/* Priority Escalation & Resolve Action Bar */}
      {ticket.status !== 'done' && ticket.status !== 'closed' && (
        <div className="sla-action-bar">
          <div className="sla-action-left">
            <label className="sla-action-label">Priority:</label>
            <select
              value={ticket.priority}
              onChange={(e) => handlePriorityChange(e.target.value)}
              disabled={updatingPriority || !isOwnerOrLead}
              className="priority-select"
              title={!isOwnerOrLead ? 'Only assigned agent or lead can change priority' : ''}
            >
              <option value="urgent">🔴 Urgent</option>
              <option value="medium">🟡 Medium</option>
              <option value="small">🟢 Small</option>
            </select>
            {updatingPriority && <span className="sla-action-hint">Updating…</span>}
          </div>
          <Button
            variant="success"
            size="sm"
            onClick={handleResolve}
            loading={resolvingTicket}
            disabled={!ticket.assigned_agent_id || !isOwnerOrLead}
            title={!isOwnerOrLead ? 'Only assigned agent or lead can resolve this ticket' : ''}
          >
            ✅ Mark as Resolved
          </Button>
        </div>
      )}

      {/* Resolved Banner */}
      {ticket.status === 'done' && (
        <div className="resolved-banner">
          <div>
            ✅ <strong>Ticket Resolved</strong>
            {ticket.resolved_at && <span> on {new Date(ticket.resolved_at).toLocaleString()}</span>}
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleReopen}
            loading={reopeningTicket}
            disabled={!isOwnerOrLead}
          >
            🔄 Reopen Ticket
          </Button>
        </div>
      )}

      {/* Closed Banner */}
      {ticket.status === 'closed' && (
        <div className="closed-banner">
          <div>
            🔒 <strong>Ticket Closed</strong>
            {ticket.closed_at && <span> on {new Date(ticket.closed_at).toLocaleString()}</span>}
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleReopen}
            loading={reopeningTicket}
            disabled={!isOwnerOrLead}
          >
            🔄 Reopen Ticket
          </Button>
        </div>
      )}

      {/* Claim Banner (if unassigned) */}
      {ticket.assigned_agent_id === null && (
        <div className="claim-banner">
          <span>This ticket is currently unassigned.</span>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onClaim(ticket.id)}
            loading={claiming}
          >
            Claim Ticket
          </Button>
        </div>
      )}

      {/* Description */}
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

      {/* Navigation Tabs */}
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

      {/* Tab 1: Conversation & Dual-Mode Messaging */}
      {activeTab === 'conversation' && (
        <div className="detail-section conversation-section">
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
                  <span className="message-time">
                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <div className="message-content">{m.content}</div>
              </div>
            ))}
          </div>

          {/* Customer Simulator Banner: Visible when ticket is waiting on customer */}
          {ticket.status === 'waiting_on_customer' && (
            <div className="v3-customer-simulator-banner">
              <div className="simulator-banner-content">
                <div className="simulator-banner-icon">⏳</div>
                <div>
                  <div className="simulator-banner-title">
                    Ticket is <strong>Waiting on Customer</strong> (SLA Timer Paused)
                  </div>
                  <div className="simulator-banner-desc">
                    In production, this resumes when <strong>{ticket.customer_name}</strong> responds via email webhook or magic link portal.
                  </div>
                </div>
              </div>
              <button
                type="button"
                className="simulator-action-btn"
                onClick={() => handleSimulateCustomerReply()}
                disabled={simulatingCustomer}
                title="Simulate incoming customer message to unfreeze SLA and resume ticket"
              >
                {simulatingCustomer ? 'Simulating…' : `⚡ Simulate ${ticket.customer_name} Reply`}
              </button>
            </div>
          )}

          {/* Dual-Mode Composer */}
          <div className="composer-container">
            <div className="composer-mode-bar">
              <button
                type="button"
                className={`composer-mode-btn ${msgMode === 'public' ? 'mode-public-active' : ''}`}
                onClick={() => setMsgMode('public')}
                disabled={!isOwnerOrLead}
                title={!isOwnerOrLead ? 'Only assigned agent or lead can send public replies' : ''}
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

            <form
              onSubmit={handleSendMessage}
              className={`composer-form ${msgMode === 'private' ? 'form-private-theme' : 'form-public-theme'}`}
            >
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
                <Button
                  type="submit"
                  variant={msgMode === 'private' ? 'secondary' : 'primary'}
                  loading={sendingMsg}
                >
                  {msgMode === 'private' ? '🔒 Add Internal Note' : '💬 Send Public Reply'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tab 2: Immutable Audit Trail */}
      {activeTab === 'audit' && (
        <div className="detail-section audit-section">
          <div style={{ marginBottom: '14px', fontSize: '0.85rem', color: '#6b7280' }}>
            Chronological append-only event ledger for non-repudiation (INC-0318).
          </div>
          {loadingAudit && <div style={{ padding: '20px', textAlign: 'center', color: '#9ca3af' }}>Loading audit records…</div>}
          <div className="audit-timeline">
            {auditLogs.map((log) => (
              <div key={log.id} className="audit-entry">
                <div className="audit-entry-header">
                  <span className="audit-action-tag">{log.action}</span>
                  <span className="audit-time">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <div className="audit-entry-actor">
                  By: <strong>{log.actor_name}</strong> ({log.actor_type})
                </div>
                {log.details && (
                  <pre className="audit-details-json">
                    {JSON.stringify(log.details, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
