"""
app/services/router.py

Hierarchical Scoring Router — maps investor psychology to the correct
quantitative model via a priority-based decision matrix that resolves
conflicting preference signals.

Decision hierarchy (evaluated top-to-bottom, first match wins):

  P0 — CONFLICT OVERRIDE
       High Diversification + Panic at 5% drop
       → HRP  (clustering prevents the corner-solution drawdowns the user fears)

  P1 — CAPITAL PROTECTION
       Panic at 5% drop (any diversification)
       → CVaR  (minimises α=0.05 tail risk directly)

  P2 — ADVANCED CUSTOM VIEWS
       Advanced experience level
       → Black-Litterman  (Bayesian blend of market prior + user view vector)

  P3 — PURE DIVERSIFICATION
       High diversification preference
       → HRP  (unsupervised ML clustering, equal risk contribution)

  P4 — DEFAULT
       → Markowitz Max-Sharpe  (classic mean-variance, appropriate for
         balanced/aggressive/focused profiles)

Each path also derives L2 regularisation strength (gamma) and a per-asset
weight cap (max_weight) so the optimiser itself gets mathematically
consistent constraints — not just a model switch.

Returns
-------
(result_dict, engine_name, routing_rationale)
  result_dict       — the raw output from the chosen optimiser function
  engine_name       — one of "hrp" | "cvar" | "black_litterman" | "markowitz"
  routing_rationale — a 1-2 sentence plain-English explanation of the decision
                      (displayed on the frontend as the engine explanation)
"""

import logging
from typing import Any

import pandas as pd

from app.schemas.user_preferences import UserPreferencesRead
from app.services import optimizer as optimizer_svc

logger = logging.getLogger(__name__)


# ── Preference value constants (must match InvestorProfileWizard.jsx) ─────────

_PANIC_DRAWDOWN   = "Panic at 5% drop (Protect my capital)"
_BALANCED_DD      = "Uncomfortable at 15% (Balanced)"
_AGGRESSIVE_DD    = "Can ignore 25%+ crashes (Aggressive)"

_HIGH_DIVERS      = "High (Maximum Spread)"
_STD_DIVERS       = "Standard"
_FOCUSED_DIVERS   = "Focused"

_ADVANCED_EXP     = "Advanced (I want to input custom views)"
_BEGINNER_EXP     = "Beginner (Do it for me)"

_HIGH_LIQ         = "High (Need cash soon)"
_LOW_LIQ          = "Low (Locked away)"


# ── Constraint derivation ─────────────────────────────────────────────────────

def _derive_constraints(prefs: UserPreferencesRead) -> dict[str, Any]:
    """
    Translate qualitative preferences into hard mathematical constraints
    that are applied to every model that accepts them (Markowitz, BL).

    gamma (L2 regularisation)
    ─────────────────────────
    Penalises portfolio concentration by adding γ·‖w‖² to the objective.
    Higher γ → more even spread.
      High diversification  → 0.20  (strict spread)
      Standard              → 0.10  (mild spread)
      Focused               → 0.00  (allow concentration)

    max_weight (per-asset cap)
    ──────────────────────────
    Hard upper bound on any single asset's weight.
      High diversification  → 0.15  (no asset dominates)
      Standard              → 0.40  (moderate cap)
      Focused               → 1.00  (unconstrained — let the solver decide)

    Liquidity adjustment
    ────────────────────
    High liquidity need tightens max_weight by 5 pp and adds a small γ bump
    to avoid illiquid concentrated positions.
    """
    div = prefs.diversification_preference
    liq = prefs.liquidity_needs

    gamma_map     = {_HIGH_DIVERS: 0.20, _STD_DIVERS: 0.10, _FOCUSED_DIVERS: 0.00}
    max_wt_map    = {_HIGH_DIVERS: 0.15, _STD_DIVERS: 0.40, _FOCUSED_DIVERS: 1.00}

    gamma     = gamma_map.get(div, 0.10)
    max_weight = max_wt_map.get(div, 0.40)

    # Liquidity tightening
    if liq == _HIGH_LIQ:
        max_weight = max(0.10, max_weight - 0.05)
        gamma      = min(0.25, gamma + 0.05)

    return {"gamma": round(gamma, 4), "max_weight": round(max_weight, 4)}


# ── Main router ───────────────────────────────────────────────────────────────

