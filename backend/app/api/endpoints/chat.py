"""
app/api/endpoints/chat.py
Conversational AI advisor — full context engineering.

POST /api/v1/chat/ingest  — upload a document into the RAG vector store
POST /api/v1/chat/ask     — multi-turn chat with portfolio + RAG + history
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models.holding import Holding
from app.services.rag import ingest_article

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Ingest document ──────────────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_document(file: UploadFile = File(...)):
    """Parse an uploaded PDF, TXT, or CSV and index it into Qdrant."""
    content_bytes = await file.read()
    filename = file.filename or "uploaded_file"

    if filename.lower().endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content_bytes))
            text_parts = [page.extract_text() or "" for page in reader.pages]
            raw_text = "\n\n".join(t for t in text_parts if t.strip())
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"PDF extraction failed: {exc}")
    else:
        raw_text = content_bytes.decode("utf-8", errors="replace")

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the file.")

    chunks = await ingest_article(raw_text, source_url=f"uploaded://{filename}")
    return {"status": "ok", "filename": filename, "chunks": chunks}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    portfolio_id: str | None = None
    include_portfolio_context: bool = True
    # Conversation history — last N turns sent by the frontend
    history: list[ChatMessage] = []
    # Full snapshots from the frontend Zustand store (avoids extra DB calls)
    analytics_snapshot: dict | None = None
    optimization_snapshot: dict | None = None


# ── Context builder ───────────────────────────────────────────────────────────

def _build_portfolio_context(
    holdings: list[Holding],
    analytics: dict | None,
    optimization: dict | None,
) -> str:
    """Build a rich, structured portfolio context string for the LLM."""
    sections: list[str] = []

    # --- Holdings from DB ---
    if holdings:
        rows = [
            f"  • {h.asset_symbol} ({h.asset_type}): "
            f"{h.quantity} units @ avg ₹{h.average_buy_price:.2f}"
            for h in holdings
        ]
        sections.append("=== CURRENT PORTFOLIO HOLDINGS ===\n" + "\n".join(rows))

    # --- Analytics snapshot ---
    if analytics:
        lines = ["=== PORTFOLIO ANALYTICS ==="]
        total_val = analytics.get("total_portfolio_value", 0)
        if total_val:
            lines.append(f"  Total Portfolio Value: ₹{total_val:,.2f}")

        summary = analytics.get("portfolio_summary") or {}
        if summary:
            lines.append(
                f"  Total Absolute Return: ₹{summary.get('total_absolute_return_inr', 0):,.2f}"
            )
            lines.append(
                f"  Total % Return: {summary.get('total_percentage_return', 0):.2f}%"
            )

        beta = analytics.get("portfolio_beta") or {}
        if beta:
            lines.append(f"  Portfolio Beta vs Nifty 50: {beta.get('portfolio_beta', 'N/A')}")
            if beta.get("interpretation"):
                lines.append(f"  Beta Interpretation: {beta['interpretation']}")

        abs_returns = analytics.get("absolute_returns") or {}
        if abs_returns:
            lines.append("  Per-Asset Performance:")
            for sym, r in abs_returns.items():
                lines.append(
                    f"    - {sym}: Price ₹{r.get('current_price', 0):.2f} | "
                    f"Return {r.get('percentage_return', 0):.2f}% "
                    f"(₹{r.get('absolute_return_inr', 0):,.2f})"
                )

        vol = analytics.get("rolling_volatility_30d") or {}
        if vol:
            lines.append("  30-Day Rolling Volatility:")
            for sym, v in vol.items():
                lines.append(f"    - {sym}: {float(v) * 100:.2f}%")

        drawdown = analytics.get("max_drawdown_pct") or {}
        if drawdown:
            lines.append("  Maximum Drawdown:")
            for sym, d in drawdown.items():
                lines.append(f"    - {sym}: {float(d) * 100:.2f}%")

        sections.append("\n".join(lines))

    # --- Optimization snapshot ---
    if optimization:
        lines = ["=== OPTIMIZATION RESULTS ==="]
        model = optimization.get("model", "unknown")
        lines.append(f"  Model: {model.replace('_', ' ').title()}")
        ear = optimization.get("expected_annual_return")
        av  = optimization.get("annual_volatility")
        sr  = optimization.get("sharpe_ratio")
        if ear is not None:
            lines.append(f"  Expected Annual Return: {float(ear) * 100:.2f}%")
        if av is not None:
            lines.append(f"  Annual Volatility: {float(av) * 100:.2f}%")
        if sr is not None:
            lines.append(f"  Sharpe Ratio: {float(sr):.3f}")
        weights = optimization.get("weights") or {}
        if weights:
            sorted_w = sorted(weights.items(), key=lambda x: -float(x[1]))
            lines.append("  Recommended Target Weights:")
            for sym, w in sorted_w:
                lines.append(f"    - {sym}: {float(w) * 100:.2f}%")
        if optimization.get("engine_explanation"):
            lines.append(f"  Engine Note: {optimization['engine_explanation']}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Equisight AI — a knowledgeable, empathetic financial advisor \
specializing in Indian equities, ETFs, and mutual funds for retail investors.

Your expertise covers portfolio performance analysis, optimization, rebalancing, and market intelligence.

Core rules:
1. Always ground answers in the provided portfolio data. Reference specific assets and exact figures.
2. Never fabricate numbers — if data is unavailable, say so clearly.
3. Use INR (₹) and Indian financial conventions (Lakhs, Crores) throughout.
4. Be concise unless the user asks for a detailed breakdown.
5. Maintain conversation continuity — refer to earlier exchanges when helpful.
6. If asked about something outside portfolio finance, politely redirect.
7. When optimization data is present, proactively connect it to the user's question.

FORMATTING RULES — strictly follow these:
- Write in plain flowing prose. No markdown whatsoever.
- No headers (no # or ##), no bullet points (no - or *), no bold markers (no **), no numbered lists.
- Use short paragraphs separated by a blank line if you need structure.
- For lists of items, write them inline with commas: "Your top holdings are RELIANCE.NS, TCS.NS, and HDFCBANK.NS."
- Numbers and figures are fine inline: "Your Sharpe ratio is 0.42, which means..."
- Keep responses conversational and to the point."""


