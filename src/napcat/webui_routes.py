"""
WebUI API routes for the NapCat adapter.

Registered on the existing aiohttp server during ``connect()``.
All handlers are plain async functions that capture the adapter
instance via closure.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING

from aiohttp import web, WSMsgType

from .constants import (
    ENV_ALLOW_ALL_USERS,
    ENV_ALLOWED_USERS,
    ENV_AUTO_ACCEPT_FRIEND,
    ENV_AUTO_ACCEPT_GROUP_INVITE,
    ENV_GROUP_ALLOWED_USERS,
    ENV_WS_HOST,
    ENV_WS_PORT,
    ENV_TOKEN,
    MAX_LOG_ENTRIES,
)

if TYPE_CHECKING:
    from .adapter import NapCatAdapter

logger = logging.getLogger(__name__)

# ---- Config keys that can be changed at runtime via WebUI -------------------
_MUTABLE_KEYS = frozenset({
    ENV_ALLOWED_USERS,
    ENV_GROUP_ALLOWED_USERS,
    ENV_ALLOW_ALL_USERS,
    ENV_AUTO_ACCEPT_FRIEND,
    ENV_AUTO_ACCEPT_GROUP_INVITE,
})

_READONLY_KEYS = frozenset({
    ENV_WS_HOST,
    ENV_WS_PORT,
    ENV_TOKEN,
})

_ALL_CONFIG_KEYS = sorted(_MUTABLE_KEYS | _READONLY_KEYS)


def register_webui_routes(app: web.Application, adapter: "NapCatAdapter") -> None:
    """Register all WebUI routes on the aiohttp *app*."""

    async def _api_status(request: web.Request) -> web.Response:
        now = time.time()
        cm = adapter._client_manager
        connections = cm.get_client_infos()

        counters = {
            "messages_received": adapter._msg_received,
            "messages_sent": adapter._msg_sent,
            "api_errors": adapter._api_errors,
            "tool_calls": adapter._tool_calls,
        }

        config_summary = {
            "host": adapter._ws_host,
            "port": adapter._ws_port,
            "token_configured": bool(adapter._token),
            "auto_accept_friend": adapter._auto_accept_friend,
            "auto_accept_group_invite": adapter._auto_accept_group_invite,
            "allowed_users_count": (
                len(adapter._get_effective_allowed_users())
                if adapter._get_effective_allowed_users() is not None
                else 0
            ),
            "group_allowed_users_count": (
                len(adapter._group_allowed_ids)
                if adapter._group_allowed_ids is not None
                else 0
            ),
            "allow_all_users": adapter._get_effective_allow_all(),
            "config_overrides": dict(adapter._config_overrides),
        }

        return web.json_response({
            "status": "ok" if connections else "waiting",
            "uptime_seconds": round(now - adapter._started_at),
            "connections": len(connections),
            "self_ids": cm.get_self_ids(),
            "per_connection": connections,
            "counters": counters,
            "config_summary": config_summary,
        })

    async def _api_logs(request: web.Request) -> web.Response:
        limit = min(int(request.query.get("limit", "50")), 200)
        offset = int(request.query.get("offset", "0"))
        direction = request.query.get("direction", "all")  # "in" | "out" | "all"
        chat_type = request.query.get("chat_type", "all")   # "dm" | "group" | "all"

        entries = list(adapter._message_log)

        # Filter
        if direction != "all":
            entries = [e for e in entries if e["direction"] == direction]
        if chat_type != "all":
            entries = [e for e in entries if e["chat_type"] == chat_type]

        total = len(entries)
        page = entries[offset:offset + limit]

        return web.json_response({
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": page,
        })

    async def _api_config_get(request: web.Request) -> web.Response:
        items = []
        for key in _ALL_CONFIG_KEYS:
            value, source = adapter._resolve_config(key)
            items.append({
                "key": key,
                "value": value,
                "source": source,       # "env" | "override" | "default"
                "mutable": key in _MUTABLE_KEYS,
            })
        return web.json_response({"config": items})

    async def _api_config_post(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"error": "Invalid JSON body"}, status=400
            )

        updated = {}
        rejected = {}
        for key, raw_value in body.items():
            if key not in _MUTABLE_KEYS:
                rejected[key] = "read-only (requires restart)"
                continue
            adapter._config_overrides[key] = str(raw_value).strip()
            updated[key] = adapter._config_overrides[key]

        # Re-parse affected adapter state
        adapter._reload_config_overrides()

        return web.json_response({
            "updated": updated,
            "rejected": rejected,
        })

    async def _api_chat_ws(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await ws.send_json({"error": "Invalid JSON"})
                        continue

                    action = data.get("action", "chat")
                    if action == "ping":
                        await ws.send_json({"type": "pong"})
                        continue

                    if action == "chat":
                        text = (data.get("text") or "").strip()
                        if not text:
                            await ws.send_json({"error": "Empty message"})
                            continue

                        chat_type = data.get("chat_type", "dm")
                        user_id = data.get("user_id", "webui-tester")
                        chat_id = data.get("chat_id", user_id)

                        # Build a synthetic MessageEvent
                        from gateway.platforms.base import MessageEvent, MessageType, SessionSource
                        event = MessageEvent(
                            text=text,
                            message_type=MessageType.TEXT,
                            source=SessionSource(
                                platform=adapter.platform,
                                chat_id=chat_id,
                                user_id=user_id,
                                chat_type=chat_type,
                            ),
                        )

                        try:
                            await adapter.handle_message(event)
                            await ws.send_json({
                                "type": "sent",
                                "text": text,
                                "chat_type": chat_type,
                            })
                        except Exception as exc:
                            logger.error("[WebUI] Chat test error: %s", exc)
                            await ws.send_json({
                                "type": "error",
                                "error": str(exc),
                            })

                elif msg.type == WSMsgType.ERROR:
                    logger.error("[WebUI] Chat WS error: %s", ws.exception())
        finally:
            await ws.close()

        return ws

    # Register routes
    app.router.add_get("/api/status", _api_status)
    app.router.add_get("/api/logs", _api_logs)
    app.router.add_get("/api/config", _api_config_get)
    app.router.add_post("/api/config", _api_config_post)
    app.router.add_get("/api/chat/ws", _api_chat_ws)

    # Serve static WebUI from the webui/ directory
    import pathlib
    _webui_dir = pathlib.Path(__file__).parent / "webui"
    app.router.add_static("/", _webui_dir, show_index=True)
