import React, { useState } from 'react';
import { createCustomerTicket } from '../../api.js';
import { Modal, Button, Input } from '../common/index.js';

export function CustomerNewTicketModal({ onClose, onCreated }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('medium');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;

    setSubmitting(true);
    setError('');
    try {
      const newTicket = await createCustomerTicket({
        title: title.trim(),
        description: description.trim(),
        priority,
      });
      onCreated(newTicket);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to submit support ticket.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Submit New Support Ticket" size="md">
      <form onSubmit={handleSubmit} className="customer-new-ticket-form">
        {error && <div className="v3-auth-error" style={{ marginBottom: '14px' }}>{error}</div>}

        <Input
          label="Ticket Subject"
          placeholder="e.g. Unable to connect to VPN gateway"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          autoFocus
        />

        <div className="input-group" style={{ marginBottom: '16px' }}>
          <label className="input-label" htmlFor="ticket-priority">
            Issue Priority / Urgency
          </label>
          <select
            id="ticket-priority"
            className="input-field"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="small">Small — General inquiry / minor question (1-day response SLA)</option>
            <option value="medium">Medium — System degraded / intermittent failure (4.5-hr response SLA)</option>
            <option value="urgent">Urgent — Critical production down / blocking outage (2-hr response SLA)</option>
          </select>
        </div>

        <div className="input-group" style={{ marginBottom: '20px' }}>
          <label className="input-label" htmlFor="ticket-description">
            Detailed Description & Steps to Reproduce
          </label>
          <textarea
            id="ticket-description"
            className="input-field"
            rows={4}
            placeholder="Please include error messages, steps taken, or specific URLs..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="modal-actions" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={submitting}>
            Submit Ticket
          </Button>
        </div>
      </form>
    </Modal>
  );
}
