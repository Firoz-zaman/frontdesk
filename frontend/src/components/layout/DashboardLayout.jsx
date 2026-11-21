import React, { useState, useEffect, useCallback } from 'react';
import { fetchTickets, fetchTicket, claimTicket } from '../../api.js';
import { useAuth } from '../../hooks/useAuth.js';
import { useEventStream } from '../../useEventStream.js';
import { Navbar } from './Navbar.jsx';
import { TicketQueue } from '../tickets/TicketQueue.jsx';
import { TicketDetail } from '../tickets/TicketDetail.jsx';
import { CreateTicketModal } from '../tickets/CreateTicketModal.jsx';

export function DashboardLayout() {
  const { user, token } = useAuth();
  const [tickets, setTickets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [filter, setFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [liveConnected, setLiveConnected] = useState(false);

  // Load ticket list
  const loadTickets = useCallback(() => {
    fetchTickets(filter)
      .then(setTickets)
      .catch(console.error);
  }, [filter]);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  // Load active ticket detail
  useEffect(() => {
    if (selectedId) {
      fetchTicket(selectedId)
        .then(setSelectedTicket)
        .catch(() => setSelectedTicket(null));
    } else {
      setSelectedTicket(null);
    }
  }, [selectedId]);

  // Real-Time SSE subscription
  const handleEvent = useCallback(
    (eventType, data) => {
      if (eventType === 'CONNECTED') {
        setLiveConnected(true);
        return;
      }
      if (
        [
          'TICKET_CLAIMED',
          'PUBLIC_REPLY_SENT',
          'CUSTOMER_REPLY_RECEIVED',
          'TICKET_RESOLVED',
          'TICKET_REOPENED',
          'TICKET_PRIORITY_CHANGED',
        ].includes(eventType)
      ) {
        loadTickets();
        if (selectedId && data.ticket_id === selectedId) {
          fetchTicket(selectedId).then(setSelectedTicket).catch(console.error);
        }
      }
    },
    [loadTickets, selectedId]
  );

  useEventStream(handleEvent, token);

  // Handle atomic claim
  const handleClaim = async (ticketId) => {
    if (!user) return;
    setClaiming(true);
    try {
      const updated = await claimTicket(ticketId, user.id);
      setSelectedTicket(updated);
      loadTickets();
    } catch (err) {
      alert(err.message || 'Failed to claim ticket');
      fetchTicket(ticketId).then(setSelectedTicket).catch(console.error);
      loadTickets();
    } finally {
      setClaiming(false);
    }
  };

  return (
    <div className="v3-app-shell">
      {/* Top Navbar */}
      <Navbar liveConnected={liveConnected} />

      {/* Main Split Layout */}
      <div className="app-layout">
        {/* Left Pane: Ticket Feed */}
        <TicketQueue
          tickets={tickets}
          selectedId={selectedId}
          onSelectTicket={setSelectedId}
          filter={filter}
          onFilterChange={setFilter}
          onOpenCreate={() => setShowCreate(true)}
        />

        {/* Right Pane: Inspector */}
        <TicketDetail
          ticket={selectedTicket}
          onClaim={handleClaim}
          claiming={claiming}
          onTicketUpdated={() => {
            loadTickets();
            if (selectedId) fetchTicket(selectedId).then(setSelectedTicket);
          }}
        />
      </div>

      {/* New Ticket Modal */}
      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={loadTickets}
        />
      )}
    </div>
  );
}
