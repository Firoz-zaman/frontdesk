import React from 'react';

/**
 * Reusable Badge Component
 * Displays standardized priority chips and ticket status pills with dot markers.
 */
export function Badge({
  type = 'status', // 'status' | 'priority'
  value = '',
  children,
  className = '',
}) {
  const normalized = (value || '').toLowerCase().trim();

  // Status human-readable label
  const formatStatus = (s) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  if (type === 'priority') {
    return (
      <span className={`v3-badge v3-badge-priority v3-priority-${normalized} ${className}`}>
        <span className="v3-badge-dot" />
        {children || normalized}
      </span>
    );
  }

  return (
    <span className={`v3-badge v3-badge-status v3-status-${normalized} ${className}`}>
      {children || formatStatus(normalized)}
    </span>
  );
}
