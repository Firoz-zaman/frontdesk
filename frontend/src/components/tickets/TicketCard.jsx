import React from 'react';
import { Badge } from '../common/index.js';

export function TicketCard({ ticket, selected, onClick }) {
  const slaStatus = ticket.sla_status;

  return (
    <div className={`ticket-card ${selected ? 'selected' : ''}`} onClick={onClick}>
      <div className="ticket-card-header">
        <span className="ticket-id">{ticket.id}</span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <Badge type="priority" value={ticket.priority} />
          <Badge type="status" value={ticket.status} />
        </div>
      </div>

      <div className="ticket-card-title">{ticket.title}</div>
      <div className="ticket-card-customer">From: {ticket.customer_name}</div>

      <div className="ticket-card-footer">
        <span className="ticket-agent">
          {ticket.assigned_agent_name ? (
            <span>👤 {ticket.assigned_agent_name}</span>
          ) : (
            <span style={{ color: '#ef4444', fontWeight: 600 }}>⚠ Unassigned</span>
          )}
        </span>
        {slaStatus && (
          <span className={`sla-chip ${slaStatus.badge_class || 'sla-chip-healthy'}`}>
            {slaStatus.label}
          </span>
        )}
      </div>
    </div>
  );
}
