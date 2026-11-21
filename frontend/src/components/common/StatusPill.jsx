import React from 'react';

/**
 * Reusable StatusPill Component
 * Displays real-time SSE stream health with pulsating beacon indicator.
 */
export function StatusPill({
  live = false,
  className = '',
}) {
  return (
    <div className={`v3-status-pill ${live ? 'live' : 'connecting'} ${className}`}>
      <span className="v3-status-dot" />
      <span className="v3-status-label">{live ? 'Live Stream' : 'Connecting…'}</span>
    </div>
  );
}