# ── Ask endpoint ──────────────────────────────────────────────────────────────

@router.post("/ask")
async def ask(payload: ChatRequest, session: AsyncSession = Depends(get_db)):
    """
    Multi-turn portfolio AI advisor.

    Context engineering pipeline:
      1. RAG retrieval (Qdrant) — relevant doc chunks for this question
      2. Portfolio holdings from DB
      3. Rich analytics + optimization snapshots from the frontend store
      4. Last ≤10 conversation turns for memory
      5. Gemini with system instruction + structured multi-turn contents
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="LLM service not configured (GEMINI_API_KEY missing).",
        )

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    # ── 1. RAG retrieval ──────────────────────────────────────────────────────
    from app.services.rag import _embed, _get_qdrant, COLLECTION_NAME

    rag_chunks: list[str] = []
    rag_sources: list[str] = []
    try:
        embedding = await _embed(question)
        if embedding is not None:
            qclient = _get_qdrant()
            result = qclient.query_points(
                collection_name=COLLECTION_NAME,
                query=embedding,
                limit=4,
                with_payload=True,
            )
            for hit in result.points:
                if hit.payload:
                    chunk = hit.payload.get("content", "")
                    if chunk:
                        rag_chunks.append(chunk)
                    src = hit.payload.get("source_url", "")
                    if src:
                        rag_sources.append(src)
    except Exception as exc:
        logger.warning("RAG retrieval failed in chat: %s", exc)

    # ── 2. DB holdings ────────────────────────────────────────────────────────
    db_holdings: list[Holding] = []
    if payload.include_portfolio_context and payload.portfolio_id:
        try:
            pid = uuid.UUID(payload.portfolio_id)
            db_holdings = (
                await session.execute(
                    select(Holding).where(Holding.portfolio_id == pid)
                )
            ).scalars().all()
        except Exception as exc:
            logger.warning("Portfolio DB fetch failed: %s", exc)

    # ── 3. Build rich context block ───────────────────────────────────────────
    portfolio_context = _build_portfolio_context(
        db_holdings,
        payload.analytics_snapshot,
        payload.optimization_snapshot,
    )

    rag_section = ""
    if rag_chunks:
        rag_section = (
            "=== RELEVANT CONTEXT FROM DOCUMENTS ===\n"
            + "\n---\n".join(rag_chunks[:3])
        )

    # ── 4. Compose the current user turn with injected context ────────────────
    # Context is injected into the current user turn so it's always fresh
    # and doesn't bloat history turns with stale data.
    context_prefix = ""
    if portfolio_context:
        context_prefix += f"[LIVE PORTFOLIO DATA — ground your answer in this]\n{portfolio_context}\n\n"
    if rag_section:
        context_prefix += f"[DOCUMENT CONTEXT]\n{rag_section}\n\n"

    current_user_text = f"{context_prefix}[USER]\n{question}"

    # ── 5. Gemini multi-turn call ─────────────────────────────────────────────
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Build message list from history (last 10 turns = 5 exchanges)
        contents = []
        for msg in payload.history[-10:]:
            role = "user" if msg.role == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg.content)])
            )

        # Current turn (with injected context)
        contents.append(
            types.Content(role="user", parts=[types.Part(text=current_user_text)])
        )

        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.35,
                max_output_tokens=1200,
            ),
        )
        answer = response.text.strip()

    except Exception as exc:
        logger.error("LLM call failed in chat: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    return {
        "answer": answer,
        "sources": list(dict.fromkeys(rag_sources)),
    }
