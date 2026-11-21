import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../hooks/useAuth.js';
import { useEventStream } from '../../useEventStream.js';
import {
  fetchCustomerTickets,
  fetchCustomerTicket,
  fetchCustomerMessages,
  postCustomerMessage,
} from '../../api.js';
import { Button, Badge, StatusPill, EmptyState } from '../common/index.js';
import { CustomerNewTicketModal } from './CustomerNewTicketModal.jsx';

export function CustomerPortal() {
  const { user, token, logout } = useAuth();
  const [tickets, setTickets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [replyText, setReplyText] = useState('');
  const [loadingTickets, setLoadingTickets] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [submittingReply, setSubmittingReply] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [liveConnected, setLiveConnected] = useState(false);

  // Load customer tickets
  const loadTickets = useCallback(async () => {
    try {
      const data = await fetchCustomerTickets();
      setTickets(data);
      if (data.length > 0 && !selectedId) {
        setSelectedId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load tickets:', err);
    } finally {
      setLoadingTickets(false);
    }
  }, [selectedId]);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  // Load selected ticket details and messages
  useEffect(() => {
    if (!selectedId) {
      setSelectedTicket(null);
      setMessages([]);
      return;
    }

    fetchCustomerTicket(selectedId)
      .then(setSelectedTicket)
      .catch(() => setSelectedTicket(null));

    setLoadingMessages(true);
    fetchCustomerMessages(selectedId)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setLoadingMessages(false));
  }, [selectedId]);

  // Real-time SSE updates
  const handleEvent = useCallback(
    (type, data) => {
      if (type === 'CONNECTED') {
        setLiveConnected(true);
        return;
      }
      if (type === 'DISCONNECTED') {
        setLiveConnected(false);
        return;
      }
      // When agent replies, status changes, or ticket resolved
      loadTickets();
      if (selectedId && data.ticket_id === selectedId) {
        fetchCustomerTicket(selectedId).then(setSelectedTicket).catch(console.error);
        fetchCustomerMessages(selectedId).then(setMessages).catch(console.error);
      }
    },
    [loadTickets, selectedId]
  );

  useEventStream(handleEvent, token);

  // Send real customer reply
  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || !selectedId) return;

    setSubmittingReply(true);
    try {
      await postCustomerMessage(selectedId, replyText.trim());
      setReplyText('');
      // Reload ticket and conversation
      const [updatedTicket, updatedMsgs] = await Promise.all([
        fetchCustomerTicket(selectedId),
        fetchCustomerMessages(selectedId),
      ]);
      setSelectedTicket(updatedTicket);
      setMessages(updatedMsgs);
      loadTickets();
    } catch (err) {
      alert(err.message || 'Failed to submit response');
    } finally {
      setSubmittingReply(false);
    }
  };

  // Filtered tickets
  const filteredTickets = tickets.filter((t) => {
    if (statusFilter === 'waiting') return t.status === 'waiting_on_customer';
    if (statusFilter === 'active') return ['open', 'in_progress'].includes(t.status);
    if (statusFilter === 'resolved') return ['done', 'closed'].includes(t.status);
    return true;
  });

  return (
    <div className="customer-portal-shell">
      {/* Top Portal Header */}
      <header className="customer-portal-header">
        <div className="portal-header-left">
          <div className="portal-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <h1 className="portal-title">Frontdesk Customer Portal</h1>
            <span className="portal-subtitle">{user?.company || 'Corporate Client Workspace'}</span>
          </div>
        </div>

        <div className="portal-header-right">
          <div className="portal-live-badge">
            <span className={`portal-live-dot ${liveConnected ? 'connected' : ''}`} />
            <span>{liveConnected ? 'Live Connection Active' : 'Connecting…'}</span>
          </div>

          <div className="customer-user-chip">
            <div className="customer-avatar">{user?.name ? user.name.charAt(0) : 'C'}</div>
            <div className="customer-user-meta">
              <span className="customer-user-name">{user?.name || 'Customer'}</span>
              <span className="customer-user-email">{user?.email}</span>
            </div>
          </div>

          <Button variant="ghost" size="sm" onClick={logout}>
            Sign Out
          </Button>
        </div>
      </header>

      {/* Main Portal Workspace */}
      <div className="customer-portal-body">
        {/* Left Sidebar: Tickets List */}
        <aside className="customer-portal-sidebar">
          <div className="sidebar-action-header">
            <div>
              <h2 className="sidebar-heading">My Support Requests</h2>
              <span className="sidebar-count">{tickets.length} total tickets</span>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowCreateModal(true)}
            >
              + New Ticket
            </Button>
          </div>

          {/* Filter Pills */}
          <div className="portal-filter-bar">
            <button
              type="button"
              className={`portal-filter-pill ${statusFilter === 'all' ? 'active' : ''}`}
              onClick={() => setStatusFilter('all')}
            >
              All ({tickets.length})
            </button>
            <button
              type="button"
              className={`portal-filter-pill ${statusFilter === 'waiting' ? 'active' : ''}`}
              onClick={() => setStatusFilter('waiting')}
            >
              Action Required ({tickets.filter((t) => t.status === 'waiting_on_customer').length})
            </button>
            <button
              type="button"
              className={`portal-filter-pill ${statusFilter === 'active' ? 'active' : ''}`}
              onClick={() => setStatusFilter('active')}
            >
              In Progress ({tickets.filter((t) => ['open', 'in_progress'].includes(t.status)).length})
            </button>
            <button
              type="button"
              className={`portal-filter-pill ${statusFilter === 'resolved' ? 'active' : ''}`}
              onClick={() => setStatusFilter('resolved')}
            >
              Resolved ({tickets.filter((t) => ['done', 'closed'].includes(t.status)).length})
            </button>
          </div>

          {/* Ticket Card Feed */}
          <div className="portal-ticket-feed">
            {loadingTickets && <div className="portal-loading">Loading your tickets…</div>}
            {!loadingTickets && filteredTickets.length === 0 && (
              <div className="portal-empty-list">No tickets found in this category.</div>
            )}
            {filteredTickets.map((t) => {
              const isSelected = t.id === selectedId;
              const isActionRequired = t.status === 'waiting_on_customer';
              return (
                <div
                  key={t.id}
                  className={`portal-ticket-card ${isSelected ? 'selected' : ''} ${
                    isActionRequired ? 'action-required' : ''
                  }`}
                  onClick={() => setSelectedId(t.id)}
                >
                  <div className="portal-card-top">
                    <span className="portal-card-id">{t.id}</span>
                    <Badge variant={t.priority} />
                  </div>

                  <h3 className="portal-card-title">{t.title}</h3>

                  <div className="portal-card-bottom">
                    <StatusPill status={t.status} />
                    <span className="portal-card-date">
                      {new Date(t.created_at).toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  </div>

                  {isActionRequired && (
                    <div className="portal-action-callout">
                      ⚡ <strong>Reply requested:</strong> The support team is waiting for your response.
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        {/* Right Pane: Selected Ticket Conversation & Resolution */}
        <main className="customer-portal-main">
          {!selectedTicket ? (
            <div className="portal-empty-main">
              <EmptyState
                title="Select a Support Request"
                description="Pick a ticket from the left panel to review updates, replies, and communicate with the support team."
              />
            </div>
          ) : (
            <div className="customer-ticket-workspace">
              {/* Ticket Meta Header */}
              <div className="ticket-hero-header">
                <div>
                  <div className="ticket-hero-id">
                    <span>{selectedTicket.id}</span>
                    <Badge variant={selectedTicket.priority} />
                    <StatusPill status={selectedTicket.status} />
                  </div>
                  <h2 className="ticket-hero-title">{selectedTicket.title}</h2>
                  <div className="ticket-hero-meta">
                    <span>
                      Created: {new Date(selectedTicket.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                    </span>
                    {selectedTicket.assigned_agent_name && (
                      <span> • Assigned Support Specialist: <strong>{selectedTicket.assigned_agent_name}</strong></span>
                    )}
                  </div>
                </div>
              </div>

              {/* Action Alert Banner when Waiting on Customer */}
              {selectedTicket.status === 'waiting_on_customer' && (
                <div className="customer-waiting-banner">
                  <div className="waiting-banner-icon">📩</div>
                  <div>
                    <h4 className="waiting-banner-title">Response Needed from You</h4>
                    <p className="waiting-banner-desc">
                      The support specialist has replied and is waiting for your input. Replying below will automatically resume work on this issue.
                    </p>
                  </div>
                </div>
              )}

              {/* Description Section */}
              <div className="ticket-detail-block">
                <h4 className="detail-block-title">Initial Issue Details</h4>
                <div className="detail-block-content">
                  {selectedTicket.description || 'No description provided.'}
                </div>
              </div>

              {/* Conversation Feed */}
              <div className="customer-conversation-container">
                <h4 className="conversation-section-title">
                  Messages & Updates ({messages.length})
                </h4>

                <div className="customer-messages-list">
                  {loadingMessages && <div className="messages-loading">Loading conversation…</div>}
                  {!loadingMessages && messages.length === 0 && (
                    <div className="messages-empty">No updates posted yet.</div>
                  )}
                  {messages.map((m) => {
                    const isMe = m.sender_type === 'customer';
                    return (
                      <div
                        key={m.id}
                        className={`customer-message-row ${isMe ? 'message-outbound' : 'message-inbound'}`}
                      >
                        <div className="customer-bubble">
                          <div className="customer-bubble-header">
                            <span className="customer-bubble-sender">
                              {isMe ? 'You (Customer)' : `Support: ${m.sender_name}`}
                            </span>
                            <span className="customer-bubble-time">
                              {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <div className="customer-bubble-text">{m.content}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Reply Composer */}
                <form onSubmit={handleSendReply} className="customer-reply-composer">
                  <textarea
                    rows={3}
                    required
                    className="customer-composer-input"
                    placeholder="Type your response to the support team..."
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    disabled={submittingReply}
                  />
                  <div className="customer-composer-actions">
                    <span className="composer-tip">
                      {selectedTicket.status === 'waiting_on_customer'
                        ? '⚡ Replying immediately resumes the ticket and unfreezes the SLA clock.'
                        : 'Your reply is immediately visible to the assigned support team.'}
                    </span>
                    <Button type="submit" variant="primary" loading={submittingReply}>
                      Send Response
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* New Ticket Modal */}
      {showCreateModal && (
        <CustomerNewTicketModal
          onClose={() => setShowCreateModal(false)}
          onCreated={(newTicket) => {
            loadTickets();
            setSelectedId(newTicket.id);
          }}
        />
      )}
    </div>
  );
}
