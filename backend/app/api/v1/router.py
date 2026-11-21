"""Aggregator for all v1 API route modules."""
from fastapi import APIRouter

from .auth import router as auth_router
from .agents import router as agents_router
from .tickets import router as tickets_router
from .messages import router as messages_router
from .audit import router as audit_router
from .events import router as events_router
from .customer import router as customer_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(tickets_router)
api_v1_router.include_router(messages_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(customer_router)
