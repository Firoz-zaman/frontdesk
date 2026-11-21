import React from 'react';

/**
 * Reusable EmptyState Component
 * Displays friendly zero-state guidance when ticket queues or inspector panes are empty.
 */
export function EmptyState({
  icon = null,
  title = 'No items found',
  description = '',
  action = null,
  className = '',
}) {
  return (
    <div className={`v3-empty-state ${className}`}>
      <div className="v3-empty-icon">
        {icon || (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        )}
      </div>
      <h4 className="v3-empty-title">{title}</h4>
      {description && <p className="v3-empty-description">{description}</p>}
      {action && <div className="v3-empty-action">{action}</div>}
    </div>
  );
}
