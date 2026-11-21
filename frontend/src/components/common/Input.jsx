import React from 'react';

/**
 * Reusable Form Input & Textarea Component
 * Supports labels, validation error banners, helper text, and multiline mode.
 */
export function Input({
  label,
  error,
  helper,
  type = 'text',
  value,
  onChange,
  placeholder = '',
  required = false,
  multiline = false,
  rows = 4,
  autoFocus = false,
  disabled = false,
  className = '',
  ...props
}) {
  return (
    <div className={`v3-form-group ${error ? 'has-error' : ''} ${className}`}>
      {label && (
        <label className="v3-form-label">
          {label}
          {required && <span className="v3-required-mark">*</span>}
        </label>
      )}

      {multiline ? (
        <textarea
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          required={required}
          rows={rows}
          autoFocus={autoFocus}
          disabled={disabled}
          className="v3-textarea"
          {...props}
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          required={required}
          autoFocus={autoFocus}
          disabled={disabled}
          className="v3-input"
          {...props}
        />
      )}

      {error && <span className="v3-input-error">{error}</span>}
      {!error && helper && <span className="v3-input-helper">{helper}</span>}
    </div>
  );
}
