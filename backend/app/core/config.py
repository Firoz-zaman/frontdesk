"""Core application configuration — Frontdesk v3."""
import os
from typing import List


class Settings:
    PROJECT_NAME: str = "Frontdesk"
    VERSION: str = "3.0.0"

    # Security & JWT
    SECRET_KEY: str = os.getenv(
        "FRONTDESK_SECRET_KEY",
        "arvo-production-secret-key-change-in-prod-2026",
    )
    ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_HOURS: int = 8
    REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:////home/local-admin/project-11/backend/frontdesk.db",
    )

    # CORS Configuration
    # Note: When allow_credentials=True, W3C CORS forbids wildcard "*".
    # Specific origins must be listed.
    _cors_env: str = os.getenv("FRONTDESK_CORS_ORIGINS", "")
    CORS_ORIGINS: List[str] = [
        origin.strip() for origin in _cors_env.split(",") if origin.strip()
    ] if _cors_env else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
