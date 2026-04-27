"""
app/services/analytics.py
State Engine — calculates the current portfolio's analytical baseline.

All functions are pure / synchronous (called from async endpoints via
run_in_executor where heavy, or directly since pandas ops are fast).
Metrics:
  - Current weights (market-value weighted)
  - Absolute returns (per asset + portfolio total)
  - Rolling 30-day annualised volatility
  - Maximum drawdown
  - Sector / asset-type concentration + HHI
"""
import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
NIFTY50_TICKER = "^NSEI"  # Nifty 50 benchmark for Beta calculation


# ── 1. Current Weights ───────────────────────────────────────────────────────

def calculate_current_weights(
    holdings: list[dict],
) -> dict[str, Any]:
    """
    Returns market-value weights and total portfolio value.

    holdings items must include:
      asset_symbol, quantity, current_price (float | None)
    """
    enriched = []
    total_value = 0.0

    for h in holdings:
        price = h.get("current_price") or 0.0
        market_value = h["quantity"] * price
        total_value += market_value
        enriched.append({**h, "market_value": market_value})

    if total_value == 0:
        return {
            "error": "Total portfolio value is zero. Prices may not have been fetched correctly.",
            "weights": {},
            "total_value": 0.0,
        }

    weights = {
        h["asset_symbol"]: round(h["market_value"] / total_value, 6)
        for h in enriched
    }
    return {"weights": weights, "total_value": round(total_value, 2)}


# ── 2. Absolute Returns ──────────────────────────────────────────────────────

def calculate_absolute_returns(
    holdings: list[dict],
) -> dict[str, Any]:
    """
    Per-asset and portfolio-level P&L.

    holdings items must include:
      asset_symbol, quantity, average_buy_price, current_price (float | None)
    """
    asset_returns: dict[str, dict] = {}
    total_cost = 0.0
    total_market_value = 0.0

    for h in holdings:
        current_price = h.get("current_price") or 0.0
        avg_buy = h["average_buy_price"]
        qty = h["quantity"]

        cost_basis = qty * avg_buy
        market_value = qty * current_price
        abs_return = market_value - cost_basis
        pct_return = (
            (current_price - avg_buy) / avg_buy * 100
            if avg_buy > 0 else 0.0
        )

        total_cost += cost_basis
        total_market_value += market_value

        asset_returns[h["asset_symbol"]] = {
            "average_buy_price": round(avg_buy, 4),
            "current_price": round(current_price, 4),
            "quantity": qty,
            "cost_basis": round(cost_basis, 2),
            "market_value": round(market_value, 2),
            "absolute_return_inr": round(abs_return, 2),
            "percentage_return": round(pct_return, 2),
        }

    portfolio_pct = (
        (total_market_value - total_cost) / total_cost * 100
        if total_cost > 0 else 0.0
    )

    return {
        "assets": asset_returns,
        "portfolio_summary": {
            "total_cost_basis": round(total_cost, 2),
            "total_market_value": round(total_market_value, 2),
            "total_absolute_return_inr": round(total_market_value - total_cost, 2),
            "total_percentage_return": round(portfolio_pct, 2),
        },
    }


# ── 3. Rolling Volatility ────────────────────────────────────────────────────

def calculate_rolling_volatility(
    prices_df: pd.DataFrame,
    window: int = 30,
) -> dict[str, float]:
    """
    Latest rolling annualised volatility (σ * √252) per asset.
    Requires a DataFrame of closing prices with assets as columns.
    """
    if prices_df.empty or len(prices_df) < window:
        logger.warning("Not enough price history (%d rows) for %d-day rolling volatility.", len(prices_df), window)
        return {}

    daily_returns = prices_df.pct_change().dropna()
    rolling_vol = (
        daily_returns.rolling(window=window).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    )
    latest = rolling_vol.iloc[-1]

    return {
        sym: round(float(vol), 4)
        for sym, vol in latest.items()
        if not np.isnan(vol)
    }


# ── 4. Maximum Drawdown ──────────────────────────────────────────────────────

def calculate_maximum_drawdown(prices_df: pd.DataFrame) -> dict[str, float]:
    """
    Max peak-to-trough percentage decline per asset over the price history.
    Returns a dict of {ticker: max_drawdown_pct} where values are negative.
    """
    result: dict[str, float] = {}
    for col in prices_df.columns:
        series = prices_df[col].dropna()
        if series.empty:
            continue
        rolling_max = series.cummax()
        drawdown = (series - rolling_max) / rolling_max
        result[col] = round(float(drawdown.min()) * 100, 2)  # percentage, negative
    return result


# ── 5. Sector / Asset-Type Concentration ────────────────────────────────────

