import React from 'react';

/**
 * Reusable Button Component
 * Supports variants: primary | secondary | danger | ghost | success
 * Supports sizes: sm | md | lg
 * Built-in loading spinner and icon support
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  icon = null,
  type = 'button',
  onClick,
  className = '',
  title = '',
  ...props
}) {
  const baseClasses = 'inline-flex items-center justify-center font-medium transition-all cursor-pointer select-none';
  
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      className={`v3-btn v3-btn-${variant} v3-btn-${size} ${loading ? 'v3-btn-loading' : ''} ${className}`}
      {...props}
    >
      {loading && (
        <svg className="v3-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="12" r="10" strokeWidth="3" stroke="currentColor" strokeDasharray="30 60" />
        </svg>
      )}
      {!loading && icon && <span className="v3-btn-icon">{icon}</span>}
      <span className="v3-btn-text">{children}</span>
    </button>
  );
}
