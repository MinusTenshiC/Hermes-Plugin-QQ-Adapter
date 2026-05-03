"""
OneBot v11 API wrapper.

Thin, typed helpers over ``OneBotClientManager.send_action()``.
Every public method corresponds to a OneBot v11 API action.

All methods accept an optional ``self_id`` parameter for routing
to a specific NapCat instance when multiple are connected.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import API_RESPONSE_TIMEOUT


class OneBotAPI:
    """High-level caller for OneBot v11 API actions."""

    def __init__(self, client_manager) -> None:
        self._cm = client_manager

    # ------------------------------------------------------------------
    # Message sending
    # ------------------------------------------------------------------

    async def send_private_msg(
        self,
        user_id: int,
        message: str | list,
        auto_escape: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "send_private_msg",
            {"user_id": user_id, "message": message, "auto_escape": auto_escape},
            self_id=self_id,
        )

    async def send_group_msg(
        self,
        group_id: int,
        message: str | list,
        auto_escape: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "send_group_msg",
            {"group_id": group_id, "message": message, "auto_escape": auto_escape},
            self_id=self_id,
        )

    async def send_msg(
        self,
        message_type: str,
        user_id: Optional[int] = None,
        group_id: Optional[int] = None,
        message: str | list | None = None,
        auto_escape: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        params: Dict[str, Any] = {
            "message_type": message_type,
            "auto_escape": auto_escape,
        }
        if user_id is not None:
            params["user_id"] = user_id
        if group_id is not None:
            params["group_id"] = group_id
        if message is not None:
            params["message"] = message
        return await self._cm.send_action("send_msg", params, self_id=self_id)

    async def delete_msg(
        self,
        message_id: int,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "delete_msg", {"message_id": message_id}, self_id=self_id
        )

    async def get_msg(
        self,
        message_id: int,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "get_msg", {"message_id": message_id}, self_id=self_id
        )

    # ------------------------------------------------------------------
    # Group info
    # ------------------------------------------------------------------

    async def get_group_info(
        self,
        group_id: int,
        no_cache: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "get_group_info",
            {"group_id": group_id, "no_cache": no_cache},
            self_id=self_id,
        )

    async def get_group_list(
        self,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action("get_group_list", {}, self_id=self_id)

    async def get_group_member_info(
        self,
        group_id: int,
        user_id: int,
        no_cache: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "get_group_member_info",
            {"group_id": group_id, "user_id": user_id, "no_cache": no_cache},
            self_id=self_id,
        )

    async def get_group_member_list(
        self,
        group_id: int,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "get_group_member_list", {"group_id": group_id}, self_id=self_id
        )

    # ------------------------------------------------------------------
    # User info
    # ------------------------------------------------------------------

    async def get_stranger_info(
        self,
        user_id: int,
        no_cache: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "get_stranger_info",
            {"user_id": user_id, "no_cache": no_cache},
            self_id=self_id,
        )

    async def get_friend_list(
        self,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action("get_friend_list", {}, self_id=self_id)

    async def get_login_info(
        self,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action("get_login_info", {}, self_id=self_id)

    # ------------------------------------------------------------------
    # Group administration
    # ------------------------------------------------------------------

    async def set_group_kick(
        self,
        group_id: int,
        user_id: int,
        reject_add_request: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_kick",
            {
                "group_id": group_id,
                "user_id": user_id,
                "reject_add_request": reject_add_request,
            },
            self_id=self_id,
        )

    async def set_group_ban(
        self,
        group_id: int,
        user_id: int,
        duration: int = 1800,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_ban",
            {"group_id": group_id, "user_id": user_id, "duration": duration},
            self_id=self_id,
        )

    async def set_group_whole_ban(
        self,
        group_id: int,
        enable: bool = True,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_whole_ban",
            {"group_id": group_id, "enable": enable},
            self_id=self_id,
        )

    async def set_group_admin(
        self,
        group_id: int,
        user_id: int,
        enable: bool = True,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_admin",
            {"group_id": group_id, "user_id": user_id, "enable": enable},
            self_id=self_id,
        )

    async def set_group_card(
        self,
        group_id: int,
        user_id: int,
        card: str = "",
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_card",
            {"group_id": group_id, "user_id": user_id, "card": card},
            self_id=self_id,
        )

    async def set_group_name(
        self,
        group_id: int,
        group_name: str,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_name",
            {"group_id": group_id, "group_name": group_name},
            self_id=self_id,
        )

    async def set_group_leave(
        self,
        group_id: int,
        is_dismiss: bool = False,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_leave",
            {"group_id": group_id, "is_dismiss": is_dismiss},
            self_id=self_id,
        )

    async def set_group_special_title(
        self,
        group_id: int,
        user_id: int,
        special_title: str = "",
        duration: int = -1,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_special_title",
            {
                "group_id": group_id,
                "user_id": user_id,
                "special_title": special_title,
                "duration": duration,
            },
            self_id=self_id,
        )

    # ------------------------------------------------------------------
    # Request handling
    # ------------------------------------------------------------------

    async def set_friend_add_request(
        self,
        flag: str,
        approve: bool = True,
        remark: str = "",
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_friend_add_request",
            {"flag": flag, "approve": approve, "remark": remark},
            self_id=self_id,
        )

    async def set_group_add_request(
        self,
        flag: str,
        sub_type: str,
        approve: bool = True,
        reason: str = "",
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "set_group_add_request",
            {
                "flag": flag,
                "sub_type": sub_type,
                "approve": approve,
                "reason": reason,
            },
            self_id=self_id,
        )

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    async def get_image(
        self,
        file: str,
        self_id: Optional[str] = None,
    ) -> dict:
        """Get image file info (download URL, etc.)."""
        return await self._cm.send_action(
            "get_image", {"file": file}, self_id=self_id
        )

    async def get_record(
        self,
        file: str,
        out_format: str = "mp3",
        self_id: Optional[str] = None,
    ) -> dict:
        """Get voice record file info."""
        return await self._cm.send_action(
            "get_record",
            {"file": file, "out_format": out_format},
            self_id=self_id,
        )

    async def can_send_image(
        self,
        self_id: Optional[str] = None,
    ) -> bool:
        try:
            data = await self._cm.send_action("can_send_image", {}, self_id=self_id)
            return data.get("yes", False)
        except Exception:
            return True  # assume yes on error

    async def can_send_record(
        self,
        self_id: Optional[str] = None,
    ) -> bool:
        try:
            data = await self._cm.send_action("can_send_record", {}, self_id=self_id)
            return data.get("yes", False)
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    async def get_status(
        self,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action("get_status", {}, self_id=self_id)

    async def get_version_info(
        self,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action("get_version_info", {}, self_id=self_id)

    async def send_like(
        self,
        user_id: int,
        times: int = 1,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action(
            "send_like",
            {"user_id": user_id, "times": min(times, 10)},
            self_id=self_id,
        )

    async def clean_cache(
        self,
        self_id: Optional[str] = None,
    ) -> dict:
        return await self._cm.send_action("clean_cache", {}, self_id=self_id)