def calculate_sector_concentration(
    holdings: list[dict],
    total_value: float,
) -> dict[str, Any]:
    """
    Groups by asset_type (Stock / ETF / MutualFund) and computes:
      - Weight per type (%)
      - Herfindahl–Hirschman Index (HHI) as concentration score
        0 = perfectly diversified, 10 000 = single position

    holdings items must include: asset_type, quantity, current_price
    """
    if total_value == 0:
        return {"by_asset_type_pct": {}, "herfindahl_index": 0, "concentration_level": "N/A"}

    bucket: dict[str, float] = {}
    for h in holdings:
        price = h.get("current_price") or 0.0
        mv = h["quantity"] * price
        atype = h.get("asset_type", "Unknown")
        bucket[atype] = bucket.get(atype, 0.0) + mv

    concentration = {k: round(v / total_value * 100, 2) for k, v in bucket.items()}
    hhi = round(sum((w / 100) ** 2 for w in concentration.values()) * 10_000, 2)

    if hhi > 2_500:
        level = "High"
    elif hhi > 1_000:
        level = "Medium"
    else:
        level = "Low"

    return {
        "by_asset_type_pct": concentration,
        "herfindahl_index": hhi,
        "concentration_level": level,
    }


# ── 6. Portfolio Beta vs Nifty 50 ───────────────────────────────────────────

def _sync_calculate_beta(
    prices_df: pd.DataFrame,
    weights: dict[str, float],
    period: str = "1y",
) -> dict[str, Any]:
    """
    Calculates individual asset Beta and weighted portfolio Beta vs. Nifty 50.
    Beta > 1: more volatile than market. Beta < 1: more defensive.

    Robust to both yfinance's old (flat Series) and new (MultiIndex DataFrame)
    column return formats. Safely handles tz-naive and tz-aware indices.
    """
    if prices_df.empty:
        return {"error": "No price data available for Beta calculation."}

    try:
        raw_benchmark = yf.download(
            NIFTY50_TICKER, period=period, interval="1d",
            auto_adjust=True, progress=False,
        )
        if raw_benchmark.empty:
            return {"error": "Could not fetch Nifty 50 benchmark data."}

        # ── Robustly extract a flat Series from whichever format yfinance returned ──
        close_col = raw_benchmark["Close"]

        # yfinance ≥ 0.2 with a single ticker returns a DataFrame with the ticker
        # name as the column (MultiIndex flattened). Squeeze it to a Series.
        if isinstance(close_col, pd.DataFrame):
            # Flatten: take the first (and only) column
            benchmark: pd.Series = close_col.iloc[:, 0].copy()
        else:
            benchmark = close_col.copy()

        # ── Normalise timezone \u2014 make both indices tz-naive ──────────────────────
        if benchmark.index.tz is not None:
            benchmark.index = benchmark.index.tz_convert(None)  # tz-aware  → tz-naive
        else:
            benchmark.index = pd.to_datetime(benchmark.index)   # already tz-naive

        if prices_df.index.tz is not None:
            prices_df = prices_df.copy()
            prices_df.index = prices_df.index.tz_convert(None)
        else:
            prices_df.index = pd.to_datetime(prices_df.index)

        # ── Name the series and merge ─────────────────────────────────────────
        benchmark.name = "NIFTY50"
        combined = prices_df.join(benchmark, how="inner")
        if len(combined) < 30:
            return {"error": "Insufficient overlapping data between portfolio and benchmark."}

        daily_returns = combined.pct_change().dropna()
        benchmark_returns: pd.Series = daily_returns["NIFTY50"]
        portfolio_returns: pd.DataFrame = daily_returns.drop(columns=["NIFTY50"])

        benchmark_var: float = float(benchmark_returns.var())
        if benchmark_var == 0:
            return {"error": "Benchmark variance is zero \u2014 cannot compute Beta."}

        asset_betas: dict[str, float] = {}
        for col in portfolio_returns.columns:
            cov_val: float = float(portfolio_returns[col].cov(benchmark_returns))
            asset_betas[col] = round(cov_val / benchmark_var, 4)

        # Weighted portfolio Beta using current market-value weights
        portfolio_beta: float = sum(
            asset_betas.get(str(sym), 0) * w
            for sym, w in weights.items()
        )

        return {
            "portfolio_beta": round(portfolio_beta, 4),
            "asset_betas": asset_betas,
            "benchmark": "Nifty 50 (^NSEI)",
            "interpretation": (
                "For every 10% Nifty 50 move, this portfolio is expected to move "
                f"~{round(abs(portfolio_beta) * 10, 1)}%"
                f" {'in the same direction' if portfolio_beta > 0 else 'inversely'}."
            ),
        }
    except Exception as exc:
        logger.error("Beta calculation failed: %s", exc)
        return {"error": str(exc)}


async def calculate_portfolio_beta(
    prices_df: pd.DataFrame,
    weights: dict[str, float],
    period: str = "1y",
) -> dict[str, Any]:
    """Async wrapper for Beta calculation — runs in thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _sync_calculate_beta, prices_df, weights, period
    )
