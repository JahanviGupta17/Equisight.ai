"""
app/schemas/optimizer.py
Pydantic v2 schemas for Phase 2 — Optimization & Analytics request/response.
"""
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Markowitz ───────────────────────────────────────────────────────────────

class MarkowitzRequest(BaseModel):
    """
    Request body for the Mean-Variance optimizer.
    objective determines what the solver maximises/minimises.
    """
    objective: Literal[
        "max_sharpe",       # Maximise Sharpe ratio (default)
        "min_volatility",   # Minimise portfolio volatility
        "efficient_return", # Hit a specific target return
        "efficient_risk",   # Hit a specific target volatility
    ] = Field(
        default="max_sharpe",
        description="Optimization objective.",
        examples=["max_sharpe"],
    )
    target_return: float | None = Field(
        default=None, ge=0.0, le=5.0,
        description="Required only when objective='efficient_return'. Annualised decimal (0.15 = 15%).",
        examples=[0.15],
    )
    target_risk: float | None = Field(
        default=None, ge=0.0, le=5.0,
        description="Required only when objective='efficient_risk'. Annualised decimal (0.10 = 10%).",
        examples=[0.10],
    )
    long_only: bool = Field(
        default=True,
        description="If False, allows short positions (weight_bounds=(-1,1)).",
    )


# ── Black-Litterman ─────────────────────────────────────────────────────────

class BlackLittermanRequest(BaseModel):
    """
    Request body for the Black-Litterman optimizer.

    views: a dict mapping ticker → expected annual return (absolute views).
      e.g. {"BEL.NS": 0.18, "NTPC.NS": 0.12}
    market_weights: optional dict mapping ticker → market-cap weight prior.
      If omitted, an equal-weight prior is used.
    """
    views: dict[str, float] = Field(
        ...,
        description=(
            "Absolute return views per ticker. "
            "Key = Yahoo Finance ticker (must match DB). "
            "Value = expected annual return as decimal."
        ),
        examples=[{"BEL.NS": 0.18, "NTPC.NS": 0.12}],
    )
    market_weights: dict[str, float] | None = Field(
        default=None,
        description=(
            "Optional market-cap weights per ticker used as prior. "
            "If omitted, equal weights are assumed."
        ),
        examples=[{"BEL.NS": 0.4, "NTPC.NS": 0.3, "HDFCBANK.NS": 0.3}],
    )


# ── Shared result schemas ────────────────────────────────────────────────────

class OptimizationResult(BaseModel):
    portfolio_id: uuid.UUID
    model: Literal["markowitz", "black_litterman"]
    weights: dict[str, float]
    expected_annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    meta: dict[str, Any] = Field(default_factory=dict)


class PortfolioSummary(BaseModel):
    total_cost_basis: float
    total_market_value: float
    total_absolute_return_inr: float
    total_percentage_return: float


class AssetReturn(BaseModel):
    average_buy_price: float
    current_price: float | None
    quantity: float
    cost_basis: float
    market_value: float
    absolute_return_inr: float
    percentage_return: float


class AnalyticsResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    portfolio_id: uuid.UUID

    # Current state
    current_weights: dict[str, float]
    total_portfolio_value: float

    # Returns
    absolute_returns: dict[str, Any]
    portfolio_summary: PortfolioSummary

    # Risk metrics
    rolling_volatility_30d: dict[str, float]
    max_drawdown_pct: dict[str, float]

    # Concentration
    sector_concentration: dict[str, Any]
    
    # Beta
    portfolio_beta: dict[str, Any] | None = None
