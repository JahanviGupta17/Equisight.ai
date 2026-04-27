"""
app/core/db.py
Async SQLAlchemy engine, session factory, shared Base, and startup helper.

Vector storage is handled by Qdrant (app/services/rag.py) — no pgvector
extension or market_intelligence table needed here.
"""
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """
    Create all SQLAlchemy-mapped tables that don't yet exist.
    Safe to call repeatedly — existing tables are left untouched.
    """
    # Import every model so Base.metadata knows about its table.
    from app.models import (  # noqa: F401
        user, preferences, portfolio, holding,
        drift_event, user_preferences, recommendation,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables verified / created.")


async def dispose_engine() -> None:
    await engine.dispose()
    logger.info("Database engine disposed.")
