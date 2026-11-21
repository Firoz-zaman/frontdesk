"""Authentication module — Backward-compatible facade wrapping core/security and core/dependencies."""
from .core.config import settings
from .core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    generate_customer_token,
    verify_customer_token,
)
from .core.dependencies import (
    get_current_agent,
    get_effective_agent,
    verify_ticket_ownership,
)

# Export module constants
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
TOKEN_EXPIRE_HOURS = settings.TOKEN_EXPIRE_HOURS
REQUIRE_AUTH = settings.REQUIRE_AUTH

__all__ = [
    "SECRET_KEY",
    "ALGORITHM",
    "TOKEN_EXPIRE_HOURS",
    "REQUIRE_AUTH",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "generate_customer_token",
    "verify_customer_token",
    "get_current_agent",
    "get_effective_agent",
    "verify_ticket_ownership",
]
