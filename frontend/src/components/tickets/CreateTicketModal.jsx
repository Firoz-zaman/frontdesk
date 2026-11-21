import React, { useState } from 'react';
import { createTicket } from '../../api.js';
import { Modal, Input, Button } from '../common/index.js';

export function CreateTicketModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    customer_name: '',
    customer_email: '',
    priority: 'small',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await createTicket(form);
      onCreated();
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to create ticket');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Create Support Ticket"
      maxWidth="480px"
    >
      {error && <div className="v3-auth-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <Input
          label="Ticket Title"
          required
          autoFocus
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          placeholder="Brief description of the issue"
        />

        <Input
          label="Detailed Description"
          multiline
          rows={3}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Steps to reproduce, environment, error codes..."
        />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <Input
            label="Customer Name"
            required
            value={form.customer_name}
            onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
            placeholder="e.g. Rahul Sharma"
          />

          <Input
            label="Customer Email"
            type="email"
            required
            value={form.customer_email}
            onChange={(e) => setForm({ ...form, customer_email: e.target.value })}
            placeholder="rahul@acme.com"
          />
        </div>

        <div className="v3-form-group">
          <label className="v3-form-label">Initial Priority <span className="v3-required-mark">*</span></label>
          <select
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}
            className="v3-input"
          >
            <option value="urgent">🔴 Urgent (SLA: 4h Response / 24h Resolution)</option>
            <option value="medium">🟡 Medium (SLA: 8h Response / 48h Resolution)</option>
            <option value="small">🟢 Small (SLA: 16h Response / 72h Resolution)</option>
          </select>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={submitting}>
            Create Ticket
          </Button>
        </div>
      </form>
    </Modal>
  );
}
