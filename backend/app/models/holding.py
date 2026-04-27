"""
app/models/holding.py
Holding — an individual asset position within a portfolio.
asset_type uses a PostgreSQL CHECK constraint via Enum.
"""
import uuid

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

ASSET_TYPE_ENUM = SAEnum(
    "Stock", "ETF", "MutualFund",
    name="asset_type_enum",
    create_type=True,  # creates the PostgreSQL ENUM type on first run
)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Exact Yahoo Finance ticker — e.g. BEL.NS, NTPC.NS, 0P0000YWL1.BO
    # No auto-normalization. User MUST supply the correct suffix.
    asset_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_type: Mapped[str] = mapped_column(ASSET_TYPE_ENUM, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    average_buy_price: Mapped[float] = mapped_column(Float, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(  # noqa: F821
        "Portfolio", back_populates="holdings"
    )
