import React from 'react';

export function SlaPanel({ ticket }) {
  if (!ticket || !ticket.sla_status) return null;
  const { sla_status: slaStatus } = ticket;

  return (
    <div className="sla-panel">
      <div className="sla-panel-left">
        <span className="sla-panel-label">SLA Health</span>
        <span className={`sla-chip ${slaStatus.badge_class || 'sla-chip-healthy'}`}>
          {slaStatus.label}
        </span>
        {slaStatus.is_paused && (
          <span className="sla-paused-hint">⏸ Timer paused — waiting on customer</span>
        )}
      </div>

      <div className="sla-panel-right">
        {ticket.first_response_due_at && (
          <div className="sla-deadline-item">
            <span className="sla-deadline-label">First Response Due</span>
            <span className="sla-deadline-value">
              {ticket.first_responded_at ? (
                <span className="sla-met">✓ {new Date(ticket.first_responded_at).toLocaleString()}</span>
              ) : (
                new Date(ticket.first_response_due_at).toLocaleString()
              )}
            </span>
          </div>
        )}

        {ticket.resolution_due_at && (
          <div className="sla-deadline-item">
            <span className="sla-deadline-label">Resolution Due</span>
            <span className="sla-deadline-value">
              {ticket.resolved_at ? (
                <span className="sla-met">✓ {new Date(ticket.resolved_at).toLocaleString()}</span>
              ) : (
                new Date(ticket.resolution_due_at).toLocaleString()
              )}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
