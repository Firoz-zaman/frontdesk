"""FastAPI application entrypoint — Frontdesk v3.

Modular, production-structured application assembling core settings,
lifespan database migrations, CORS middleware, and versioned API routers.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .core.config import settings
from .database import engine, Base
from .seed import seed_database
from .events import broadcaster
from .api.health import health_router
from .api.v1.router import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set the running event loop for thread-safe event publishing
    broadcaster.set_loop(asyncio.get_running_loop())

    # Create tables and execute idempotent migrations
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        ticket_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tickets)"))]
        if "closed_at" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN closed_at DATETIME"))
            conn.commit()
        if "customer_token_hash" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN customer_token_hash VARCHAR(64)"))
            conn.commit()

        agent_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(agents)"))]
        if "password_hash" not in agent_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"))
            conn.commit()
        if "is_active" not in agent_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            conn.commit()
        if "last_login_at" not in agent_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN last_login_at DATETIME"))
            conn.commit()

    seed_database()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(health_router, prefix="/api")
app.include_router(api_v1_router, prefix="/api")
