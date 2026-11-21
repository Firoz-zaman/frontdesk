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

    # CORS
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
