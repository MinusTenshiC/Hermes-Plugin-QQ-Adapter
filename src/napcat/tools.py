"""
QQ-specific tools for the NapCat / OneBot v11 platform adapter.

Registered under ``toolset="napcat"``, these tools are automatically
included in the auto-generated ``hermes-napcat`` toolset alongside
the standard Hermes core tools.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Module-level reference to the adapter, set during register().
_adapter: Optional[Any] = None


def set_adapter(adapter) -> None:
    """Store the adapter reference for tool handlers."""
    global _adapter
    _adapter = adapter


def _get_api():
    """Return the OneBotAPI from the current adapter, or raise."""
    if _adapter is None:
        raise RuntimeError("NapCat adapter not initialised")
    return _adapter.api


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

QQ_KICK_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {
            "type": "integer",
            "description": "QQ group number to kick the member from",
        },
        "user_id": {
            "type": "integer",
            "description": "QQ number of the member to kick",
        },
        "reject_add_request": {
            "type": "boolean",
            "description": "If true, the member cannot re-join via normal means",
            "default": False,
        },
    },
    "required": ["group_id", "user_id"],
}

QQ_MUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {
            "type": "integer",
            "description": "QQ group number",
        },
        "user_id": {
            "type": "integer",
            "description": "QQ number of the member to mute",
        },
        "duration": {
            "type": "integer",
            "description": "Mute duration in seconds (0 = unmute, default 1800 = 30 min)",
            "default": 1800,
        },
    },
    "required": ["group_id", "user_id"],
}

QQ_MUTE_ALL_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {
            "type": "integer",
            "description": "QQ group number",
        },
        "enable": {
            "type": "boolean",
            "description": "True to enable whole-group mute, False to disable",
            "default": True,
        },
    },
    "required": ["group_id"],
}

QQ_SET_ADMIN_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {
            "type": "integer",
            "description": "QQ group number",
        },
        "user_id": {
            "type": "integer",
            "description": "QQ number of the member to set/unset as admin",
        },
        "enable": {
            "type": "boolean",
            "description": "True to set as admin, False to unset",
            "default": True,
        },
    },
    "required": ["group_id", "user_id"],
}

QQ_GET_MEMBER_INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {
            "type": "integer",
            "description": "QQ group number",
        },
        "user_id": {
            "type": "integer",
            "description": "QQ number of the member to query",
        },
    },
    "required": ["group_id", "user_id"],
}

QQ_GET_GROUP_INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {
            "type": "integer",
            "description": "QQ group number to query",
        },
    },
    "required": ["group_id"],
}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def qq_kick(ctx, group_id: int, user_id: int, reject_add_request: bool = False) -> dict:
    """Kick a member from a QQ group. Requires admin permissions."""
    api = _get_api()
    _adapter.record_tool_call()
    try:
        result = await api.set_group_kick(
            group_id=group_id,
            user_id=user_id,
            reject_add_request=reject_add_request,
        )
        return {"success": True, "message": f"Kicked user {user_id} from group {group_id}", "raw": result}
    except Exception as exc:
        logger.error("qq_kick failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def qq_mute(ctx, group_id: int, user_id: int, duration: int = 1800) -> dict:
    """Mute a QQ group member for the specified duration.

    Set duration=0 to unmute. Default duration is 1800 seconds (30 minutes).
    """
    api = _get_api()
    _adapter.record_tool_call()
    try:
        result = await api.set_group_ban(
            group_id=group_id,
            user_id=user_id,
            duration=duration,
        )
        if duration == 0:
            msg = f"Unmuted user {user_id} in group {group_id}"
        else:
            msg = f"Muted user {user_id} in group {group_id} for {duration}s"
        return {"success": True, "message": msg, "raw": result}
    except Exception as exc:
        logger.error("qq_mute failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def qq_mute_all(ctx, group_id: int, enable: bool = True) -> dict:
    """Enable or disable whole-group muting."""
    api = _get_api()
    _adapter.record_tool_call()
    try:
        result = await api.set_group_whole_ban(group_id=group_id, enable=enable)
        state = "enabled" if enable else "disabled"
        return {"success": True, "message": f"Whole-group mute {state} for group {group_id}", "raw": result}
    except Exception as exc:
        logger.error("qq_mute_all failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def qq_set_admin(ctx, group_id: int, user_id: int, enable: bool = True) -> dict:
    """Set or unset a group member as admin."""
    api = _get_api()
    _adapter.record_tool_call()
    try:
        result = await api.set_group_admin(group_id=group_id, user_id=user_id, enable=enable)
        state = "set as admin" if enable else "unset as admin"
        return {"success": True, "message": f"User {user_id} {state} in group {group_id}", "raw": result}
    except Exception as exc:
        logger.error("qq_set_admin failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def qq_get_member_info(ctx, group_id: int, user_id: int) -> dict:
    """Get a QQ group member's info (nickname, card, role, join time, etc.)."""
    api = _get_api()
    _adapter.record_tool_call()
    try:
        data = await api.get_group_member_info(group_id=group_id, user_id=user_id)
        return {"success": True, "data": data}
    except Exception as exc:
        logger.error("qq_get_member_info failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def qq_get_group_info(ctx, group_id: int) -> dict:
    """Get QQ group info (name, member count, etc.)."""
    api = _get_api()
    _adapter.record_tool_call()
    try:
        data = await api.get_group_info(group_id=group_id)
        return {"success": True, "data": data}
    except Exception as exc:
        logger.error("qq_get_group_info failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_tools(ctx) -> None:
    """Register all QQ-specific tools via *ctx*.

    Called from ``register()`` in ``adapter.py`` after the adapter is
    instantiated and the tool handler closure captures the adapter
    reference.
    """
    ctx.register_tool(
        name="qq_kick",
        toolset="napcat",
        schema=QQ_KICK_SCHEMA,
        handler=qq_kick,
    )
    ctx.register_tool(
        name="qq_mute",
        toolset="napcat",
        schema=QQ_MUTE_SCHEMA,
        handler=qq_mute,
    )
    ctx.register_tool(
        name="qq_mute_all",
        toolset="napcat",
        schema=QQ_MUTE_ALL_SCHEMA,
        handler=qq_mute_all,
    )
    ctx.register_tool(
        name="qq_set_admin",
        toolset="napcat",
        schema=QQ_SET_ADMIN_SCHEMA,
        handler=qq_set_admin,
    )
    ctx.register_tool(
        name="qq_get_member_info",
        toolset="napcat",
        schema=QQ_GET_MEMBER_INFO_SCHEMA,
        handler=qq_get_member_info,
    )
    ctx.register_tool(
        name="qq_get_group_info",
        toolset="napcat",
        schema=QQ_GET_GROUP_INFO_SCHEMA,
        handler=qq_get_group_info,
    )
