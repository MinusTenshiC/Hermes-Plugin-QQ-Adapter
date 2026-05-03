"""
OneBot WebSocket client connection manager.

Each NapCat instance connects as a WebSocket **client** to the adapter's
server.  This module manages those connections:

* Tracks connected clients keyed by ``self_id`` (QQ number).
* Routes inbound JSON payloads: events (has ``post_type``) vs API
  responses (has ``echo`` and ``status``).
* Provides ``send_action()`` for outbound API calls with Future-based
  request/response correlation via the ``echo`` field.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from .constants import (
    API_RESPONSE_TIMEOUT,
    ROLE_UNIVERSAL,
    ROLE_API,
    ROLE_EVENT,
    ONEBOT_STATUS_OK,
    ONEBOT_STATUS_FAILED,
)


class OneBotClientInfo:
    """Metadata for a single NapCat WebSocket connection."""

    __slots__ = (
        "ws",
        "self_id",
        "client_role",
        "connected_at",
        "last_event_at",
    )

    def __init__(
        self,
        ws,
        self_id: str,
        client_role: str,
    ) -> None:
        self.ws = ws
        self.self_id = self_id
        self.client_role = client_role
        self.connected_at = asyncio.get_event_loop().time()
        self.last_event_at = self.connected_at

    @property
    def is_universal(self) -> bool:
        return self.client_role == ROLE_UNIVERSAL

    @property
    def is_event_only(self) -> bool:
        return self.client_role == ROLE_EVENT


class OneBotClientManager:
    """Manages 1+ NapCat WebSocket connections.

    Supports two connection topologies:

    * **Universal** (recommended): one WS per ``self_id`` carries both
      events and API calls.
    * **Separate**: two WS connections per ``self_id`` — an API client
      and an Event client.

    Thread-safety: all operations assume they run on the asyncio event
    loop (no external locking).
    """

    def __init__(self) -> None:
        # keyed by self_id
        self._universal: Dict[str, OneBotClientInfo] = {}
        self._api_clients: Dict[str, OneBotClientInfo] = {}
        self._event_clients: Dict[str, OneBotClientInfo] = {}

        # echo -> Future[dict] for pending API responses
        self._pending: Dict[str, asyncio.Future] = {}

        # event callback: (self_id, payload) -> None
        self._event_handler = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_client(
        self,
        ws,
        self_id: str,
        client_role: str,
    ) -> bool:
        """Register a new WebSocket connection.

        If a connection with the same ``self_id`` and role already
        exists the old connection is closed and replaced.

        Returns ``True`` when the client was added (or replaced).
        """
        old = None
        if client_role == ROLE_UNIVERSAL:
            old = self._universal.get(self_id)
            self._universal[self_id] = OneBotClientInfo(ws, self_id, client_role)
            # A new universal replaces separate API + Event clients too.
            self._api_clients.pop(self_id, None)
            self._event_clients.pop(self_id, None)
        elif client_role == ROLE_API:
            old = self._api_clients.get(self_id)
            self._api_clients[self_id] = OneBotClientInfo(ws, self_id, client_role)
        elif client_role == ROLE_EVENT:
            old = self._event_clients.get(self_id)
            self._event_clients[self_id] = OneBotClientInfo(ws, self_id, client_role)

        if old is not None:
            asyncio.ensure_future(self._close_ws(old.ws))

        return True

    def remove_client(self, self_id: str) -> None:
        """Remove all connections for *self_id*.

        Fails any pending API responses for this client.
        """
        self._universal.pop(self_id, None)
        self._api_clients.pop(self_id, None)
        self._event_clients.pop(self_id, None)
        self._fail_pending_for(self_id, "NapCat disconnected")

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def _get_client(self, self_id: str):
        """Return the OneBotClientInfo for *self_id* from any role dict."""
        for d in (self._universal, self._api_clients, self._event_clients):
            info = d.get(self_id)
            if info is not None:
                return info
        return None

    def get_send_target(self, self_id: Optional[str] = None):
        """Return the WS to use for outbound API calls.

        Prefers the API client, then the universal client.  When
        *self_id* is ``None`` and only one client is connected that
        client is returned.
        """
        if self_id:
            api = self._api_clients.get(self_id)
            if api is not None:
                return api.ws
            uni = self._universal.get(self_id)
            if uni is not None:
                return uni.ws
            return None

        # No explicit self_id — try the only available client.
        if len(self._api_clients) == 1 and not self._universal:
            return next(iter(self._api_clients.values())).ws
        if len(self._universal) == 1 and not self._api_clients:
            return next(iter(self._universal.values())).ws
        return None

    def get_self_ids(self) -> list[str]:
        """Return all connected QQ numbers."""
        ids: set[str] = set()
        ids.update(self._universal.keys())
        ids.update(self._api_clients.keys())
        ids.update(self._event_clients.keys())
        return sorted(ids)

    def get_client_infos(self) -> list[dict]:
        """Return per-connection metadata for the WebUI dashboard."""
        result = []
        now = asyncio.get_event_loop().time()
        for d in (self._universal, self._api_clients, self._event_clients):
            for info in d.values():
                result.append({
                    "self_id": info.self_id,
                    "role": info.client_role,
                    "connected_at": info.connected_at,
                    "last_event_at": info.last_event_at,
                    "uptime_seconds": round(now - info.connected_at),
                    "idle_seconds": round(now - info.last_event_at),
                })
        return result

    @property
    def client_count(self) -> int:
        return len(self._universal) + len(self._api_clients) + len(self._event_clients)

    @property
    def is_any_connected(self) -> bool:
        return self.client_count > 0

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    async def send_action(
        self,
        action: str,
        params: Dict[str, Any],
        self_id: Optional[str] = None,
        timeout: float = API_RESPONSE_TIMEOUT,
    ) -> Dict[str, Any]:
        """Send a OneBot API action and wait for the response.

        Returns the ``data`` field on success.

        Raises ``RuntimeError`` when no client is connected,
        ``asyncio.TimeoutError`` when no response arrives in time,
        and ``OneBotAPIError`` for non-zero ``retcode``.
        """
        ws = self.get_send_target(self_id)
        if ws is None:
            raise RuntimeError("No NapCat client connected")

        echo = str(uuid.uuid4())
        payload = {"action": action, "params": params, "echo": echo}

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[echo] = future

        try:
            await ws.send_json(payload)
        except Exception:
            self._pending.pop(echo, None)
            raise RuntimeError(f"Failed to send {action} — WS send error")

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise asyncio.TimeoutError(
                f"OneBot API '{action}' timed out after {timeout}s"
            )

        status = response.get("status", "")
        retcode = response.get("retcode", 0)
        if status == ONEBOT_STATUS_FAILED or retcode != 0:
            msg = response.get("msg", response.get("wording", "unknown error"))
            raise OneBotAPIError(action, retcode, msg, response)

        return response.get("data", {})

    def set_event_handler(self, handler) -> None:
        """Set the async callback ``handler(self_id, payload)`` for
        inbound events."""
        self._event_handler = handler

    async def route_message(self, payload: Dict[str, Any], self_id: str) -> None:
        """Route an inbound JSON payload from the WS receive loop.

        * API responses (``echo`` + ``status`` present): resolve the
          pending future.
        * Events (``post_type`` present): dispatch to the event handler.
        * Everything else: logged at debug level and ignored.
        """
        if "echo" in payload and "status" in payload:
            self._resolve_response(payload)
            return

        if "post_type" in payload:
            client = self._get_client(self_id)
            if client is not None:
                client.last_event_at = asyncio.get_event_loop().time()
            handler = self._event_handler
            if handler is not None:
                await handler(self_id, payload)
            return

        logger.debug(
            "[NapCat] Unknown payload (no post_type, no echo): %.200s",
            str(payload),
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close_all(self) -> None:
        """Close all WebSocket connections and fail pending futures."""
        clients: list[OneBotClientInfo] = []
        clients.extend(self._universal.values())
        clients.extend(self._api_clients.values())
        clients.extend(self._event_clients.values())

        self._universal.clear()
        self._api_clients.clear()
        self._event_clients.clear()

        for info in clients:
            await self._close_ws(info.ws)

        for echo, future in list(self._pending.items()):
            if not future.done():
                future.set_exception(ConnectionError("NapCat disconnected"))
            del self._pending[echo]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_response(self, payload: Dict[str, Any]) -> None:
        echo = payload.get("echo")
        if echo is None:
            logger.debug("[NapCat] API response missing echo field")
            return
        future = self._pending.pop(echo, None)
        if future is None:
            logger.debug("[NapCat] No pending future for echo=%s", echo)
            return
        if not future.done():
            future.set_result(payload)

    def _fail_pending_for(self, self_id: str, reason: str) -> None:
        """Fail all pending futures whose echo was created via *self_id*.

        Since we don't store per-echo self_id mapping, we fail
        everything — the caller will retry on the next available
        connection.
        """
        for echo, future in list(self._pending.items()):
            if not future.done():
                future.set_exception(ConnectionError(reason))
            del self._pending[echo]

    @staticmethod
    async def _close_ws(ws) -> None:
        try:
            if not ws.closed:
                await ws.close()
        except Exception:
            pass


class OneBotAPIError(Exception):
    """OneBot API returned a non-zero retcode."""

    def __init__(self, action: str, retcode: int, message: str, raw: dict) -> None:
        self.action = action
        self.retcode = retcode
        self.message = message
        self.raw = raw
        super().__init__(f"OneBot API '{action}' failed (retcode={retcode}): {message}")
