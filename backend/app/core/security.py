"""Cryptographic security utilities — Argon2id password hashing, JWTs, and HMAC tokens."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import HTTPException

from .config import settings

# Argon2id hasher with OWASP-recommended parameters
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
)


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


def create_access_token(agent_id: str, agent_email: str, agent_role: str) -> str:
    """Create a signed JWT for an agent. Expires in settings.TOKEN_EXPIRE_HOURS."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": agent_id,
        "email": agent_email,
        "role": agent_role,
        "iat": now,
        "exp": now + timedelta(hours=settings.TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException 401 on any failure."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")


def generate_customer_token(ticket_id: str, customer_email: str) -> str:
    """Generate a deterministic HMAC-SHA256 hex token for customer ticket access."""
    message = f"{ticket_id}:{customer_email.lower().strip()}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def verify_customer_token(ticket_id: str, customer_email: str, token: str) -> bool:
    """Verify a customer magic link token using constant-time comparison."""
    expected = generate_customer_token(ticket_id, customer_email)
    return hmac.compare_digest(expected, token)
