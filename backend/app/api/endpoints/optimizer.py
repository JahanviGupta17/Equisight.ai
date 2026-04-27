"""
app/api/endpoints/optimizer.py
Phase 2 endpoints:

  POST /api/v1/optimize/markowitz/{portfolio_id}
  POST /api/v1/optimize/black-litterman/{portfolio_id}
  GET  /api/v1/analytics/{portfolio_id}
  POST /api/v1/analyse/{portfolio_id}   ← full pipeline with investor profile

All three follow the same pipeline:
  1. Query Holdings from DB
  2. Fetch current prices (30-day via market_data service)
  3. Fetch 1-year history (via optimizer service)
  4. Run the requested calculation
  5. Return structured response
"""
import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pypfopt.exceptions import OptimizationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.holding import Holding
from app.schemas.optimizer import (
    AnalyticsResult,
    BlackLittermanRequest,
    MarkowitzRequest,
    OptimizationResult,
)
from app.services import analytics as analytics_svc
from app.services import market_data as market_data_svc
from app.services import optimizer as optimizer_svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Quantitative Engine"])


# ── Shared helper ────────────────────────────────────────────────────────────

async def _get_holdings(portfolio_id: uuid.UUID, db: AsyncSession) -> list[Holding]:
    """Fetch holdings for a portfolio or raise 404."""
    try:
        result = await db.execute(
            select(Holding).where(Holding.portfolio_id == portfolio_id)
        )
        holdings = result.scalars().all()
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is temporarily unavailable.",
        ) from exc

    if not holdings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No holdings found for portfolio_id '{portfolio_id}'. "
                "Upload holdings first via POST /portfolio/upload."
            ),
        )
    return holdings


def _enrich_holdings(
    holdings: list[Holding],
    price_data: dict[str, Any],
) -> list[dict]:
    """Merge DB holding rows with fetched price data into flat dicts."""
    return [
        {
            "asset_symbol": h.asset_symbol,
            "asset_type": h.asset_type,
            "quantity": h.quantity,
            "average_buy_price": h.average_buy_price,
            "current_price": (price_data.get(h.asset_symbol) or {}).get("current_price"),
        }
        for h in holdings
    ]


# ── POST /api/v1/optimize/markowitz/{portfolio_id} ───────────────────────────

