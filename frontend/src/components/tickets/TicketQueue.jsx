import React from 'react';
import { TicketCard } from './TicketCard.jsx';
import { Button, EmptyState } from '../common/index.js';

const FILTERS = [
  { label: 'All', value: '' },
  { label: 'Open', value: 'open' },
  { label: 'In Progress', value: 'in_progress' },
  { label: 'Waiting', value: 'waiting_on_customer' },
  { label: 'Done', value: 'done' },
  { label: 'Closed', value: 'closed' },
];

export function TicketQueue({
  tickets,
  selectedId,
  onSelectTicket,
  filter,
  onFilterChange,
  onOpenCreate,
}) {
  return (
    <div className="ticket-queue">
      <div className="queue-header">
        <h2>Tickets ({tickets.length})</h2>
        <Button variant="primary" size="sm" onClick={onOpenCreate}>
          + New Ticket
        </Button>
      </div>

      <div className="queue-filters">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            className={`filter-btn ${filter === f.value ? 'active' : ''}`}
            onClick={() => onFilterChange(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="queue-list">
        {tickets.map((t) => (
          <TicketCard
            key={t.id}
            ticket={t}
            selected={t.id === selectedId}
            onClick={() => onSelectTicket(t.id)}
          />
        ))}

        {tickets.length === 0 && (
          <EmptyState
            title="No tickets found"
            description="There are no tickets matching the selected status filter."
          />
        )}
      </div>
    </div>
  );
}
