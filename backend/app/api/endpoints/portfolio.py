"""
app/api/endpoints/portfolio.py
POST /api/v1/portfolio/create          — creates a portfolio and returns its UUID.
GET  /api/v1/portfolio/{id}/history    — real daily portfolio value time-series.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.schemas.portfolio import PortfolioCreate, PortfolioRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

# ---------------------------------------------------------------------------
# Convenience: the hardcoded test user UUID for Phase 1
# ---------------------------------------------------------------------------
TEST_USER_ID = uuid.UUID(settings.TEST_USER_ID)


@router.post(
    "/create",
    response_model=PortfolioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new portfolio",
    description=(
        "Creates a portfolio record for the given user and returns the "
        "generated portfolio_id. Use this UUID in the /upload endpoint."
    ),
)
async def create_portfolio(
    payload: PortfolioCreate,
    db: AsyncSession = Depends(get_db),
) -> PortfolioRead:
    """
    Phase 1 note: user_id is not authenticated. Pass the test user UUID:
      00000000-0000-0000-0000-000000000001
    """
    portfolio = Portfolio(
        user_id=payload.user_id,
        name=payload.name,
        target_return=payload.target_return,
        target_risk=payload.target_risk,
    )
    try:
        db.add(portfolio)
        await db.flush()   # get the auto-generated UUID before commit
        await db.refresh(portfolio)
    except IntegrityError as exc:
        logger.error("IntegrityError creating portfolio: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Portfolio could not be created due to a constraint violation. "
                   "Ensure the user_id exists.",
        ) from exc
    except OperationalError as exc:
        logger.error("DB connection error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is temporarily unavailable. Please try again.",
        ) from exc

    logger.info("Created portfolio '%s' with id=%s", portfolio.name, portfolio.id)
    return PortfolioRead.model_validate(portfolio)


# ── GET /api/v1/portfolio/{portfolio_id}/history ─────────────────────────────

@router.get(
    "/{portfolio_id}/history",
    summary="Daily Portfolio Value Time-Series",
    description=(
        "Computes the daily portfolio value using historical prices and the "
        "current quantity of each holding. Returns an array of {date, value} "
        "objects suitable for direct use in Recharts. Data is Redis-cached for "
        "12 hours; falls back to live fetch on cache miss or Redis unavailability."
    ),
)
async def portfolio_history(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # ── 1. Load holdings ──────────────────────────────────────────────────────
    try:
        result = await db.execute(
            select(Holding).where(Holding.portfolio_id == portfolio_id)
        )
        holdings = result.scalars().all()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc

    if not holdings:
        raise HTTPException(
            status_code=404,
            detail=f"No holdings for portfolio_id '{portfolio_id}'.",
        )

    symbols    = [h.asset_symbol for h in holdings]
    quantities = {h.asset_symbol: h.quantity for h in holdings}
    asset_types = {h.asset_symbol: h.asset_type for h in holdings}

    # ── 2. Fetch price history (uses Redis cache in optimizer service) ─────────
    from app.services import optimizer as optimizer_svc

    try:
        prices_df = await optimizer_svc.fetch_historical_prices(
            symbols, asset_types=asset_types, history_period="1y"
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=502, detail="Timed out fetching price history.")

    if prices_df.empty:
        raise HTTPException(status_code=502, detail="No price data returned for holdings.")

    # ── 3. Compute daily portfolio value ──────────────────────────────────────
    # portfolio_value[date] = sum(quantity_i * price_i[date])
    import pandas as pd
    aligned_quantities = pd.Series(
        {sym: quantities.get(sym, 0.0) for sym in prices_df.columns}
    )
    daily_value: pd.Series = prices_df.mul(aligned_quantities, axis=1).sum(axis=1)

    # ── 4. Serialise to [{date, value}] ──────────────────────────────────────
    series = [
        {"date": str(date.date()), "value": round(float(val), 2)}
        for date, val in daily_value.items()
        if val > 0
    ]

    return {"portfolio_id": str(portfolio_id), "series": series, "count": len(series)}
