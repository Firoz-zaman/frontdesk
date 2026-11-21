/**
 * useEventStream — React hook for Server-Sent Events (SSE) real-time push.
 *
 * Usage:
 *   useEventStream((eventType, data) => { ... });
 *
 * Connects to /api/events/stream with the stored JWT token (if present).
 * Reconnects automatically on disconnect (browser's native EventSource behaviour).
 * The hook cleans up the EventSource on component unmount.
 */
import { useEffect, useRef } from 'react';

export function useEventStream(onEvent) {
  const onEventRef = useRef(onEvent);
  // Always keep ref current so the closure inside useEffect doesn't stale
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    const token = localStorage.getItem('frontdesk_token');
    // Pass token as query param — EventSource does not support custom headers
    const url = token
      ? `/api/events/stream?token=${encodeURIComponent(token)}`
      : '/api/events/stream';

    const es = new EventSource(url);

    const handleEvent = (type) => (e) => {
      try {
        const data = JSON.parse(e.data);
        onEventRef.current(type, data);
      } catch {
        // Malformed event — ignore
      }
    };

    // Subscribe to all event types defined in the SSE spec
    const EVENT_TYPES = [
      'CONNECTED',
      'TICKET_CLAIMED',
      'PUBLIC_REPLY_SENT',
      'CUSTOMER_REPLY_RECEIVED',
      'TICKET_RESOLVED',
      'SLA_BREACH_WARNING',
    ];

    EVENT_TYPES.forEach((type) => es.addEventListener(type, handleEvent(type)));

    es.onerror = () => {
      // EventSource handles reconnection automatically; no action needed here
    };

    return () => {
      es.close();
    };
  }, []); // Run once on mount; ref keeps onEvent current
}
