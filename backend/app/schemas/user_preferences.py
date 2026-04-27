"""
app/schemas/user_preferences.py
Pydantic v2 schemas for the Investor Profile Wizard.
"""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ── Strict literals matching the wizard UI choices ───────────────────────────

TimeHorizon = Literal["1-3 Years", "4-7 Years", "8+ Years"]
DrawdownTolerance = Literal[
    "Panic at 5% drop (Protect my capital)",
    "Uncomfortable at 15% (Balanced)",
    "Can ignore 25%+ crashes (Aggressive)"
]
LiquidityNeeds = Literal["High (Need cash soon)", "Moderate", "Low (Locked away)"]
ExperienceLevel = Literal[
    "Beginner (Do it for me)",
    "Intermediate",
    "Advanced (I want to input custom views)"
]
DiversificationPreference = Literal["High (Maximum Spread)", "Standard", "Focused"]


class UserPreferencesCreate(BaseModel):
    """Request body for POST /api/v1/portfolio/{portfolio_id}/preferences."""
    time_horizon: TimeHorizon = "4-7 Years"
    drawdown_tolerance: DrawdownTolerance = "Uncomfortable at 15% (Balanced)"
    liquidity_needs: LiquidityNeeds = "Moderate"
    experience_level: ExperienceLevel = "Beginner (Do it for me)"
    diversification_preference: DiversificationPreference = "Standard"


class UserPreferencesRead(BaseModel):
    """Response body — returned after save."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    time_horizon: str
    drawdown_tolerance: str
    liquidity_needs: str
    experience_level: str
    diversification_preference: str

