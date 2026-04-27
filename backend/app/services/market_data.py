"""
app/services/market_data.py
Async wrapper around yfinance (which is synchronous).

All yfinance calls are dispatched to a thread pool via run_in_executor
so the FastAPI event loop is never blocked.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# How many seconds to wait for yfinance before giving up
FETCH_TIMEOUT_SECONDS = 30


def _sync_fetch_prices(symbols: list[str]) -> dict[str, Any]:
    """
    Synchronous inner function — runs in a thread pool.
    Returns a dict keyed by symbol with current_price and 30-day history.
    """
    result: dict[str, Any] = {}

    if not symbols:
        return result

    try:
        # Download all symbols in one request for efficiency
        raw = yf.download(
            tickers=symbols,
            period="30d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.error("yfinance download failed: %s", exc)
        return {s: {"error": str(exc), "current_price": None, "history": []} for s in symbols}

    for symbol in symbols:
        try:
            # When only 1 symbol, yf.download returns a flat DataFrame
            if len(symbols) == 1:
                ticker_df = raw
            else:
                ticker_df = raw[symbol] if symbol in raw.columns.get_level_values(0) else None

            if ticker_df is None or ticker_df.empty:
                logger.warning("No data returned for symbol: %s", symbol)
                result[symbol] = {
                    "current_price": None,
                    "history": [],
                    "warning": f"No data found for '{symbol}'. Verify the ticker suffix.",
                }
                continue

            close_series = ticker_df["Close"].dropna()

            if close_series.empty:
                result[symbol] = {
                    "current_price": None,
                    "history": [],
                    "warning": "Close price series is empty.",
                }
                continue

            current_price = round(float(close_series.iloc[-1]), 4)
            history = [
                {
                    "date": str(ts.date()) if isinstance(ts, datetime) else str(ts)[:10],
                    "close": round(float(price), 4),
                }
                for ts, price in close_series.items()
            ]

            result[symbol] = {
                "current_price": current_price,
                "history": history,
                "data_points": len(history),
            }

        except Exception as exc:
            logger.error("Error processing symbol %s: %s", symbol, exc)
            result[symbol] = {
                "current_price": None,
                "history": [],
                "error": str(exc),
            }

    return result


async def fetch_prices(symbols: list[str]) -> dict[str, Any]:
    """
    Async entry point.
    Dispatches the synchronous yfinance call to a thread pool and applies
    a timeout to guard against Yahoo Finance rate-limits or network hangs.
    """
    if not symbols:
        return {}

    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_fetch_prices, symbols),
            timeout=FETCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "yfinance timed out after %ss for symbols: %s",
            FETCH_TIMEOUT_SECONDS, symbols,
        )
        raise

    return result
