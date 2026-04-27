"""
app/core/config.py
Reads environment variables via Pydantic BaseSettings.
Supports two env files:
  .env          — local dev (services on localhost)
  .env.docker   — inside Docker containers (services by service name)
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/equisight"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    ALPHA_VANTAGE_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Qdrant vector store
    # Local dev: leave QDRANT_URL empty — client uses on-disk storage at QDRANT_PATH.
    # Qdrant Cloud / prod: set QDRANT_URL and QDRANT_API_KEY in .env.
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_PATH: str = os.path.join(os.path.dirname(__file__), "..", "..", "qdrant_data")

    # Single Gemini model used for all LLM calls (advisory, summarisation, extraction)
    GEMINI_MODEL: str = "gemini-3.1-flash-lite-preview"

    # Redis channel used for cross-process WebSocket fan-out
    WS_PUBSUB_CHANNEL: str = "equisight:ws:advisory"

    # Hardcoded test user UUID for Phase 1 (no auth middleware yet)
    TEST_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    SECRET_KEY: str = "equisight-dev-secret-change-in-prod"


settings = Settings()
