"""
app/api/endpoints/preferences.py

POST /api/v1/portfolio/{portfolio_id}/preferences
  — Saves investor profile answers. Creates on first call, updates on repeat.

GET /api/v1/portfolio/{portfolio_id}/preferences
  — Returns the current preferences (or sensible defaults if none saved).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.user_preferences import UserPreferences
from app.schemas.user_preferences import (
    UserPreferencesCreate,
    UserPreferencesRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Investor Profile"])


@router.post(
    "/portfolio/{portfolio_id}/preferences",
    response_model=UserPreferencesRead,
    status_code=status.HTTP_200_OK,
    summary="Save Investor Profile (Wizard answers)",
    description=(
        "Upserts the investor profile for a portfolio. "
        "On first call creates the record; on subsequent calls updates it. "
        "The stored preferences are used by the router to direct to the correct engine."
    ),
)
async def save_preferences(
    portfolio_id: uuid.UUID,
    payload: UserPreferencesCreate,
    db: AsyncSession = Depends(get_db),
) -> UserPreferencesRead:
    # ── Upsert (fetch existing or create new) ────────────────────────────────
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.portfolio_id == portfolio_id)
    )
    prefs = result.scalars().first()

    if prefs:
        # Update existing row
        prefs.time_horizon = payload.time_horizon
        prefs.drawdown_tolerance = payload.drawdown_tolerance
        prefs.liquidity_needs = payload.liquidity_needs
        prefs.experience_level = payload.experience_level
        prefs.diversification_preference = payload.diversification_preference
        logger.info("Updated preferences for portfolio %s", portfolio_id)
    else:
        # Create new row
        prefs = UserPreferences(
            portfolio_id=portfolio_id,
            time_horizon=payload.time_horizon,
            drawdown_tolerance=payload.drawdown_tolerance,
            liquidity_needs=payload.liquidity_needs,
            experience_level=payload.experience_level,
            diversification_preference=payload.diversification_preference,
        )
        db.add(prefs)
        logger.info("Created preferences for portfolio %s", portfolio_id)

    await db.flush()
    await db.refresh(prefs)

    return UserPreferencesRead.model_validate(prefs)


@router.get(
    "/portfolio/{portfolio_id}/preferences",
    response_model=UserPreferencesRead,
    summary="Get Investor Profile",
    description="Returns the saved investor profile for a portfolio, or 404 if not yet set.",
)
async def get_preferences(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> UserPreferencesRead:
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.portfolio_id == portfolio_id)
    )
    prefs = result.scalars().first()

    if not prefs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No preferences found for portfolio '{portfolio_id}'. Run the onboarding wizard first.",
        )

    return UserPreferencesRead.model_validate(prefs)
