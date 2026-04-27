"""
app/models/drift_event.py
Stores portfolio drift alerts triggered by the Celery background worker.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

class DriftEvent(Base):
    __tablename__ = "drift_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), default="Open")
    # Store drift details, e.g. {"asset": "BEL.NS", "current_weight": 0.25, "target_weight": 0.15, "threshold": 0.05}
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")  # noqa: F821
