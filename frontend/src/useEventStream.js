/**
 * useEventStream — React hook for Server-Sent Events (SSE) real-time push.
 *
 * Usage:
 *   useEventStream(handleEvent, token);
 *
 * Features:
 *   - Re-establishes connection on token / identity change.
 *   - Graceful exponential backoff on disconnects (2s to 30s max).
 *   - Clean teardown on unmount or session invalidation.
 */
import { useEffect, useRef } from 'react';

export function useEventStream(onEvent, activeToken) {
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  // Use provided token or fallback to localStorage
  const currentToken = activeToken !== undefined ? activeToken : localStorage.getItem('frontdesk_token');

  useEffect(() => {
    let es = null;
    let retryTimeout = null;
    let retryDelay = 2000;
    let isCancelled = false;

    function connect() {
      if (isCancelled) return;
      const token = currentToken || localStorage.getItem('frontdesk_token');
      const url = token
        ? `/api/events/stream?token=${encodeURIComponent(token)}`
        : '/api/events/stream';

      try {
        es = new EventSource(url);
      } catch (err) {
        console.warn('Failed to initialize EventSource:', err);
        return;
      }

      const handleEvent = (type) => (e) => {
        try {
          const data = JSON.parse(e.data);
          onEventRef.current(type, data);
        } catch {
          // Malformed JSON event — ignore
        }
      };

      const EVENT_TYPES = [
        'CONNECTED',
        'TICKET_CLAIMED',
        'PUBLIC_REPLY_SENT',
        'CUSTOMER_REPLY_RECEIVED',
        'TICKET_RESOLVED',
        'SLA_BREACH_WARNING',
      ];

      EVENT_TYPES.forEach((type) => es.addEventListener(type, handleEvent(type)));

      es.onopen = () => {
        retryDelay = 2000; // Reset backoff on successful handshake
      };

      es.onerror = () => {
        if (es) {
          es.close();
        }
        if (!isCancelled) {
          retryTimeout = setTimeout(() => {
            connect();
          }, retryDelay);
          retryDelay = Math.min(retryDelay * 1.5, 30000);
        }
      };
    }

    connect();

    return () => {
      isCancelled = true;
      if (retryTimeout) clearTimeout(retryTimeout);
      if (es) es.close();
    };
  }, [currentToken]);
}
