"""
NapCat / OneBot v11 platform adapter for Hermes Agent.

Configuration in config.yaml::

    gateway:
      platforms:
        napcat:
          enabled: true
          extra:
            host: "0.0.0.0"       # WS server bind address
            port: 8080              # WS server port
            token: "auth-token"     # Must match NapCat config
            auto_accept_friend: true
            auto_accept_group_invite: true

Or via environment variables (override config.yaml):
  NAPCAT_WS_HOST, NAPCAT_WS_PORT, NAPCAT_TOKEN,
  NAPCAT_ALLOWED_USERS, NAPCAT_ALLOW_ALL_USERS,
  NAPCAT_AUTO_ACCEPT_FRIEND, NAPCAT_AUTO_ACCEPT_GROUP_INVITE
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None  # type: ignore[assignment]

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.platforms.helpers import strip_markdown

from .constants import (
    DEFAULT_WS_HOST,
    DEFAULT_WS_PORT,
    WS_PATH,
    ENV_WS_HOST,
    ENV_WS_PORT,
    ENV_TOKEN,
    ENV_AUTO_ACCEPT_FRIEND,
    ENV_AUTO_ACCEPT_GROUP_INVITE,
    ENV_GROUP_ALLOWED_USERS,
    ENV_ALLOWED_USERS,
    ENV_ALLOW_ALL_USERS,
    ENV_AUTO_ACCEPT_FRIEND,
    ENV_AUTO_ACCEPT_GROUP_INVITE,
    ENV_WS_HOST,
    ENV_WS_PORT,
    ENV_TOKEN,
    MAX_LOG_ENTRIES,
    MAX_MESSAGE_LENGTH,
    MESSAGE_INDICATOR_RESERVE,
    ROLE_UNIVERSAL,
    ROLE_API,
    ROLE_EVENT,
    POST_TYPE_REQUEST,
    REQUEST_TYPE_FRIEND,
    REQUEST_TYPE_GROUP,
)
from .onebot_client import OneBotClientManager, OneBotAPIError
from .onebot_api import OneBotAPI
from .onebot_event import OneBotEventParser
from .tools import set_adapter, register_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class NapCatAdapter(BasePlatformAdapter):
    """NapCat / OneBot v11 platform adapter.

    Runs an aiohttp WebSocket server that NapCat connects to as a client
    (reverse WebSocket mode).  Supports multiple NapCat instances
    (multiple QQ accounts) via the ``X-Self-ID`` header.
    """

    def __init__(self, config: PlatformConfig) -> None:
        platform = Platform("napcat")
        super().__init__(config=config, platform=platform)

        extra = getattr(config, "extra", {}) or {}

        # Server configuration
        self._ws_host = str(
            extra.get("host") or os.getenv(ENV_WS_HOST, DEFAULT_WS_HOST)
        )
        self._ws_port = int(
            extra.get("port") or os.getenv(ENV_WS_PORT, str(DEFAULT_WS_PORT))
        )
        self._token = str(extra.get("token") or os.getenv(ENV_TOKEN, ""))

        # Auto-handle events
        self._auto_accept_friend = _env_bool(
            ENV_AUTO_ACCEPT_FRIEND,
            extra.get("auto_accept_friend", True),
        )
        self._auto_accept_group_invite = _env_bool(
            ENV_AUTO_ACCEPT_GROUP_INVITE,
            extra.get("auto_accept_group_invite", True),
        )

        # Group-level access control (which groups can use the bot)
        self._group_allowed_ids: Optional[set] = None
        _group_raw = os.getenv(ENV_GROUP_ALLOWED_USERS, "").strip()
        if _group_raw:
            self._group_allowed_ids = {
                gid.strip() for gid in _group_raw.split(",") if gid.strip()
            }

        # WebUI infrastructure
        self._started_at: float = 0.0  # set in connect()
        self._msg_received: int = 0
        self._msg_sent: int = 0
        self._api_errors: int = 0
        self._tool_calls: int = 0
        self._message_log: collections.deque = collections.deque(
            maxlen=MAX_LOG_ENTRIES
        )
        self._config_overrides: dict = {}

        # aiohttp server state
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        # OneBot protocol layer
        self._client_manager = OneBotClientManager()
        self.api = OneBotAPI(self._client_manager)
        self._event_parser = OneBotEventParser(self.platform)

        # Lifecycle
        self._cleanup_event = asyncio.Event()

        # Store adapter reference for tool handlers
        set_adapter(self)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "NapCat"

    @property
    def max_message_length(self) -> int:
        return MAX_MESSAGE_LENGTH

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Start the aiohttp WebSocket server and wait for NapCat to connect."""
        if not AIOHTTP_AVAILABLE:
            self._set_fatal_error(
                "missing_aiohttp",
                "aiohttp is required for the NapCat adapter",
                retryable=False,
            )
            return False

        # Pre-flight port check
        if not await self._check_port(self._ws_host, self._ws_port):
            self._set_fatal_error(
                "port_in_use",
                f"Port {self._ws_port} is already in use",
                retryable=False,
            )
            return False

        try:
            self._app = web.Application()
            self._app.router.add_get(WS_PATH, self._handle_ws)
            # Health-check endpoint
            self._app.router.add_get("/health", self._handle_health)

            # WebUI — register API routes + static files
            from .webui_routes import register_webui_routes
            register_webui_routes(self._app, self)
            self._started_at = time.time()

            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._ws_host, self._ws_port)
            await self._site.start()

            self._mark_connected()
            logger.info(
                "[NapCat] WS server listening on ws://%s:%s%s",
                self._ws_host,
                self._ws_port,
                WS_PATH,
            )
            if self._token:
                logger.info("[NapCat] Token authentication enabled")
            else:
                logger.warning(
                    "[NapCat] No token set — accepting all connections "
                    "(set NAPCAT_TOKEN or config.extra.token)"
                )

            return True

        except Exception as exc:
            logger.error("[NapCat] Failed to start WS server: %s", exc)
            await self._cleanup_server()
            self._set_fatal_error("server_start_failed", str(exc), retryable=True)
            return False

    async def disconnect(self) -> None:
        """Stop the WS server and close all NapCat connections."""
        self._mark_disconnected()
        self._cleanup_event.set()

        await self._client_manager.close_all()
        await self._cleanup_server()

        logger.info("[NapCat] Disconnected")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a text message to a QQ user or group.

        *chat_id* format: ``"private:{qq_number}"`` or ``"group:{qq_number}"``.
        """
        if not self._client_manager.is_any_connected:
            return SendResult(
                success=False,
                error="No NapCat client connected",
                retryable=True,
            )

        content = self.format_message(content)

        try:
            chat_type, target_id = self._parse_chat_id(chat_id)
        except ValueError:
            return SendResult(
                success=False,
                error=f"Invalid chat_id format: {chat_id}",
            )

        # Build message payload
        message: Any = content
        if reply_to:
            message = [
                {"type": "reply", "data": {"id": str(reply_to)}},
                {"type": "text", "data": {"text": content}},
            ]

        # Split long messages
        chunks = self.truncate_message(content, MAX_MESSAGE_LENGTH)
        last_id = None

        for i, chunk in enumerate(chunks):
            chunk_message = chunk
            if reply_to and len(chunks) > 1:
                # Only first chunk gets the reply context
                chunk_message = (
                    [{"type": "reply", "data": {"id": str(reply_to)}},
                     {"type": "text", "data": {"text": chunk}}]
                    if i == 0
                    else chunk
                )
            elif reply_to and len(chunks) == 1:
                chunk_message = message

            try:
                if chat_type == "private":
                    data = await self.api.send_private_msg(
                        user_id=int(target_id),
                        message=chunk_message,
                    )
                else:
                    data = await self.api.send_group_msg(
                        group_id=int(target_id),
                        message=chunk_message,
                    )
                last_id = str(data.get("message_id", ""))
            except OneBotAPIError as exc:
                self._api_errors += 1
                return SendResult(
                    success=False,
                    error=f"OneBot API error: {exc.message}",
                    retryable=_is_retryable(exc.retcode),
                )
            except asyncio.TimeoutError:
                self._api_errors += 1
                return SendResult(
                    success=False,
                    error="OneBot API timeout",
                    retryable=True,
                )
            except RuntimeError as exc:
                self._api_errors += 1
                return SendResult(
                    success=False,
                    error=str(exc),
                    retryable=True,
                )

        self._msg_sent += 1
        self._message_log.append({
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "direction": "out",
            "chat_type": chat_type,
            "chat_id": target_id,
            "user_id": "",
            "content_preview": content[:200],
            "content_full": content,
            "status": "chunked" if len(chunks) > 1 else "ok",
            "self_id": "",
        })
        return SendResult(success=True, message_id=last_id)

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """OneBot v11 has no typing indicator — no-op."""
        pass

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get info for a chat (QQ user or group)."""
        try:
            chat_type, target_id = self._parse_chat_id(chat_id)
        except ValueError:
            return {"name": chat_id, "type": "unknown"}

        try:
            if chat_type == "private":
                data = await self.api.get_stranger_info(user_id=int(target_id))
                return {
                    "name": data.get("nickname", target_id),
                    "type": "dm",
                    "user_id": target_id,
                    "sex": data.get("sex", "unknown"),
                    "age": data.get("age", 0),
                }
            else:
                data = await self.api.get_group_info(group_id=int(target_id))
                return {
                    "name": data.get("group_name", target_id),
                    "type": "group",
                    "member_count": data.get("member_count", 0),
                    "max_member_count": data.get("max_member_count", 0),
                }
        except Exception as exc:
            logger.debug("[NapCat] get_chat_info failed for %s: %s", chat_id, exc)
            return {"name": chat_id, "type": "unknown"}

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_message(self, content: str) -> str:
        """Strip markdown — QQ doesn't render it."""
        return strip_markdown(content)

    # ------------------------------------------------------------------
    # WebSocket handler
    # ------------------------------------------------------------------

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        """Handle an incoming WebSocket connection from NapCat."""
        ws = web.WebSocketResponse(heartbeat=WS_HEARTBEAT)
        await ws.prepare(request)

        self_id = request.headers.get("X-Self-ID", "")
        client_role = request.headers.get("X-Client-Role", ROLE_UNIVERSAL)
        auth_header = request.headers.get("Authorization", "")

        # Validate token
        if self._token:
            token = auth_header
            # NapCat may send token as "Bearer <token>" or plain "<token>"
            if token.startswith("Bearer "):
                token = token[7:]
            if token != self._token:
                logger.warning(
                    "[NapCat] Token mismatch for self_id=%s from %s",
                    self_id,
                    request.remote,
                )
                await ws.close(code=4001, message=b"Invalid token")
                return ws

        # Validate self_id
        if not self_id:
            logger.warning("[NapCat] Missing X-Self-ID header from %s", request.remote)
            await ws.close(code=4002, message=b"Missing X-Self-ID")
            return ws

        # Register client
        self._client_manager.add_client(ws, self_id, client_role)
        logger.info(
            "[NapCat] Client connected: self_id=%s role=%s", self_id, client_role
        )

        # Receive loop
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                    except json.JSONDecodeError:
                        logger.debug("[NapCat] Invalid JSON from self_id=%s", self_id)
                        continue
                    await self._client_manager.route_message(payload, self_id)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(
                        "[NapCat] WS error for self_id=%s: %s",
                        self_id,
                        ws.exception(),
                    )
                    break
                elif msg.type == web.WSMsgType.CLOSE:
                    logger.info("[NapCat] WS close frame from self_id=%s", self_id)
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "[NapCat] Exception in receive loop (self_id=%s): %s",
                self_id,
                exc,
            )
        finally:
            self._client_manager.remove_client(self_id)
            logger.info("[NapCat] Client disconnected: self_id=%s", self_id)

        return ws

    async def _handle_health(self, request: web.Request) -> web.Response:
        count = self._client_manager.client_count
        body = json.dumps({
            "status": "ok" if count > 0 else "waiting",
            "connections": count,
            "self_ids": self._client_manager.get_self_ids(),
        })
        return web.Response(text=body, content_type="application/json")

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    async def _process_event(self, self_id: str, payload: dict) -> None:
        """Parse an inbound OneBot event and handle it.

        Called by ``OneBotClientManager.route_message()`` via the event
        handler callback.
        """
        event = self._event_parser.parse(payload, self_id)
        if event is None:
            return

        # Handle request events inline (before queueing to agent)
        post_type = payload.get("post_type", "")
        if post_type == POST_TYPE_REQUEST:
            request_type = payload.get("request_type", "")
            flag = payload.get("flag", "")
            if request_type == REQUEST_TYPE_FRIEND and self._auto_accept_friend:
                try:
                    await self.api.set_friend_add_request(flag=flag, approve=True)
                    logger.info(
                        "[NapCat] Auto-accepted friend request: %s",
                        event.source.user_id,
                    )
                except Exception as exc:
                    logger.error(
                        "[NapCat] Failed to auto-accept friend request: %s", exc
                    )
                return  # Don't forward to agent after auto-handling
            if (
                request_type == REQUEST_TYPE_GROUP
                and self._auto_accept_group_invite
                and payload.get("sub_type") == "invite"
            ):
                try:
                    await self.api.set_group_add_request(
                        flag=flag, sub_type="invite", approve=True
                    )
                    logger.info(
                        "[NapCat] Auto-accepted group invite: %s",
                        event.source.chat_id,
                    )
                except Exception as exc:
                    logger.error(
                        "[NapCat] Failed to auto-accept group invite: %s", exc
                    )
                return

        # Group-level access control — only forward messages from
        # groups listed in NAPCAT_GROUP_ALLOWED_USERS (when configured).
        if (
            self._group_allowed_ids is not None
            and event.source.chat_type == "group"
        ):
            chat_id = event.source.chat_id or ""
            if "*" not in self._group_allowed_ids and chat_id not in self._group_allowed_ids:
                logger.debug(
                    "[NapCat] Rejected group message: group %s not in NAPCAT_GROUP_ALLOWED_USERS",
                    chat_id,
                )
                return

        # Log incoming message for WebUI
        self._msg_received += 1
        self._message_log.append({
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "direction": "in",
            "chat_type": event.source.chat_type,
            "chat_id": event.source.chat_id or "",
            "user_id": event.source.user_id or "",
            "content_preview": (event.text or "")[:200],
            "content_full": event.text or "",
            "status": "ok",
            "self_id": self_id,
        })

        # Forward to Hermes agent
        await self.handle_message(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_chat_id(chat_id: str) -> tuple[str, str]:
        """Parse ``chat_id`` into ``(chat_type, target_id)``.

        Raises ``ValueError`` for malformed chat_ids.
        """
        if ":" in chat_id:
            parts = chat_id.split(":", 1)
            return parts[0], parts[1]
        raise ValueError(f"chat_id must be 'private:<qq>' or 'group:<qq>', got {chat_id!r}")

    @staticmethod
    async def _check_port(host: str, port: int) -> bool:
        """Check if *port* on *host* is available."""
        import socket as _socket
        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                sock.bind((host, port))
                return True
            except OSError:
                return False
            finally:
                sock.close()
        except Exception:
            return True  # assume ok on unexpected error

    async def _cleanup_server(self) -> None:
        """Idempotent cleanup of the aiohttp server."""
        if self._site is not None:
            try:
                await self._site.stop()
            except Exception:
                pass
            self._site = None
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception:
                pass
            self._runner = None
        self._app = None

    # ------------------------------------------------------------------
    # Config resolution for WebUI
    # ------------------------------------------------------------------

    def _resolve_config(self, key: str) -> tuple:
        """Return ``(value, source)`` resolving env → override → default."""
        default_map = {
            ENV_WS_HOST: DEFAULT_WS_HOST,
            ENV_WS_PORT: str(DEFAULT_WS_PORT),
            ENV_TOKEN: "",
            ENV_ALLOW_ALL_USERS: "false",
            ENV_ALLOWED_USERS: "",
            ENV_GROUP_ALLOWED_USERS: "",
            ENV_AUTO_ACCEPT_FRIEND: "true",
            ENV_AUTO_ACCEPT_GROUP_INVITE: "true",
        }
        if key in self._config_overrides:
            return self._config_overrides[key], "override"
        env_val = os.getenv(key, "").strip()
        if env_val:
            return env_val, "env"
        return default_map.get(key, ""), "default"

    def record_tool_call(self) -> None:
        """Increment tool call counter (called from tools.py)."""
        self._tool_calls += 1

    def _get_effective_allowed_users(self) -> Optional[set]:
        """Return current effective allowed user IDs."""
        val, _source = self._resolve_config(ENV_ALLOWED_USERS)
        if not val:
            return None
        return {uid.strip() for uid in val.split(",") if uid.strip()}

    def _get_effective_allow_all(self) -> bool:
        """Return current effective allow-all flag."""
        val, _source = self._resolve_config(ENV_ALLOW_ALL_USERS)
        return val.lower() in ("true", "1", "yes")

    def _reload_config_overrides(self) -> None:
        """Re-read mutable config from overrides into instance attributes."""
        val, _src = self._resolve_config(ENV_GROUP_ALLOWED_USERS)
        if val:
            self._group_allowed_ids = {
                gid.strip() for gid in val.split(",") if gid.strip()
            }
        else:
            self._group_allowed_ids = None
        self._auto_accept_friend = _env_bool(
            ENV_AUTO_ACCEPT_FRIEND,
            self._config_overrides.get(ENV_AUTO_ACCEPT_FRIEND, str(True)),
        )
        self._auto_accept_group_invite = _env_bool(
            ENV_AUTO_ACCEPT_GROUP_INVITE,
            self._config_overrides.get(ENV_AUTO_ACCEPT_GROUP_INVITE, str(True)),
        )


# ---------------------------------------------------------------------------
# Plugin support functions
# ---------------------------------------------------------------------------

def check_requirements() -> bool:
    """Check if aiohttp is available."""
    return AIOHTTP_AVAILABLE


def validate_config(config: PlatformConfig) -> bool:
    """Validate that enough config is present to start the server."""
    extra = getattr(config, "extra", {}) or {}
    host = extra.get("host") or os.getenv(ENV_WS_HOST, DEFAULT_WS_HOST)
    port = extra.get("port") or os.getenv(ENV_WS_PORT, "")
    return bool(host and port)


def is_connected(config: PlatformConfig) -> bool:
    """Check whether NapCat is configured (env or config.yaml)."""
    extra = getattr(config, "extra", {}) or {}
    return bool(
        extra.get("host")
        or extra.get("port")
        or os.getenv(ENV_WS_HOST)
        or os.getenv(ENV_WS_PORT)
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_adapter_cfg: Optional[PlatformConfig] = None


def _adapter_factory(cfg: PlatformConfig) -> NapCatAdapter:
    global _adapter_cfg
    _adapter_cfg = cfg
    adapter = NapCatAdapter(cfg)
    # Wire up the event handler so the client manager routes events to the adapter
    adapter._client_manager.set_event_handler(adapter._process_event)
    return adapter


def register(ctx) -> None:
    """Plugin entry point — called by the Hermes plugin system."""
    ctx.register_platform(
        name="napcat",
        label="NapCat (QQ / OneBot v11)",
        adapter_factory=_adapter_factory,
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=[
            ENV_WS_HOST,
            ENV_WS_PORT,
            ENV_TOKEN,
        ],
        install_hint="pip install aiohttp",
        # Auth integration
        allowed_users_env="NAPCAT_ALLOWED_USERS",
        allow_all_env="NAPCAT_ALLOW_ALL_USERS",
        # Message
        max_message_length=MAX_MESSAGE_LENGTH,
        # Display
        emoji="🐧",
        pii_safe=False,
        allow_update_command=True,
        platform_hint=(
            "You are chatting via QQ (NapCat / OneBot v11). "
            "QQ does NOT support markdown formatting — use plain text only. "
            "Messages are limited to 4000 characters per chunk (long messages "
            "are automatically split). In groups, you can @mention users by "
            "using their QQ number. You have access to QQ-specific tools: "
            "qq_kick, qq_mute, qq_mute_all, qq_set_admin, "
            "qq_get_member_info, qq_get_group_info."
        ),
    )

    # Register QQ-specific tools
    register_tools(ctx)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

WS_HEARTBEAT = 30.0  # aiohttp WS ping interval, seconds

_RETRYABLE_CODES = frozenset({
    1,   # async / post-timeout
    34,  # rate limited
    100, # server error / unknown
    101, # connection lost
    102, # service unavailable
})


def _is_retryable(retcode: int) -> bool:
    """Return True when *retcode* indicates a transient error."""
    return retcode in _RETRYABLE_CODES


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable."""
    val = os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")
