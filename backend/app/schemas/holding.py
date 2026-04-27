"""
app/schemas/holding.py
Pydantic v2 schemas for Holdings.

Ticker policy:
  The CSV parser auto-appends .NS for bare Indian symbols.
  This validator accepts any ticker matching [A-Z0-9^&.-]+ so it never
  rejects valid but unusual tickers (e.g. ^NSEI, BRK.A, 0P0000YWL1.BO).
"""
import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HoldingCSVRow(BaseModel):
    """Validates a single extracted holdings row."""
    asset_symbol: str = Field(..., description="Yahoo Finance ticker, e.g. BEL.NS")
    asset_type: str = Field(default="Stock", description="Stock | ETF | MutualFund")
    quantity: float = Field(default=0.0, description="Units held (>= 0)")
    average_buy_price: float = Field(default=0.0, description="Avg cost per unit in INR (>= 0)")

    @field_validator("asset_symbol")
    @classmethod
    def clean_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        # Strip any surrounding quotes or whitespace artefacts
        v = v.strip('"').strip("'").strip()
        if not v:
            raise ValueError("asset_symbol cannot be empty.")
        # Allow: letters, digits, dot, dash, caret, ampersand (covers ^NSEI, BRK.A, etc.)
        if not re.match(r"^[A-Z0-9\.\-\^&]+$", v, re.IGNORECASE):
            raise ValueError(f"'{v}' contains invalid characters for a ticker symbol.")
        return v

    @field_validator("asset_type")
    @classmethod
    def normalise_type(cls, v: str) -> str:
        v = str(v).strip().lower()
        if "etf" in v:
            return "ETF"
        if "mutual" in v or "mf" in v or "fund" in v:
            return "MutualFund"
        return "Stock"  # default for equity / unknown

    @field_validator("quantity", "average_buy_price", mode="before")
    @classmethod
    def coerce_numeric(cls, v):
        if v is None or v == "":
            return 0.0
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip())
        except (ValueError, TypeError):
            return 0.0


class HoldingCreate(HoldingCSVRow):
    """Extends CSVRow with portfolio_id for DB insertion."""
    portfolio_id: uuid.UUID


class HoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    asset_symbol: str
    asset_type: str
    quantity: float
    average_buy_price: float


class BulkInsertResponse(BaseModel):
    inserted: int
    errors: list[dict]
