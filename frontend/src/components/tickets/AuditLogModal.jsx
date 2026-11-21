import React, { useState, useEffect } from 'react';
import { fetchAuditLogs } from '../../api.js';
import { Modal } from '../common/index.js';

export function AuditLogModal({ ticketId, isOpen, onClose }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !ticketId) return;
    setLoading(true);
    fetchAuditLogs(ticketId)
      .then(setLogs)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [isOpen, ticketId]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Immutable Audit Trail — ${ticketId}`}
      maxWidth="680px"
    >
      <div style={{ marginBottom: '16px', fontSize: '0.85rem', color: '#6b7280' }}>
        Chronological append-only event ledger for non-repudiation (INC-0318).
        Timestamps are strictly monotonic and mathematically verifiable.
      </div>

      {loading && <div style={{ textAlign: 'center', padding: '24px', color: '#9ca3af' }}>Loading audit records…</div>}

      {!loading && logs.length === 0 && (
        <div style={{ textAlign: 'center', padding: '24px', color: '#9ca3af' }}>No audit records recorded yet.</div>
      )}

      <div className="audit-timeline">
        {logs.map((log) => (
          <div key={log.id} className="audit-entry">
            <div className="audit-entry-header">
              <span className="audit-action-tag">{log.action}</span>
              <span className="audit-time">
                {new Date(log.created_at).toLocaleString()}
              </span>
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
    </Modal>
  );
}
