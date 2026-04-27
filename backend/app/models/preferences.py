"""
app/models/preferences.py
SystemPreferences — stores per-user dynamic config in a JSONB column.
Expected JSONB shape (validated at schema layer):
  {
    "risk_tolerance": "medium",
    "alert_thresholds": {"drift_pct": 5.0},
    "rebalance_frequency": "monthly"
  }
"""
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SystemPreferences(Base):
    __tablename__ = "system_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # JSONB — can be queried/indexed natively in PostgreSQL
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="preferences")  # noqa: F821
