"""SSE (Server-Sent Events) broadcaster — in-memory pub/sub for real-time push.

Architecture:
- EventBroadcaster holds a set of asyncio.Queue instances (one per connected client).
- broadcast() fans out JSON-serialised events to all subscribers.
- event_generator() streams SSE-formatted lines to a single client, sending keepalive
  pings every 20 seconds to prevent proxy timeouts.
- No external dependencies (Redis, etc.); purely in-process.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import Request

# Max queue depth per subscriber; older events are dropped if the client is slow.
_MAX_QUEUE_SIZE = 100


class EventBroadcaster:
    """Fan-out broadcaster that pushes typed events to all connected SSE clients."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        """Register a new client queue and return it."""
        q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a client queue (called on disconnect / generator cleanup)."""
        self._subscribers.discard(queue)

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Push a typed event to every connected subscriber.

        Events that cannot be enqueued (full queue / no loop) are silently dropped
        so that a slow client never blocks the main request path.
        """
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead: set[asyncio.Queue] = set()
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop event for this slow subscriber; do not disconnect it
                pass
            except Exception:
                dead.add(q)
        for q in dead:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton — imported by main.py
broadcaster = EventBroadcaster()


# ── SSE Stream Generator ───────────────────────────────────────────────────────

async def event_generator(
    request: Request, queue: asyncio.Queue
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted chunks for a single connected client.

    Protocol:
      event: <EVENT_TYPE>\\ndata: <json>\\n\\n
      : keepalive\\n\\n   (sent every 20 s when idle)
    """
    try:
        # Send a connected confirmation event immediately
        yield _format_event("CONNECTED", {"message": "SSE stream established"})

        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                yield _format_event(payload["event"], payload["data"])
            except asyncio.TimeoutError:
                # Keepalive ping — prevents proxy / load-balancer from closing idle connections
                yield ": keepalive\n\n"
    finally:
        broadcaster.unsubscribe(queue)


def _format_event(event_type: str, data: dict) -> str:
    """Render a single SSE message block."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
