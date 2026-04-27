"""
app/schemas/preferences.py
Pydantic v2 schemas for SystemPreferences.

The JSONB column is validated against a structured PreferencesPayload model
so the API layer never accepts arbitrary blobs.
"""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Inner model — maps to the JSONB structure ──────────────────────────────

class AlertThresholds(BaseModel):
    """Thresholds that trigger rebalancing or notification alerts."""
    drift_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description="Portfolio drift percentage that triggers an alert. E.g. 5.0 = 5%.",
        examples=[5.0],
    )


class PreferencesPayload(BaseModel):
    """
    Structured representation of the JSONB preferences column.
    Stored verbatim in the DB; validated on every write.
    """
    risk_tolerance: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="User's overall risk appetite.",
        examples=["medium"],
    )
    alert_thresholds: AlertThresholds = Field(
        default_factory=AlertThresholds,
        description="Thresholds that trigger alerts or rebalancing.",
    )
    rebalance_frequency: Literal["monthly", "quarterly", "annually"] = Field(
        default="quarterly",
        description="How often the portfolio should be rebalanced.",
        examples=["quarterly"],
    )


# ── API-level schemas ───────────────────────────────────────────────────────

class SystemPreferencesCreate(BaseModel):
    """Request body for creating or replacing a user's preferences."""
    user_id: uuid.UUID
    preferences: PreferencesPayload = Field(default_factory=PreferencesPayload)


class SystemPreferencesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    preferences: PreferencesPayload
