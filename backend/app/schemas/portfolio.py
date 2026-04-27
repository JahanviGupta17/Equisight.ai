"""
app/schemas/portfolio.py
Pydantic v2 schemas for Portfolio create/read.
"""
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PortfolioCreate(BaseModel):
    """Request body for POST /api/v1/portfolio/create."""
    user_id: uuid.UUID = Field(
        ...,
        description="Owner of the portfolio. Use the test UUID in Phase 1.",
        examples=["00000000-0000-0000-0000-000000000001"],
    )
    name: str = Field(
        ..., min_length=1, max_length=255,
        examples=["My India Equity Portfolio"],
    )
    target_return: float = Field(
        default=0.10, ge=0.0, le=10.0,
        description="Annualised target return as a decimal (e.g. 0.12 = 12%).",
        examples=[0.12],
    )
    target_risk: float = Field(
        default=0.15, ge=0.0, le=10.0,
        description="Annualised target volatility as a decimal (e.g. 0.15 = 15%).",
        examples=[0.15],
    )


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    target_return: float
    target_risk: float
    target_weights: dict | None = None
