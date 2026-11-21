import { useState, useEffect, useCallback } from 'react';
import { fetchAgents, fetchTickets, fetchTicket, createTicket } from './api.js';

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
    </div>
  );
}

// ── Ticket Detail (Right Pane) ──
function TicketDetail({ ticket }) {
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
            : <span style={{ color: '#dc2626' }}>⚠ Unassigned</span>
          }
          <span>📅 {new Date(ticket.created_at).toLocaleString()}</span>
        </div>
      </div>

      <div className="detail-section">
        <h3>Description</h3>
        <p>{ticket.description || 'No description provided.'}</p>
      </div>

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

  // Load agents once
  useEffect(() => {
    fetchAgents().then(data => {
      setAgents(data);
      // Default to Meera (the lead)
      const meera = data.find(a => a.role === 'lead') || data[0];
      if (meera) setCurrentAgent(meera);
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

  return (
    <>
      {/* Navbar */}
      <nav className="navbar">
        <h1>FRONTDESK</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {currentAgent && (
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
        <TicketDetail ticket={selectedTicket} />
      </div>

      {/* Create Modal */}
      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={loadTickets}
        />
      )}
    </>
  );
}
