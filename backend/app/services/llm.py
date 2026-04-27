"""
app/services/llm.py
Integration with Gemini API using google-genai library.
"""
from google import genai
from google.genai import types
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def get_gemini_client():
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Using dummy LLM response.")
        return None
    return genai.Client(api_key=settings.GEMINI_API_KEY)

async def generate_explanation(
    drift_data: dict,
    action: str,
    proposed_weights: dict,
    rag_context: dict | None = None,
) -> tuple[str, str]:
    """
    Calls Gemini Pro to generate a fiduciary-grade plain-language explanation.
    Uses rag_context (pre-summarized by Flash) as grounding evidence.
    Returns:
        tuple (explanation, scenario_projection)
    """
    client = get_gemini_client()
    rag_context = rag_context or {}
    news_section = ""
    if rag_context.get("summary"):
        news_section = f"\n\nRelevant Market Intelligence (retrieved from live news):\n{rag_context['summary']}"

    prompt = f"""You are an expert AI financial advisor for the Equisight platform, serving Indian retail investors.
A portfolio drift event has occurred. Write a clear, human-friendly advisory note.

Data:
- Action Decided: {action}
- Drift Event Details: {drift_data}
- Proposed New Weights (if rebalancing): {proposed_weights}{news_section}

Rules:
- Write in plain sentences. No markdown, no bullet points, no headers, no asterisks, no hash symbols.
- Keep it short: 3-4 sentences per section maximum.
- Reference specific assets and numbers where relevant.
- Avoid jargon. If market intelligence is provided, mention it naturally in one sentence.

Respond in exactly two sections separated by "---":
Section 1 (Explanation): What changed, why it matters, and what to do now. 3-4 sentences.
Section 2 (Scenario Projection): What may happen if this recommendation is ignored. 2-3 sentences.
"""

    if not client:
        return (
            "Your portfolio has drifted significantly from its target allocation due to recent market movements. "
            "We recommend reviewing or rebalancing to maintain your desired risk profile.",
            "Ignoring this could expose you to higher volatility or concentrated sector risk."
        )

    try:
        # Gemini Pro: heavyweight model for fiduciary-grade final advisory
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )

        text = response.text
        parts = text.split("---")
        explanation = parts[0].strip() if len(parts) > 0 else text
        scenario = parts[1].strip() if len(parts) > 1 else "No scenario projection available."
        return explanation, scenario

    except Exception as e:
        logger.error("Failed to generate LLM explanation: %s", e)
        return (
            "An error occurred while generating your advisory note. Please review your portfolio drift manually.",
            "Without rebalancing, your portfolio may no longer align with your original risk tolerance.",
        )

async def extract_holdings_from_text(raw_text: str) -> list[dict]:
    """
    Uses Gemini to intelligently extract holdings from an unstructured string
    (like a parsed PDF, raw TXT, or headerless CSV).
    Returns a list of dicts: [{"asset_symbol": str, "asset_type": str, "quantity": float, "average_buy_price": float}]
    """
    client = get_gemini_client()
    if not client:
        raise Exception("GEMINI_API_KEY is missing. Smart upload requires the LLM service.")

    prompt = f"""
    You are an expert financial data parser. I have raw text extracted from a user's portfolio upload document (it could be a CSV, PDF, or text file).
    Extract all the financial holdings mentioned and normalize them into a structured JSON list of objects.
    
    Each object must have exactly these keys:
    - "asset_symbol": The ticker symbol. Normalize this to Yahoo Finance standard (e.g. if the user says "HDFC", use "HDFCBANK.NS" or "HDFC.NS" if it's Indian, or standard US ticker). If you cannot be certain, make your best guess.
    - "asset_type": MUST BE EXACTLY ONE OF: "Stock", "ETF", or "MutualFund" (Case sensitive). Do not use any other value.
    - "quantity": A float representing the number of shares/units held.
    - "average_buy_price": A float representing the average purchase price per unit.

    Return ONLY raw JSON. No markdown formatting, no backticks, just the array of JSON objects.
    
    Raw Text:
    {raw_text}
    """

    import asyncio
    import json

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )

            text = response.text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]

            holdings = json.loads(text.strip())
            return holdings
        except Exception as e:
            last_exc = e
            err_str = str(e)
            if '503' in err_str or 'UNAVAILABLE' in err_str or 'quota' in err_str.lower():
                wait = 5 * (attempt + 1)
                logger.warning("Gemini 503/quota on attempt %d, retrying in %ds: %s", attempt + 1, wait, e)
                await asyncio.sleep(wait)
                continue
            logger.error("Failed to extract holdings via LLM: %s", e)
            raise e

    logger.error("Gemini unavailable after 3 attempts: %s", last_exc)
    raise last_exc

