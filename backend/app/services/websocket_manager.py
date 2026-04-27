"""
app/services/websocket_manager.py
Central WebSocket connection manager.

Advisory tasks now run as asyncio.create_task() inside Uvicorn, so they share
the same process and can call broadcast_to_portfolio() directly — no Redis
pub/sub bridge or cross-process IPC needed.
"""

import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # portfolio_id (str) -> set of WebSocket connections
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, portfolio_id: str):
        await websocket.accept()
        self._rooms[portfolio_id].add(websocket)
        logger.info(
            "WS client connected to portfolio room %s (total: %d)",
            portfolio_id, len(self._rooms[portfolio_id]),
        )

    def disconnect(self, websocket: WebSocket, portfolio_id: str):
        self._rooms[portfolio_id].discard(websocket)
        logger.info(
            "WS client disconnected from portfolio room %s (remaining: %d)",
            portfolio_id, len(self._rooms[portfolio_id]),
        )

    async def broadcast_to_portfolio(self, portfolio_id: str, message: str):
        """Send a JSON string to all clients subscribed to a portfolio room."""
        sockets = list(self._rooms.get(portfolio_id, []))
        if not sockets:
            logger.debug("No WS clients in portfolio room %s — message dropped", portfolio_id)
            return
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception as exc:
                logger.warning(
                    "WS send failed (portfolio %s), removing connection: %s",
                    portfolio_id, exc,
                )
                dead.append(ws)
        for ws in dead:
            self._rooms[portfolio_id].discard(ws)


# Singleton — imported by tasks and the FastAPI endpoint
manager = ConnectionManager()
