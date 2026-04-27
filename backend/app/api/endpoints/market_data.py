"""
app/api/endpoints/market_data.py
GET /api/v1/market-data/sync/{portfolio_id}
Fetches live prices and 30-day history for all holdings in a portfolio.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.holding import Holding
from app.services import market_data as market_data_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market-data", tags=["Market Data"])


@router.get(
    "/sync/{portfolio_id}",
    summary="Sync market data for a portfolio",
    description=(
        "Queries all holdings for the given portfolio_id, fetches the current "
        "live price and last 30 days of closing prices from Yahoo Finance for "
        "each asset, and returns the aggregated data payload."
    ),
)
async def sync_market_data(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # ── 1. Fetch holdings from DB ───────────────────────────────────────────
    try:
        result = await db.execute(
            select(Holding).where(Holding.portfolio_id == portfolio_id)
        )
        holdings = result.scalars().all()
    except OperationalError as exc:
        logger.error("DB connection error for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is temporarily unavailable. Please try again.",
        ) from exc

    if not holdings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No holdings found for portfolio_id '{portfolio_id}'. "
                   "Upload holdings first via POST /portfolio/upload.",
        )

    symbols = [h.asset_symbol for h in holdings]
    logger.info("Syncing market data for portfolio %s — symbols: %s", portfolio_id, symbols)

    # ── 2. Fetch prices from yfinance ───────────────────────────────────────
    try:
        price_data = await market_data_svc.fetch_prices(symbols)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Yahoo Finance request timed out. Please try again shortly.",
        )
    except Exception as exc:
        logger.error("Unexpected error fetching market data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Market data fetch failed: {exc}",
        ) from exc

    # ── 3. Gate on entirely empty response (e.g. all symbols invalid) ───────
    has_any_data = any(
        v.get("current_price") is not None for v in price_data.values()
    )
    if not has_any_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Yahoo Finance returned no data for any symbol in this portfolio. "
                "Check that all tickers include the correct exchange suffix "
                "(e.g. BEL.NS, 0P0000YWL1.BO) and that Yahoo Finance is reachable."
            ),
        )

    return {
        "portfolio_id": str(portfolio_id),
        "symbol_count": len(symbols),
        "assets": price_data,
    }
