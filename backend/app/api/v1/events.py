"""Server-Sent Events route endpoints — v1."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ...models import Agent
from ...events import broadcaster, event_generator
from ...core.dependencies import get_current_user

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/stream")
async def event_stream(
    request: Request,
    user_info = Depends(get_current_user),
):
    """Server-Sent Events endpoint. Streams real-time typed events to connected agents and customers."""
    queue = await broadcaster.subscribe()
    return StreamingResponse(
        event_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Connection": "keep-alive",
        },
    )
