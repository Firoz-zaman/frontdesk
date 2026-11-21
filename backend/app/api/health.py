"""Health check endpoint."""
from fastapi import APIRouter
from ..core.config import settings

health_router = APIRouter(tags=["Health"])


@health_router.get("/health")
def health():
    return {"status": "ok", "version": settings.VERSION}