def route_portfolio_optimization(
    prefs: UserPreferencesRead,
    prices: pd.DataFrame,
    current_weights: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, str]:
    """
    Hierarchical Scoring Router.

    Parameters
    ----------
    prefs  : validated investor profile from the wizard
    prices : price-history DataFrame (dates × tickers)

    Returns
    -------
    (result_dict, engine_name, routing_rationale)
    """
    dd  = prefs.drawdown_tolerance
    div = prefs.diversification_preference
    exp = prefs.experience_level
    liq = prefs.liquidity_needs

    constraints = _derive_constraints(prefs)

    # ── P0: Conflict override — High Diversification AND Panic at 5% ─────────
    # The user wants maximum spread but also fears tail risk.  CVaR on its own
    # can still produce concentrated allocations in a low-vol single asset.
    # HRP solves both simultaneously: the dendrogram clustering forces spread
    # while the inverse-variance bisection controls tail exposure per cluster.
    if div == _HIGH_DIVERS and dd == _PANIC_DRAWDOWN:
        logger.info(
            "[Router P0] Conflict detected — High Diversification + Panic-drawdown. "
            "Routing to HRP (cluster-based risk parity resolves both simultaneously)."
        )
        result = optimizer_svc.run_hrp(prices, current_weights=current_weights)
        rationale = (
            "Your profile has a direct conflict: maximum diversification AND extreme "
            "downside protection. HRP (Hierarchical Risk Parity) is the only model that "
            "satisfies both simultaneously — it uses ML clustering to spread risk evenly "
            "across asset groups, preventing the concentrated positions that cause the "
            "sharp drawdowns you fear."
        )
        return result, "hrp", rationale

    # ── P1: Capital protection — Panic at 5% drop ────────────────────────────
    # CVaR directly minimises the α=0.05 conditional tail loss.
    if dd == _PANIC_DRAWDOWN:
        logger.info("[Router P1] Downside protection — routing to CVaR (α=0.05).")
        result = optimizer_svc.run_cvar(prices, current_weights=current_weights)
        rationale = (
            "You've indicated you panic at a 5% portfolio drop. "
            "The engine is using Conditional Value at Risk (CVaR) to mathematically "
            "minimise your worst-case tail losses at the 95th percentile — prioritising "
            "capital preservation over return maximisation."
        )
        return result, "cvar", rationale

    # ── P2: Advanced user with custom views ───────────────────────────────────
    # Black-Litterman requires a user view vector (Q matrix) which must be
    # supplied via the BL endpoint.  Return a sentinel so the caller knows
    # to prompt the user for views rather than using stale default views.
    if exp == _ADVANCED_EXP:
        logger.info("[Router P2] Advanced user — routing to Black-Litterman.")
        rationale = (
            "As an advanced investor, the engine uses Black-Litterman — a Bayesian model "
            "that blends the market equilibrium prior with your personal return forecasts "
            "to produce a posterior-optimal allocation. "
            "Submit your views via the Black-Litterman endpoint to run a full optimisation."
        )
        return {"advanced_views_required": True}, "black_litterman", rationale

    # ── P3: Pure diversification — no tail-risk conflict ─────────────────────
    if div == _HIGH_DIVERS:
        logger.info("[Router P3] High diversification — routing to HRP.")
        result = optimizer_svc.run_hrp(prices, current_weights=current_weights)
        rationale = (
            "You've prioritised maximum diversification. "
            "HRP (Hierarchical Risk Parity) uses unsupervised machine learning to cluster "
            "your assets by correlation, then allocates risk equally across clusters — "
            "delivering true diversification beyond simple weight spreading."
        )
        return result, "hrp", rationale

    # ── P4: Default — Markowitz Max-Sharpe with preference-derived constraints ─
    gamma      = constraints["gamma"]
    max_weight = constraints["max_weight"]
    logger.info(
        "[Router P4] Markowitz Max-Sharpe — gamma=%.2f, max_weight=%.2f.",
        gamma, max_weight,
    )

    # Choose objective label for rationale
    if div == _FOCUSED_DIVERS:
        focus_note = "concentrating the allocation in the highest-conviction positions"
    elif dd == _AGGRESSIVE_DD:
        focus_note = "accepting higher volatility in pursuit of maximum risk-adjusted return"
    else:
        focus_note = "balancing return and risk within a moderate spread"

    result = optimizer_svc.run_markowitz(
        prices=prices,
        objective="max_sharpe",
        long_only=True,
        max_weight=max_weight,
        gamma=gamma,
        current_weights=current_weights,
    )
    rationale = (
        f"Mean-Variance Optimisation (Markowitz) is maximising your Sharpe ratio — "
        f"{focus_note}. "
        f"L2 regularisation (γ={gamma}) and a {int(max_weight * 100)}% per-asset cap "
        f"are applied to match your diversification and liquidity preferences."
    )
    return result, "markowitz", rationale


# ── History period helper ─────────────────────────────────────────────────────

def get_history_period_for_horizon(time_horizon: str) -> str:
    """Maps qualitative time horizon to yfinance history period string."""
    if time_horizon == "1-3 Years":
        return "1y"
    elif time_horizon == "4-7 Years":
        return "3y"
    elif time_horizon == "8+ Years":
        return "5y"
    return "3y"
