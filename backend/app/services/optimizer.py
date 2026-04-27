"""
app/services/optimizer.py
Quantitative engine — PyPortfolioOpt wrappers for:
  1. Markowitz Mean-Variance (max Sharpe / min vol / efficient frontier point)
  2. Black-Litterman (blended market prior + user views)

All yfinance calls are blocking; they run in a thread pool via
asyncio.run_in_executor so the event loop is never blocked.

Redis caching uses redis.asyncio (async client) so it NEVER blocks the
FastAPI event loop. The old redis.Redis (sync) was the primary cause of
the analysis pipeline hanging on cache reads/writes.
"""
import asyncio
import logging
from typing import Any
import pickle
import hashlib
import math

import numpy as np
import pandas as pd
import requests
import redis.asyncio as aioredis
import yfinance as yf
from pypfopt import (
    BlackLittermanModel,
    EfficientFrontier,
    expected_returns,
    risk_models,
)
from pypfopt.exceptions import OptimizationError
from app.core.config import settings

logger = logging.getLogger(__name__)

# Async Redis client — non-blocking, safe for use inside async functions.
# decode_responses=False because we store binary pickle data.
_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """Lazy singleton for the async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


# Default fallback
HISTORY_PERIOD = "3y"

# Risk-free rate proxy: RBI repo rate (update as needed)
RISK_FREE_RATE = 0.065

# Data integrity: assets missing more than 5% of data are patched via ffill, not dropped
DATA_INTEGRITY_THRESHOLD = 0.95  # require at least 95% valid rows


# ── MF Data Router — mfapi.in ────────────────────────────────────────────────

MFAPI_SEARCH_URL = "https://api.mfapi.in/mf/search"
MFAPI_FETCH_URL = "https://api.mfapi.in/mf/{scheme_code}"


def _fetch_mf_prices(symbol: str) -> pd.Series:
    """
    Fetches NAV history for an Indian Mutual Fund from mfapi.in.
    1. Searches for the scheme code by symbol name.
    2. Downloads full NAV history.
    3. Returns a tz-naive Pandas Series indexed by date (same format as yfinance).
    Returns an empty Series on failure.
    """
    try:
        # Step 1: Strip any broker-appended exchange suffixes before text search
        # e.g. "PPFAS.MF" → "PPFAS", "AXISELTM.BO" → "AXISELTM"
        search_term = symbol.split(".")[0].upper()

        # Known broker abbreviation → full fund name mappings to improve search
        BROKER_TO_FUND: dict[str, str] = {
            "PPFAS": "Parag Parikh Flexi Cap Fund",
            "MIRAE": "Mirae Asset Large Cap Fund",
            "AXIS": "Axis Bluechip Fund",
            "HDFC": "HDFC Top 100 Fund",
            "SBI": "SBI Bluechip Fund",
            "ICICI": "ICICI Prudential Bluechip Fund",
            "NIPPON": "Nippon India Large Cap Fund",
        }
        q = BROKER_TO_FUND.get(search_term, search_term)

        search_resp = requests.get(
            MFAPI_SEARCH_URL,
            params={"q": q},
            timeout=10,
        )
        search_resp.raise_for_status()
        results = search_resp.json()
        if not results:
            logger.warning("mfapi.in: No scheme found for '%s' (searched: '%s')", symbol, q)
            return pd.Series(dtype=float, name=symbol)

        scheme_code = results[0]["schemeCode"]
        logger.info("mfapi.in: '%s' → '%s' matched schemeCode %s", symbol, q, scheme_code)

        # Step 2: Fetch full NAV history
        nav_resp = requests.get(
            MFAPI_FETCH_URL.format(scheme_code=scheme_code),
            timeout=15,
        )
        nav_resp.raise_for_status()
        nav_data = nav_resp.json().get("data", [])

        if not nav_data:
            logger.warning("mfapi.in: No NAV data returned for schemeCode %s", scheme_code)
            return pd.Series(dtype=float, name=symbol)

        # Step 3: Parse and align — mfapi returns newest first, format: "DD-MM-YYYY"
        dates = pd.to_datetime([d["date"] for d in nav_data], format="%d-%m-%Y", dayfirst=True)
        navs = pd.to_numeric([d["nav"] for d in nav_data], errors="coerce")

        series = pd.Series(navs, index=dates, name=symbol)
        series = series.sort_index(ascending=True)  # oldest → newest, like yfinance
        series.index = series.index.tz_localize(None)  # ensure tz-naive, matching yfinance

        return series

    except requests.exceptions.RequestException as exc:
        logger.error("mfapi.in request failed for '%s': %s", symbol, exc)
        return pd.Series(dtype=float, name=symbol)
    except Exception as exc:
        logger.error("Unexpected error fetching MF data for '%s': %s", symbol, exc)
        return pd.Series(dtype=float, name=symbol)


# ── Historical Price Fetcher (Data Router) ───────────────────────────────────

def _sync_fetch_prices(
    symbols: list[str],
    asset_types: dict[str, str] | None = None,
    history_period: str = "3y",
) -> pd.DataFrame:
    """
    Data Router:
    - Equity / ETF → yfinance
    - MutualFund   → mfapi.in
    Merges all price series into one aligned DataFrame, then applies
    the 95% data integrity filter and forward-fills remaining gaps.
    """
    asset_types = asset_types or {}

    equity_symbols = [s for s in symbols if asset_types.get(s, "Stock") != "MutualFund"]
    mf_symbols = [s for s in symbols if asset_types.get(s) == "MutualFund"]

    # ── Equity / ETF via yfinance ────────────────────────────────────────────
    price_frames: list[pd.DataFrame] = []

    if equity_symbols:
        try:
            raw = yf.download(
                tickers=equity_symbols,
                period=history_period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if not raw.empty:
                if len(equity_symbols) == 1:
                    eq_prices = raw[["Close"]].copy()
                    eq_prices.columns = [equity_symbols[0]]
                else:
                    eq_prices = raw["Close"].copy()

                eq_prices.index = pd.to_datetime(eq_prices.index).tz_localize(None)
                price_frames.append(eq_prices)
        except Exception as exc:
            logger.error("yfinance fetch error for equities: %s", exc)

    # ── Mutual Funds via mfapi.in ────────────────────────────────────────────
    for mf_sym in mf_symbols:
        mf_series = _fetch_mf_prices(mf_sym)
        if not mf_series.empty:
            # Slice to the same history_period window as yfinance
            cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(
                years=int(history_period.replace("y", ""))
            )
            mf_series = mf_series[mf_series.index >= cutoff]
            price_frames.append(mf_series.to_frame())

    if not price_frames:
        logger.warning("No price data fetched for any asset.")
        return pd.DataFrame()

    # ── Merge all frames on date index, align to shared trading days ─────────
    prices = price_frames[0]
    for frame in price_frames[1:]:
        prices = prices.join(frame, how="outer")

    # Apply data integrity filter (95% valid rows required)
    min_valid = int(len(prices) * DATA_INTEGRITY_THRESHOLD)
    prices = prices.dropna(thresh=min_valid, axis=1)
    prices = prices.ffill()   # patch gaps with last known price
    prices = prices.dropna()  # drop leading rows still NaN after ffill

    logger.info(
        "Price matrix after data-router + integrity filter: %d assets, %d days",
        prices.shape[1], prices.shape[0],
    )
    return prices


async def fetch_historical_prices(
    symbols: list[str],
    asset_types: dict[str, str] | None = None,
    history_period: str = "3y",
) -> pd.DataFrame:
    """Async wrapper — dispatches data-router to thread pool with a 90-second timeout.
    Implements Redis caching with 12-hour TTL.
    
    Uses the async Redis client (redis.asyncio) so cache reads/writes
    never block the FastAPI event loop.
    """
    if not symbols:
        return pd.DataFrame()

    # Generate a unique cache key based on the sorted symbols + history_period
    cache_key = f"prices_{history_period}_" + hashlib.md5(",".join(sorted(symbols)).encode()).hexdigest()
    rc = _get_redis()

    # 1. Try to fetch from Redis (non-blocking await)
    try:
        cached_data = await rc.get(cache_key)
        if cached_data:
            df = pickle.loads(cached_data)
            logger.info("Cache HIT: Loaded price history for %d assets from Redis", df.shape[1])
            return df
    except Exception as exc:
        logger.warning("Redis cache read failed (continuing without cache): %s", exc)

    # 2. Cache Miss: Fetch using thread pool
    logger.info("Cache MISS: Fetching price history from sources...")
    loop = asyncio.get_running_loop()  # get_running_loop() is correct inside async context
    df = await asyncio.wait_for(
        loop.run_in_executor(
            None,
            lambda: _sync_fetch_prices(symbols, asset_types, history_period),
        ),
        timeout=90,
    )

    # 3. Save to Redis with 12-hour TTL (non-blocking await)
    if not df.empty:
        try:
            await rc.setex(cache_key, 43200, pickle.dumps(df))
            logger.info("Saved price history to Redis cache (TTL: 12h)")
        except Exception as exc:
            logger.warning("Redis cache write failed (continuing without cache): %s", exc)

    return df


# ── Shared helpers ───────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float:
    """Coerce optimizer output to a finite float, returning 0.0 on failure."""
    try:
        f = float(v)
        return 0.0 if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return 0.0


def _current_sharpe(
    current_weights: dict[str, float],
    prices: pd.DataFrame,
) -> float:
    """
    Compute the Sharpe ratio of the *current* portfolio given its weights
    and the historical price matrix.  Returns 0.0 on any failure.
    """
    try:
        aligned = {k: v for k, v in current_weights.items() if k in prices.columns}
        if not aligned:
            return 0.0
        w = np.array([aligned.get(c, 0.0) for c in prices.columns])
        w_sum = w.sum()
        if w_sum <= 0:
            return 0.0
        w = w / w_sum                                    # normalise to 1

        rets = prices.pct_change().dropna()
        port_ret = (rets * w).sum(axis=1)
        ann_ret  = port_ret.mean() * 252
        ann_vol  = port_ret.std()  * math.sqrt(252)
        if ann_vol == 0:
            return 0.0
        return (ann_ret - RISK_FREE_RATE) / ann_vol
    except Exception:
        return 0.0


# Minimum Sharpe improvement required to justify rebalancing.
# Below this threshold the engine returns current weights ("Do Not Trade").
SHARPE_IMPROVEMENT_THRESHOLD = 0.05

# Transaction cost rate used in the friction objective (1% round-trip).
TRANSACTION_COST_RATE = 0.01


# ── Markowitz Optimizer ──────────────────────────────────────────────────────

def run_markowitz(
    prices: pd.DataFrame,
    objective: str = "max_sharpe",
    target_return: float | None = None,
    target_risk: float | None = None,
    long_only: bool = True,
    # ── Preference-derived constraints (from router) ───────────────────────
    max_weight: float = 1.0,      # per-asset cap  (0.15 = high divers, 1.0 = unconstrained)
    gamma: float = 0.0,           # L2 regularisation  (0.20 = strict, 0.00 = none)
    # ── Real-world friction ────────────────────────────────────────────────
    current_weights: dict[str, float] | None = None,  # live portfolio weights
) -> dict[str, Any]:
    """
    Mean-Variance Optimization via PyPortfolioOpt with real-world friction.

    Two layers of friction are applied when current_weights are supplied:

    1. Transaction-cost objective  (PyPortfolioOpt objective_functions)
       Adds k * sum(|w_i - w_prev_i|) to the objective so the solver penalises
       turnover at 1% round-trip cost per unit of weight moved.

    2. L2 regularisation  (gamma > 0)
       Adds γ·‖w‖² to penalise concentration independently of turnover.

    After solving, a "Do Not Trade" gate checks whether the proposed Sharpe
    exceeds the current portfolio Sharpe by at least SHARPE_IMPROVEMENT_THRESHOLD
    (0.05).  If not, the current weights are returned unchanged so no noisy
    micro-trades are triggered.

    Fallback chain on infeasibility:
       constrained solve  →  vanilla max_sharpe  →  raise
    """
    if prices.empty or prices.shape[1] < 2:
        raise ValueError(
            "At least 2 assets with valid price history are required for optimization."
        )

    from pypfopt import objective_functions

    n_assets = prices.shape[1]
    # Prevent an infeasible problem: max_weight must be >= 1/n
    safe_max = max(max_weight, round(1.0 / n_assets + 0.01, 4))
    weight_bounds = (0, safe_max) if long_only else (-1, safe_max)

    mu = expected_returns.mean_historical_return(prices)
    S  = risk_models.sample_cov(prices)

    def _solve(apply_friction: bool) -> tuple[dict, tuple]:
        ef = EfficientFrontier(mu, S, weight_bounds=weight_bounds)

        # L2 regularisation — penalises concentration
        if gamma > 0:
            ef.add_objective(objective_functions.L2_reg, gamma=gamma)

        # Transaction-cost objective — penalises turnover
        if apply_friction and current_weights:
            # Align prev weights to price-matrix column order; zero-fill new assets
            w_prev = np.array(
                [current_weights.get(c, 0.0) for c in prices.columns],
                dtype=float,
            )
            w_prev_sum = w_prev.sum()
            if w_prev_sum > 0:
                w_prev /= w_prev_sum   # normalise to 1
            ef.add_objective(
                objective_functions.transaction_cost,
                w_prev=w_prev,
                k=TRANSACTION_COST_RATE,
            )

        if objective == "min_volatility":
            ef.min_volatility()
        elif objective == "efficient_return":
            if target_return is None:
                raise ValueError("target_return required for objective='efficient_return'.")
            ef.efficient_return(target_return=target_return)
        elif objective == "efficient_risk":
            if target_risk is None:
                raise ValueError("target_risk required for objective='efficient_risk'.")
            ef.efficient_risk(target_volatility=target_risk)
        else:
            ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)

        w = ef.clean_weights()
        p = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=False)
        return w, p

    # ── Attempt 1: full constraints + friction ────────────────────────────────
    try:
        weights, perf = _solve(apply_friction=True)
    except (OptimizationError, Exception) as exc:
        logger.warning(
            "Markowitz constrained solve failed (%s) — retrying without friction.", exc
        )
        # ── Attempt 2: constraints only, no transaction cost ─────────────────
        try:
            weights, perf = _solve(apply_friction=False)
        except (OptimizationError, Exception) as exc2:
            logger.warning(
                "Markowitz fallback also failed (%s) — raising to caller.", exc2
            )
            raise

    proposed_sharpe = _safe_float(perf[2])

    # ── Do-Not-Trade gate ─────────────────────────────────────────────────────
    # If the improvement over the current portfolio is below threshold, the
    # marginal benefit does not justify transaction costs — return current weights.
    if current_weights and objective == "max_sharpe":
        current_sharpe = _current_sharpe(current_weights, prices)
        improvement    = proposed_sharpe - current_sharpe
        if improvement < SHARPE_IMPROVEMENT_THRESHOLD:
            logger.info(
                "Do-Not-Trade: proposed Sharpe %.4f vs current %.4f (delta=%.4f < %.2f). "
                "Returning current weights.",
                proposed_sharpe, current_sharpe, improvement, SHARPE_IMPROVEMENT_THRESHOLD,
            )
            # Align current_weights to price-matrix tickers
            aligned_cw = {c: round(current_weights.get(c, 0.0), 6) for c in prices.columns}
            return {
                "weights": aligned_cw,
                "expected_annual_return": round(_safe_float(perf[0]), 4),
                "annual_volatility":      round(_safe_float(perf[1]), 4),
                "sharpe_ratio":           round(current_sharpe, 4),
                "objective": objective,
                "do_not_trade": True,
                "constraints_applied": {
                    "max_weight": safe_max,
                    "gamma": gamma,
                    "transaction_cost": TRANSACTION_COST_RATE,
                    "reason": f"Sharpe improvement {improvement:.4f} < threshold {SHARPE_IMPROVEMENT_THRESHOLD}",
                },
            }

    return {
        "weights": {k: round(v, 6) for k, v in weights.items()},
        "expected_annual_return": round(_safe_float(perf[0]), 4),
        "annual_volatility":      round(_safe_float(perf[1]), 4),
        "sharpe_ratio":           round(proposed_sharpe, 4),
        "objective": objective,
        "do_not_trade": False,
        "constraints_applied": {
            "max_weight": safe_max,
            "gamma": gamma,
            "transaction_cost": TRANSACTION_COST_RATE if current_weights else 0.0,
        },
    }


# ── Black-Litterman Optimizer ────────────────────────────────────────────────

def run_black_litterman(
    prices: pd.DataFrame,
    views: dict[str, float],
    market_weights: dict[str, float] | None = None,
    current_weights: dict[str, float] | None = None,
    gamma: float = 0.0,
) -> dict[str, Any]:
    """
    Black-Litterman Optimization via PyPortfolioOpt with real-world friction.

    views: {ticker: expected_annual_return}
      e.g. {"BEL.NS": 0.18, "NTPC.NS": 0.12}

    market_weights: prior distribution {ticker: weight}.
      Defaults to equal weights if not supplied.

    current_weights: live portfolio weights for transaction-cost objective
      and Do-Not-Trade gate.  Omit to run unconstrained.

    gamma: L2 regularisation strength (0 = none, 0.20 = strict spread).

    Friction layers (same as Markowitz):
      1. L2 regularisation — penalises concentration in posterior weights.
      2. Transaction-cost objective — penalises turnover at 1% round-trip.
      3. Do-Not-Trade gate — returns current weights when Sharpe delta < 0.05.

    Fallback: if friction makes the problem infeasible, retries without
    transaction cost; if that also fails, raises to caller.
    """
    from pypfopt import objective_functions

    if prices.empty or prices.shape[1] < 2:
        raise ValueError(
            "At least 2 assets with valid price history are required for optimization."
        )

    valid_views = {k: v for k, v in views.items() if k in prices.columns}
    if not valid_views:
        raise ValueError(
            f"None of the view tickers {list(views.keys())} are present in the portfolio's "
            "price data. Ensure tickers match exactly (e.g. BEL.NS, not BEL)."
        )

    S = risk_models.sample_cov(prices)

    n = len(prices.columns)
    prior = {sym: market_weights.get(sym, 1 / n) for sym in prices.columns} if market_weights \
            else {sym: 1 / n for sym in prices.columns}
    total_w = sum(prior.values())
    prior = {k: v / total_w for k, v in prior.items()}

    bl = BlackLittermanModel(S, pi="market", market_weights=prior, absolute_views=valid_views)
    bl_returns = bl.bl_returns()
    bl_cov     = bl.bl_cov()

    def _solve_bl(apply_friction: bool) -> tuple[dict, tuple]:
        ef = EfficientFrontier(bl_returns, bl_cov)

        if gamma > 0:
            ef.add_objective(objective_functions.L2_reg, gamma=gamma)

        if apply_friction and current_weights:
            w_prev = np.array(
                [current_weights.get(c, 0.0) for c in prices.columns], dtype=float
            )
            w_sum = w_prev.sum()
            if w_sum > 0:
                w_prev /= w_sum
            ef.add_objective(
                objective_functions.transaction_cost,
                w_prev=w_prev,
                k=TRANSACTION_COST_RATE,
            )

        ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)
        w = ef.clean_weights()
        p = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=False)
        return w, p

    try:
        weights, perf = _solve_bl(apply_friction=True)
    except (OptimizationError, Exception) as exc:
        logger.warning("BL constrained solve failed (%s) — retrying without friction.", exc)
        try:
            weights, perf = _solve_bl(apply_friction=False)
        except (OptimizationError, Exception) as exc2:
            logger.warning("BL fallback also failed (%s) — raising.", exc2)
            raise

    proposed_sharpe = _safe_float(perf[2])

    # Do-Not-Trade gate
    if current_weights:
        current_sharpe = _current_sharpe(current_weights, prices)
        improvement    = proposed_sharpe - current_sharpe
        if improvement < SHARPE_IMPROVEMENT_THRESHOLD:
            logger.info(
                "Do-Not-Trade (BL): Sharpe delta=%.4f < %.2f. Returning current weights.",
                improvement, SHARPE_IMPROVEMENT_THRESHOLD,
            )
            aligned_cw = {c: round(current_weights.get(c, 0.0), 6) for c in prices.columns}
            return {
                "weights": aligned_cw,
                "expected_annual_return": round(_safe_float(perf[0]), 4),
                "annual_volatility":      round(_safe_float(perf[1]), 4),
                "sharpe_ratio":           round(current_sharpe, 4),
                "bl_posterior_returns":   {k: round(_safe_float(v), 4) for k, v in bl_returns.items()},
                "views_applied": valid_views,
                "prior": "market" if market_weights else "equal_weight",
                "do_not_trade": True,
                "constraints_applied": {
                    "gamma": gamma,
                    "transaction_cost": TRANSACTION_COST_RATE,
                    "reason": f"Sharpe improvement {improvement:.4f} < threshold {SHARPE_IMPROVEMENT_THRESHOLD}",
                },
            }

    return {
        "weights": {k: round(v, 6) for k, v in weights.items()},
        "expected_annual_return": round(_safe_float(perf[0]), 4),
        "annual_volatility":      round(_safe_float(perf[1]), 4),
        "sharpe_ratio":           round(proposed_sharpe, 4),
        "bl_posterior_returns":   {k: round(_safe_float(v), 4) for k, v in bl_returns.items()},
        "views_applied": valid_views,
        "prior": "market" if market_weights else "equal_weight",
        "do_not_trade": False,
        "constraints_applied": {
            "gamma": gamma,
            "transaction_cost": TRANSACTION_COST_RATE if current_weights else 0.0,
        },
    }


# ── CVaR Optimizer ───────────────────────────────────────────────────────────

def run_cvar(
    prices: pd.DataFrame,
    current_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Conditional Value at Risk (CVaR) optimization — minimises α=0.05 tail loss.

    EfficientCVaR does not support add_objective, so L2 / transaction-cost
    objectives are not applicable here.  The Do-Not-Trade gate is still applied:
    if the CVaR-optimal portfolio does not improve the current Sharpe by at
    least SHARPE_IMPROVEMENT_THRESHOLD, current weights are returned unchanged.

    Note: portfolio_performance on EfficientCVaR returns (expected_return, CVaR)
    not (return, volatility, sharpe).  annual_volatility is therefore not
    available from this model and is reported as None.
    """
    from pypfopt import EfficientCVaR

    if prices.empty or prices.shape[1] < 2:
        raise ValueError("At least 2 assets required for optimization.")

    mu      = expected_returns.mean_historical_return(prices)
    returns = prices.pct_change().dropna()

    ec = EfficientCVaR(mu, returns)
    ec.min_cvar()
    weights = ec.clean_weights()
    perf    = ec.portfolio_performance(verbose=False)   # (expected_return, CVaR)

    proposed_ret  = _safe_float(perf[0])
    proposed_cvar = _safe_float(perf[1])

    # Estimate Sharpe of proposed portfolio (CVaR solver doesn't give vol directly)
    proposed_sharpe = _current_sharpe(weights, prices)

    # Do-Not-Trade gate
    if current_weights:
        current_sharpe = _current_sharpe(current_weights, prices)
        improvement    = proposed_sharpe - current_sharpe
        if improvement < SHARPE_IMPROVEMENT_THRESHOLD:
            logger.info(
                "Do-Not-Trade (CVaR): Sharpe delta=%.4f < %.2f. Returning current weights.",
                improvement, SHARPE_IMPROVEMENT_THRESHOLD,
            )
            aligned_cw = {c: round(current_weights.get(c, 0.0), 6) for c in prices.columns}
            return {
                "weights": aligned_cw,
                "expected_annual_return": proposed_ret,
                "annual_volatility": None,
                "annual_cvar": proposed_cvar,
                "sharpe_ratio": round(current_sharpe, 4),
                "objective": "min_cvar",
                "do_not_trade": True,
                "constraints_applied": {
                    "cvar": True,
                    "reason": f"Sharpe improvement {improvement:.4f} < threshold {SHARPE_IMPROVEMENT_THRESHOLD}",
                },
            }

    return {
        "weights": {k: round(v, 6) for k, v in weights.items()},
        "expected_annual_return": round(proposed_ret, 4),
        "annual_volatility": None,
        "annual_cvar": round(proposed_cvar, 4),
        "sharpe_ratio": round(proposed_sharpe, 4),
        "objective": "min_cvar",
        "do_not_trade": False,
        "constraints_applied": {"cvar": True},
    }