@router.post(
    "/optimize/markowitz/{portfolio_id}",
    response_model=OptimizationResult,
    summary="Markowitz Mean-Variance Optimization",
    description=(
        "Fetches 1-year price history and runs PyPortfolioOpt's EfficientFrontier "
        "on the portfolio's holdings. Supports max_sharpe, min_volatility, "
        "efficient_return, and efficient_risk objectives."
    ),
)
async def optimize_markowitz(
    portfolio_id: uuid.UUID,
    payload: MarkowitzRequest,
    db: AsyncSession = Depends(get_db),
) -> OptimizationResult:
    holdings = await _get_holdings(portfolio_id, db)
    symbols = [h.asset_symbol for h in holdings]
    asset_types = {h.asset_symbol: h.asset_type for h in holdings}

    logger.info("Markowitz optimizing portfolio %s — %d assets", portfolio_id, len(symbols))

    try:
        prices = await optimizer_svc.fetch_historical_prices(symbols, asset_types=asset_types)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Timed out fetching price history.",
        )

    if prices.empty:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Yahoo Finance returned no price history. Check ticker symbols.",
        )

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: optimizer_svc.run_markowitz(
                prices=prices,
                objective=payload.objective,
                target_return=payload.target_return,
                target_risk=payload.target_risk,
                long_only=payload.long_only,
                current_weights=None,   # standalone endpoint — no DNT gate
            ),
        )
    except (OptimizationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return OptimizationResult(
        portfolio_id=portfolio_id,
        model="markowitz",
        weights=result["weights"],
        expected_annual_return=result["expected_annual_return"],
        annual_volatility=result["annual_volatility"],
        sharpe_ratio=result["sharpe_ratio"],
        meta={"objective": result["objective"], "assets_optimized": len(prices.columns)},
    )


# ── POST /api/v1/optimize/black-litterman/{portfolio_id} ────────────────────

@router.post(
    "/optimize/black-litterman/{portfolio_id}",
    response_model=OptimizationResult,
    summary="Black-Litterman Optimization",
    description=(
        "Blends a market/equal-weight prior with your absolute return views, "
        "then maximises Sharpe on the posterior expected returns + covariance. "
        "Views must be provided as a dict of {ticker: expected_annual_return}."
    ),
)
async def optimize_black_litterman(
    portfolio_id: uuid.UUID,
    payload: BlackLittermanRequest,
    db: AsyncSession = Depends(get_db),
) -> OptimizationResult:
    holdings = await _get_holdings(portfolio_id, db)
    symbols = [h.asset_symbol for h in holdings]
    asset_types = {h.asset_symbol: h.asset_type for h in holdings}

    logger.info("Black-Litterman optimizing portfolio %s — %d assets", portfolio_id, len(symbols))

    try:
        prices = await optimizer_svc.fetch_historical_prices(symbols, asset_types=asset_types)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Timed out fetching price history.",
        )

    if prices.empty:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Yahoo Finance returned no price history. Check ticker symbols.",
        )

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: optimizer_svc.run_black_litterman(
                prices=prices,
                views=payload.views,
                market_weights=payload.market_weights,
                current_weights=None,   # standalone endpoint — no DNT gate
            ),
        )
    except (OptimizationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return OptimizationResult(
        portfolio_id=portfolio_id,
        model="black_litterman",
        weights=result["weights"],
        expected_annual_return=result["expected_annual_return"],
        annual_volatility=result["annual_volatility"],
        sharpe_ratio=result["sharpe_ratio"],
        meta={
            "bl_posterior_returns": result["bl_posterior_returns"],
            "views_applied": result["views_applied"],
            "prior": result["prior"],
        },
    )


# ── GET /api/v1/analytics/{portfolio_id} ────────────────────────────────────

@router.get(
    "/analytics/{portfolio_id}",
    response_model=AnalyticsResult,
    summary="Full Portfolio Analytics",
    description=(
        "Calculates and returns the complete current-state analytics dashboard: "
        "market-value weights, per-asset absolute returns, 30-day rolling volatility, "
        "maximum drawdown, and asset-type concentration with HHI score."
    ),
)
async def get_analytics(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResult:
    holdings = await _get_holdings(portfolio_id, db)
    symbols = [h.asset_symbol for h in holdings]
    asset_types = {h.asset_symbol: h.asset_type for h in holdings}

    logger.info("Running analytics for portfolio %s — %d assets", portfolio_id, len(symbols))

    try:
        price_data = await market_data_svc.fetch_prices(symbols)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Timed out fetching prices from Yahoo Finance.",
        )

    try:
        prices_df = await optimizer_svc.fetch_historical_prices(symbols, asset_types=asset_types)
    except asyncio.TimeoutError:
        prices_df = None

    enriched = _enrich_holdings(holdings, price_data)
    weights_result = analytics_svc.calculate_current_weights(enriched)
    total_value = weights_result.get("total_value", 0.0)
    returns_result = analytics_svc.calculate_absolute_returns(enriched)

    vol_result: dict = {}
    drawdown_result: dict = {}
    if prices_df is not None and not prices_df.empty:
        vol_result = analytics_svc.calculate_rolling_volatility(prices_df, window=30)
        drawdown_result = analytics_svc.calculate_maximum_drawdown(prices_df)

    concentration_result = analytics_svc.calculate_sector_concentration(enriched, total_value)

    beta_result: dict = {}
    if prices_df is not None and not prices_df.empty:
        beta_result = await analytics_svc.calculate_portfolio_beta(
            prices_df, weights_result.get("weights", {}), period="1y"
        )

    return AnalyticsResult(
        portfolio_id=portfolio_id,
        current_weights=weights_result.get("weights", {}),
        total_portfolio_value=total_value,
        absolute_returns=returns_result["assets"],
        portfolio_summary=returns_result["portfolio_summary"],
        rolling_volatility_30d=vol_result,
        max_drawdown_pct=drawdown_result,
        sector_concentration=concentration_result,
        portfolio_beta=beta_result,
    )


# ── POST /api/v1/analyse/{portfolio_id} ──────────────────────────────────────
# Full pipeline: Investor Profile → Optimize → Analytics → Drift → RAG advisory

from pydantic import BaseModel as _AnalyseBase
from typing import Literal as _AnalyseLiteral


class AnalyseRequest(_AnalyseBase):
    objective: _AnalyseLiteral["max_sharpe", "min_volatility"] = "max_sharpe"
    force_advisory: bool = True


@router.post(
    "/analyse/{portfolio_id}",
    summary="Full Pipeline: Optimize + Analytics + Advisory",
    description=(
        "Runs Markowitz optimization (personalized via saved investor profile if available), "
        "calculates analytics, compares current vs. optimized weights, "
        "and triggers the RAG advisory generation pipeline. Returns analytics + optimization "
        "result immediately; advisory arrives via WebSocket."
    ),
)
async def analyse_portfolio(
    portfolio_id: uuid.UUID,
    payload: AnalyseRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = payload or AnalyseRequest()
    holdings = await _get_holdings(portfolio_id, db)
    symbols = [h.asset_symbol for h in holdings]
    asset_types = {h.asset_symbol: h.asset_type for h in holdings}

    logger.info("Full analysis triggered for portfolio %s (%d assets)", portfolio_id, len(symbols))

    # ── Load investor preferences + derive math constraints ───────────────────
    from app.models.user_preferences import UserPreferences
    from app.schemas.user_preferences import UserPreferencesRead
    from app.services.router import get_history_period_for_horizon, route_portfolio_optimization

    pref_result = await db.execute(
        select(UserPreferences).where(UserPreferences.portfolio_id == portfolio_id)
    )
    saved_prefs_db = pref_result.scalars().first()

    if saved_prefs_db:
        saved_prefs = UserPreferencesRead.model_validate(saved_prefs_db)
        history_period = get_history_period_for_horizon(saved_prefs.time_horizon)
        logger.info(
            "Applying investor profile -> time_horizon=%s -> history_period=%s",
            saved_prefs.time_horizon, history_period
        )
    else:
        saved_prefs = None
        history_period = "3y"
        logger.info("No investor profile found — using default")

    # ── Step 1: Fetch prices ──────────────────────────────────────────────────
    try:
        price_data = await market_data_svc.fetch_prices(symbols)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Timed out fetching prices.")

    try:
        prices_df = await optimizer_svc.fetch_historical_prices(symbols, asset_types=asset_types, history_period=history_period)
    except asyncio.TimeoutError:
        prices_df = None

    # ── Step 2: Analytics ─────────────────────────────────────────────────────
    enriched = _enrich_holdings(holdings, price_data)
    weights_result = analytics_svc.calculate_current_weights(enriched)
    total_value = weights_result.get("total_value", 0.0)
    returns_result = analytics_svc.calculate_absolute_returns(enriched)
    current_weights = weights_result.get("weights", {})

    vol_result, drawdown_result, beta_result = {}, {}, {}
    if prices_df is not None and not prices_df.empty:
        vol_result = analytics_svc.calculate_rolling_volatility(prices_df, window=30)
        drawdown_result = analytics_svc.calculate_maximum_drawdown(prices_df)
        beta_result = await analytics_svc.calculate_portfolio_beta(
            prices_df, current_weights, period="1y"
        )

    analytics_out = AnalyticsResult(
        portfolio_id=portfolio_id,
        current_weights=current_weights,
        total_portfolio_value=total_value,
        absolute_returns=returns_result["assets"],
        portfolio_summary=returns_result["portfolio_summary"],
        rolling_volatility_30d=vol_result,
        max_drawdown_pct=drawdown_result,
        sector_concentration=analytics_svc.calculate_sector_concentration(enriched, total_value),
        portfolio_beta=beta_result,
    )

    # ── Step 3: Optimization (via intelligent router) ─────────────────────────
    optimization_out = None
    optimized_weights: dict = {}
    engine_name = "markowitz"
    if prices_df is not None and not prices_df.empty:
        try:
            loop = asyncio.get_running_loop()
            routing_rationale = ""
            if saved_prefs:
                opt_result, engine_name, routing_rationale = await loop.run_in_executor(
                    None,
                    lambda: route_portfolio_optimization(
                        saved_prefs, prices_df, current_weights=current_weights
                    )
                )
            else:
                opt_result = await loop.run_in_executor(
                    None,
                    lambda: optimizer_svc.run_markowitz(
                        prices=prices_df,
                        objective=payload.objective,
                        long_only=True,
                        current_weights=current_weights,
                    ),
                )
                routing_rationale = (
                    "No investor profile found. "
                    "Defaulting to Markowitz Max-Sharpe optimisation."
                )

            optimized_weights = opt_result.get("weights", {})

            optimization_out = {
                "model": engine_name,
                "weights": optimized_weights,
                "expected_annual_return": opt_result.get("expected_annual_return"),
                "annual_volatility": opt_result.get("annual_volatility"),
                "sharpe_ratio": opt_result.get("sharpe_ratio"),
                "constraints_applied": opt_result.get("constraints_applied", {}),
                "investor_profile": saved_prefs.model_dump() if saved_prefs else None,
                "engine_explanation": routing_rationale,
            }
        except Exception as exc:
            logger.warning("Optimization step failed during analyse: %s", exc)

    # ── Step 4: Drift comparison ──────────────────────────────────────────────
    drift_details: dict = {"drifts": [], "total_value": total_value}
    if optimized_weights:
        DRIFT_THRESHOLD = 0.05
        drifts = []
        for asset, opt_w in optimized_weights.items():
            curr_w = current_weights.get(asset, 0.0)
            abs_drift = abs(curr_w - opt_w)
            if abs_drift > DRIFT_THRESHOLD or payload.force_advisory:
                drifts.append({
                    "asset": asset,
                    "current_weight": round(curr_w, 4),
                    "target_weight": round(opt_w, 4),
                    "absolute_drift": round(abs_drift, 4),
                    "relative_drift_pct": round((abs_drift / opt_w * 100) if opt_w else 0, 2),
                })
        drift_details["drifts"] = drifts

    # ── Step 5: Persist DriftEvent + fire RAG advisory as asyncio background task
    advisory_triggered = False
    if drift_details["drifts"] or payload.force_advisory:
        from app.models.drift_event import DriftEvent
        from app.tasks.drift import generate_rag_advisory_task

        event = DriftEvent(
            portfolio_id=portfolio_id,
            details=drift_details,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)

        if drift_details["drifts"]:
            worst = max(drift_details["drifts"], key=lambda d: d["absolute_drift"])
            focus_asset = worst["asset"]
        else:
            focus_asset = symbols[0] if symbols else "NIFTY50"

        # create_task schedules the coroutine on the running event loop.
        # It runs concurrently — the HTTP response returns immediately while
        # the advisory is generated in the background and pushed via WebSocket.
        asyncio.create_task(
            generate_rag_advisory_task(str(portfolio_id), str(event.id), focus_asset)
        )
        advisory_triggered = True
        logger.info(
            "RAG advisory task started (asyncio) for portfolio %s, asset %s",
            portfolio_id, focus_asset,
        )

    return {
        "status": "ok",
        "advisory_triggered": advisory_triggered,
        "analytics": analytics_out.model_dump(),
        "optimization": optimization_out,
        "drift_summary": drift_details,
        "message": (
            "Analysis complete. Advisory is being generated — watch the Active Alerts page "
            "for your personalised recommendation."
            if advisory_triggered else
            "Analysis complete. No significant drift detected."
        ),
    }
