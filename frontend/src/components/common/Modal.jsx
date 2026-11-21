import React, { useEffect } from 'react';

/**
 * Reusable Accessible Modal Component
 * Features backdrop-blur, Escape key dismiss, backdrop click dismiss, and scale-in animation.
 */
export function Modal({
  isOpen = false,
  onClose,
  title,
  children,
  maxWidth = '500px',
  footer = null,
  className = '',
}) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && onClose) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="v3-modal-overlay" onClick={onClose}>
      <div
        className={`v3-modal-card ${className}`}
        style={{ maxWidth }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        {/* Header */}
        <div className="v3-modal-header">
          {title && <h3 id="modal-title" className="v3-modal-title">{title}</h3>}
          {onClose && (
            <button
              type="button"
              className="v3-modal-close"
              onClick={onClose}
              aria-label="Close modal"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </div>

        {/* Body */}
        <div className="v3-modal-body">
          {children}
        </div>

        {/* Optional Footer */}
        {footer && (
          <div className="v3-modal-footer">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