# ── HRP Optimizer ────────────────────────────────────────────────────────────

def run_hrp(
    prices: pd.DataFrame,
    current_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Hierarchical Risk Parity (HRP) optimization.

    HRPOpt does not support add_objective, so L2 / transaction-cost objectives
    are not applicable.  The Do-Not-Trade gate is still applied.
    """
    from pypfopt import HRPOpt

    if prices.empty or prices.shape[1] < 2:
        raise ValueError("At least 2 assets required for optimization.")

    returns = prices.pct_change().dropna()

    hrp     = HRPOpt(returns)
    hrp.optimize()
    weights = hrp.clean_weights()
    perf    = hrp.portfolio_performance(risk_free_rate=RISK_FREE_RATE, verbose=False)

    proposed_sharpe = _safe_float(perf[2])

    # Do-Not-Trade gate
    if current_weights:
        current_sharpe = _current_sharpe(current_weights, prices)
        improvement    = proposed_sharpe - current_sharpe
        if improvement < SHARPE_IMPROVEMENT_THRESHOLD:
            logger.info(
                "Do-Not-Trade (HRP): Sharpe delta=%.4f < %.2f. Returning current weights.",
                improvement, SHARPE_IMPROVEMENT_THRESHOLD,
            )
            aligned_cw = {c: round(current_weights.get(c, 0.0), 6) for c in prices.columns}
            return {
                "weights": aligned_cw,
                "expected_annual_return": round(_safe_float(perf[0]), 4),
                "annual_volatility":      round(_safe_float(perf[1]), 4),
                "sharpe_ratio":           round(current_sharpe, 4),
                "objective": "hrp",
                "do_not_trade": True,
                "constraints_applied": {
                    "hrp": True,
                    "reason": f"Sharpe improvement {improvement:.4f} < threshold {SHARPE_IMPROVEMENT_THRESHOLD}",
                },
            }

    return {
        "weights": {k: round(v, 6) for k, v in weights.items()},
        "expected_annual_return": round(_safe_float(perf[0]), 4),
        "annual_volatility":      round(_safe_float(perf[1]), 4),
        "sharpe_ratio":           round(proposed_sharpe, 4),
        "objective": "hrp",
        "do_not_trade": False,
        "constraints_applied": {"hrp": True},
    }

