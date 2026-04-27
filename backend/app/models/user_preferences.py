"""
app/models/user_preferences.py
UserPreferences — stores investor profile answers per portfolio.
Linked to portfolio_id so preferences are portfolio-scoped, not just user-scoped.

Fields:
  time_horizon
  drawdown_tolerance
  liquidity_needs
  experience_level
  diversification_preference
"""
import uuid
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one preferences row per portfolio
        index=True,
    )

    # ── Investor profile answers ─────────────────────────────────────────────
    time_horizon: Mapped[str] = mapped_column(
        String(32), nullable=False, default="4-7 Years"
    )
    drawdown_tolerance: Mapped[str] = mapped_column(
        String(128), nullable=False, default="Uncomfortable at 15% (Balanced)"
    )
    liquidity_needs: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Moderate"
    )
    experience_level: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Beginner (Do it for me)"
    )
    diversification_preference: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Standard"
    )