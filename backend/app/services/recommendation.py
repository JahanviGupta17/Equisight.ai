"""
app/services/recommendation.py
Action Engine and Candidate Action Scoring for Phase 4.
"""
from typing import Dict, Any, Tuple
from app.models.recommendation import RecommendationAction
from app.services.llm import generate_explanation

# Transaction cost threshold: portfolios below this value (INR) get a Rebalance penalty
# because brokerage fees + STCG taxes make rebalancing unprofitable at small sizes.
SMALL_PORTFOLIO_THRESHOLD_INR = 100_000  # ₹1,00,000
REBALANCE_SMALL_PORTFOLIO_PENALTY = 0.20  # 20% score reduction


def score_action(
    drift_details: Dict[str, Any],
    portfolio_value: float = 0.0,
) -> Tuple[RecommendationAction, Dict[str, float]]:
    """
    Candidate Action Scoring: Evaluate whether to "Hold", "Rebalance", or "Review".
    Accounts for transaction cost viability based on portfolio size.
    Returns the chosen action and the scoring details.
    """
    drifts = drift_details.get("drifts", [])

    # Use relative_drift_pct if available (new format), fallback to absolute drift
    total_drift = sum([
        d.get("absolute_drift", d.get("drift", 0)) for d in drifts
    ])
    max_drift = max([
        d.get("absolute_drift", d.get("drift", 0)) for d in drifts
    ]) if drifts else 0

    scores = {
        "Hold": 1.0 - (total_drift * 5),
        "Rebalance": total_drift * 10,
        "Review": max_drift * 8
    }

    # ── Transaction Cost Penalty ─────────────────────────────────────────────
    # If the portfolio is too small, brokerage fees and STCG taxes will eat the
    # gains from rebalancing. Penalize the Rebalance score.
    if 0 < portfolio_value < SMALL_PORTFOLIO_THRESHOLD_INR:
        penalty = scores["Rebalance"] * REBALANCE_SMALL_PORTFOLIO_PENALTY
        scores["Rebalance"] -= penalty

    # Decide action
    best_action_str = max(scores, key=scores.get)
    action = RecommendationAction(best_action_str)

    return action, scores

async def generate_recommendation_data(
    portfolio_id: str,
    drift_details: Dict[str, Any],
    portfolio_value: float = 0.0,
    rag_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Orchestrates the Action Engine and LLM to produce a recommendation.
    rag_context: {"summary": str, "sources": [str]} from the RAG pipeline.
    """
    rag_context = rag_context or {}

    # 1. Candidate Action Scoring
    action, scores = score_action(drift_details, portfolio_value=portfolio_value)

    # 2. Proposed weights (revert drifted assets to targets)
    proposed_weights = {}
    if action == RecommendationAction.REBALANCE:
        drifts = drift_details.get("drifts", [])
        for d in drifts:
            proposed_weights[d["asset"]] = d["target_weight"]

    # 3. LLM — Gemini Pro with RAG-grounded context
    explanation, scenario = await generate_explanation(
        drift_details, action.value, proposed_weights, rag_context=rag_context
    )

    return {
        "portfolio_id": portfolio_id,
        "action": action,
        "candidate_scores": scores,
        "proposed_weights": proposed_weights,
        "explanation": explanation,
        "scenario_projection": scenario,
        "rag_sources": rag_context.get("sources", []),
        "transaction_cost_penalty_applied": 0 < portfolio_value < SMALL_PORTFOLIO_THRESHOLD_INR,
    }
