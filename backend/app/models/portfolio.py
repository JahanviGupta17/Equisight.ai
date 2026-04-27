"""
app/models/portfolio.py
Portfolio — a named collection of holdings belonging to a user,
with target return and risk parameters for optimization.
"""
import uuid

from sqlalchemy import Float, ForeignKey, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_return: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    target_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    target_weights: Mapped[dict] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="portfolios")  # noqa: F821
    holdings: Mapped[list["Holding"]] = relationship(  # noqa: F821
        "Holding", back_populates="portfolio", cascade="all, delete-orphan"
    )
