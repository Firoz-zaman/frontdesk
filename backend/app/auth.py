"""Authentication module — JWT (HMAC-SHA256) + Argon2id password hashing + customer magic links.

Design principles:
- REQUIRE_AUTH env var gates enforcement. When falsy (default), get_current_agent returns
  the lead agent unconditionally, preserving 100% backward compatibility with Stage 0-5 tests.
- Passwords hashed with Argon2id via argon2-cffi (no passlib dependency).
- Customer magic links are HMAC-SHA256(ticket_id + customer_email, SECRET_KEY) stored as hex.
- JWTs are signed with HMAC-SHA256, expire in 8 hours.
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db

# ── Configuration ──────────────────────────────────────────────────────────────

SECRET_KEY: str = os.getenv(
    "FRONTDESK_SECRET_KEY",
    "arvo-production-secret-key-change-in-prod-2026",
)
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

# Controls whether auth is enforced. Set REQUIRE_AUTH=true in production.
# Default: false — dev/test mode; get_current_agent returns lead agent without token.
REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# Argon2id hasher with OWASP-recommended parameters
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
)


# ── Password Helpers ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return an Argon2id hash of the given plain-text password."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored Argon2id hash. Never raises."""
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ── JWT Helpers ────────────────────────────────────────────────────────────────

def create_access_token(agent_id: str, agent_email: str, agent_role: str) -> str:
    """Create a signed JWT for an agent. Expires in TOKEN_EXPIRE_HOURS hours."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": agent_id,
        "email": agent_email,
        "role": agent_role,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException 401 on any failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")


# ── Customer Magic Link Helpers ────────────────────────────────────────────────

def generate_customer_token(ticket_id: str, customer_email: str) -> str:
    """Generate a deterministic HMAC-SHA256 hex token for customer ticket access."""
    message = f"{ticket_id}:{customer_email.lower().strip()}".encode()
    return hmac.new(SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def verify_customer_token(ticket_id: str, customer_email: str, token: str) -> bool:
    """Verify a customer magic link token using constant-time comparison."""
    expected = generate_customer_token(ticket_id, customer_email)
    return hmac.compare_digest(expected, token)


# ── FastAPI Dependency ─────────────────────────────────────────────────────────

def get_current_agent(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """FastAPI dependency that resolves the authenticated agent.

    - If a token is provided (via Authorization: Bearer <token> or query param ?token=...):
      validates signature, expiration, and agent status. Raises HTTP 401 if invalid.
    - If NO token is provided:
      - REQUIRE_AUTH=false (default dev/test): returns lead agent for backward compat.
      - REQUIRE_AUTH=true (production): raises HTTP 401.
    """
    # Lazy import to avoid circular dependency (models → database → auth)
    from .models import Agent

    raw_token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        payload = decode_token(raw_token)
        agent_id = payload.get("sub")
        agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
        if not agent:
            raise HTTPException(status_code=401, detail="Agent account not found or deactivated.")
        return agent

    if not REQUIRE_AUTH:
        # Dev/test mode: return lead agent unconditionally when no credentials provided
        lead = db.query(Agent).filter(Agent.role == "lead").first()
        if not lead:
            lead = db.query(Agent).first()
        return lead

    # Production mode: enforce JWT
    raise HTTPException(
        status_code=401,
        detail="Authorization header with Bearer token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
