"""
OneBot v11 event parser.

Converts raw OneBot v11 JSON events (message, notice, request,
meta_event) into Hermes ``MessageEvent`` objects.  Handles both
CQ-code string format and array segment format for message content.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource

from .constants import (
    POST_TYPE_MESSAGE,
    POST_TYPE_NOTICE,
    POST_TYPE_REQUEST,
    POST_TYPE_META,
    MESSAGE_TYPE_PRIVATE,
    MESSAGE_TYPE_GROUP,
    NOTICE_GROUP_INCREASE,
    NOTICE_GROUP_DECREASE,
    NOTICE_GROUP_ADMIN,
    NOTICE_GROUP_BAN,
    REQUEST_TYPE_FRIEND,
    REQUEST_TYPE_GROUP,
    META_HEARTBEAT,
    META_LIFECYCLE,
    DEDUP_WINDOW_SECONDS,
    DEDUP_MAX_SIZE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CQ-code parsing
# ---------------------------------------------------------------------------

# Matches [CQ:type,key=value,...]
_CQ_RE = re.compile(r"\[CQ:(\w+),([^\]]*)\]")


def _parse_cq_params(raw: str) -> Dict[str, str]:
    """Parse ``key=value,key2=value2`` from a CQ code into a dict."""
    params: Dict[str, str] = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        params[key.strip()] = value.strip()
    return params


class ParsedMessage:
    """Result of parsing a OneBot message."""

    __slots__ = (
        "text",
        "image_urls",
        "voice_urls",
        "reply_to_message_id",
        "at_self",
        "message_type",
    )

    def __init__(self) -> None:
        self.text: str = ""
        self.image_urls: List[str] = []
        self.voice_urls: List[str] = []
        self.reply_to_message_id: Optional[str] = None
        self.at_self: bool = False
        self.message_type: MessageType = MessageType.TEXT


# ---------------------------------------------------------------------------
# Event parser
# ---------------------------------------------------------------------------


class OneBotEventParser:
    """Parses OneBot v11 JSON events into Hermes MessageEvent objects."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform
        self._dedup: Dict[str, float] = {}  # msg_id -> expiry timestamp

    def parse(self, payload: Dict[str, Any], self_id: str) -> Optional[MessageEvent]:
        """Parse a raw OneBot v11 event.

        Returns ``None`` for events that should be silently ignored
        (heartbeats, lifecycle, unknown types).
        """
        post_type = payload.get("post_type", "")
        if post_type == POST_TYPE_MESSAGE:
            return self._parse_message(payload, self_id)
        if post_type == POST_TYPE_NOTICE:
            return self._parse_notice(payload, self_id)
        if post_type == POST_TYPE_REQUEST:
            return self._parse_request(payload, self_id)
        if post_type == POST_TYPE_META:
            return self._parse_meta(payload, self_id)
        logger.debug("[NapCat] Unknown post_type: %s", post_type)
        return None

    # ------------------------------------------------------------------
    # Message events
    # ------------------------------------------------------------------

    def _parse_message(
        self, payload: Dict[str, Any], self_id: str
    ) -> Optional[MessageEvent]:
        message_type = payload.get("message_type", "")
        user_id = str(payload.get("user_id", ""))
        raw_message = payload.get("message", "")
        raw_message_str = payload.get("raw_message", raw_message)
        message_id = str(payload.get("message_id", ""))
        sender = payload.get("sender", {}) or {}
        timestamp = payload.get("time", 0)

        # Deduplication
        if message_id and self._is_duplicate(message_id):
            return None

        # Skip self-sent messages (echo)
        if self_id and user_id == self_id:
            return None

        # Parse message content
        parsed = self._parse_content(raw_message)

        # Determine chat info
        if message_type == MESSAGE_TYPE_PRIVATE:
            chat_id = f"private:{user_id}"
            chat_type = "dm"
            chat_name = sender.get("nickname", user_id)
        elif message_type == MESSAGE_TYPE_GROUP:
            group_id = str(payload.get("group_id", ""))
            chat_id = f"group:{group_id}"
            chat_type = "group"
            chat_name = group_id
        else:
            logger.debug("[NapCat] Unknown message_type: %s", message_type)
            return None

        # Build source
        source = SessionSource(
            platform=self._platform,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=user_id,
            user_name=sender.get("nickname", "") or sender.get("card", ""),
            message_id=message_id,
        )

        # Determine primary message type
        msg_type = parsed.message_type
        if parsed.voice_urls and not parsed.text:
            msg_type = MessageType.VOICE
        elif parsed.image_urls and not parsed.text:
            msg_type = MessageType.PHOTO

        return MessageEvent(
            text=parsed.text or "[media]",
            message_type=msg_type,
            source=source,
            raw_message=payload,
            message_id=message_id,
            media_urls=parsed.image_urls + parsed.voice_urls,
            media_types=(
                ["image"] * len(parsed.image_urls)
                + ["voice"] * len(parsed.voice_urls)
            ),
            reply_to_message_id=parsed.reply_to_message_id,
            timestamp=(
                datetime.fromtimestamp(timestamp, tz=timezone.utc)
                if timestamp
                else datetime.now(tz=timezone.utc)
            ),
        )

    # ------------------------------------------------------------------
    # Notice events
    # ------------------------------------------------------------------

    def _parse_notice(
        self, payload: Dict[str, Any], self_id: str
    ) -> Optional[MessageEvent]:
        notice_type = payload.get("notice_type", "")
        group_id = str(payload.get("group_id", ""))

        if notice_type == NOTICE_GROUP_INCREASE:
            user_id = str(payload.get("user_id", ""))
            operator_id = str(payload.get("operator_id", ""))
            text = f"[系统] {user_id} 加入了群 {group_id}"
            if operator_id != user_id:
                text += f" (由 {operator_id} 邀请)"
            return self._build_notice(text, group_id)

        if notice_type == NOTICE_GROUP_DECREASE:
            user_id = str(payload.get("user_id", ""))
            operator_id = str(payload.get("operator_id", ""))
            sub_type = payload.get("sub_type", "leave")
            if sub_type == "kick":
                text = f"[系统] {user_id} 被 {operator_id} 踢出了群 {group_id}"
            elif sub_type == "kick_me":
                text = f"[系统] 机器人被 {operator_id} 踢出了群 {group_id}"
            else:
                text = f"[系统] {user_id} 退出了群 {group_id}"
            return self._build_notice(text, group_id)

        if notice_type == NOTICE_GROUP_ADMIN:
            user_id = str(payload.get("user_id", ""))
            sub_type = payload.get("sub_type", "set")
            verb = "被设为管理员" if sub_type == "set" else "被取消管理员"
            text = f"[系统] {user_id} 在群 {group_id} {verb}"
            return self._build_notice(text, group_id)

        if notice_type == NOTICE_GROUP_BAN:
            user_id = str(payload.get("user_id", ""))
            operator_id = str(payload.get("operator_id", ""))
            duration = payload.get("duration", 0)
            sub_type = payload.get("sub_type", "ban")
            if sub_type == "ban":
                text = f"[系统] {operator_id} 禁言了 {user_id} {duration}s (群 {group_id})"
            else:
                text = f"[系统] {operator_id} 解除了 {user_id} 的禁言 (群 {group_id})"
            return self._build_notice(text, group_id)

        return None

    # ------------------------------------------------------------------
    # Request events
    # ------------------------------------------------------------------

    def _parse_request(
        self, payload: Dict[str, Any], self_id: str
    ) -> Optional[MessageEvent]:
        request_type = payload.get("request_type", "")

        if request_type == REQUEST_TYPE_FRIEND:
            user_id = str(payload.get("user_id", ""))
            comment = payload.get("comment", "")
            flag = payload.get("flag", "")
            text = f"[系统] 用户 {user_id} 申请添加好友"
            if comment:
                text += f"，留言: {comment}"

            source = SessionSource(
                platform=self._platform,
                chat_id=f"private:{user_id}",
                chat_name=user_id,
                chat_type="dm",
                user_id=user_id,
            )
            return MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                raw_message=payload,
                message_id=f"request_{flag}",
                timestamp=datetime.now(tz=timezone.utc),
            )

        if request_type == REQUEST_TYPE_GROUP:
            sub_type = payload.get("sub_type", "invite")
            group_id = str(payload.get("group_id", ""))
            user_id = str(payload.get("user_id", ""))
            flag = payload.get("flag", "")
            if sub_type == "invite":
                text = f"[系统] 用户 {user_id} 邀请机器人加入群 {group_id}"
            else:
                text = f"[系统] 用户 {user_id} 申请加入群 {group_id}"

            source = SessionSource(
                platform=self._platform,
                chat_id=f"group:{group_id}",
                chat_name=group_id,
                chat_type="group",
                user_id=user_id,
            )
            return MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                raw_message=payload,
                message_id=f"request_{flag}",
                timestamp=datetime.now(tz=timezone.utc),
            )

        return None

    # ------------------------------------------------------------------
    # Meta events
    # ------------------------------------------------------------------

    def _parse_meta(
        self, payload: Dict[str, Any], self_id: str
    ) -> Optional[MessageEvent]:
        meta_type = payload.get("meta_event_type", "")
        if meta_type == META_HEARTBEAT:
            logger.debug("[NapCat] Heartbeat from self_id=%s", self_id)
            return None
        if meta_type == META_LIFECYCLE:
            sub_type = payload.get("sub_type", "")
            logger.info("[NapCat] Lifecycle event: %s (self_id=%s)", sub_type, self_id)
            return None
        return None

    # ------------------------------------------------------------------
    # Content parsing
    # ------------------------------------------------------------------

    def _parse_content(self, message: Any) -> ParsedMessage:
        """Parse OneBot message content (string or array format)."""
        parsed = ParsedMessage()

        if isinstance(message, list):
            self._parse_array(message, parsed)
        elif isinstance(message, str):
            self._parse_string(message, parsed)
        elif message is not None:
            parsed.text = str(message)

        return parsed

    def _parse_string(self, raw: str, parsed: ParsedMessage) -> None:
        """Parse CQ-code string format."""
        parts: List[str] = []
        last_end = 0

        for match in _CQ_RE.finditer(raw):
            # Text before this CQ code
            prefix = raw[last_end : match.start()]
            if prefix:
                parts.append(prefix)

            cq_type = match.group(1)
            params = _parse_cq_params(match.group(2))
            self._handle_cq(cq_type, params, parsed, parts)

            last_end = match.end()

        # Trailing text
        if last_end < len(raw):
            parts.append(raw[last_end:])

        parsed.text = "".join(parts).strip()

    def _parse_array(self, segments: list, parsed: ParsedMessage) -> None:
        """Parse OneBot array segment format."""
        parts: List[str] = []
        for seg in segments:
            seg_type = seg.get("type", "")
            data = seg.get("data", {}) or {}
            self._handle_segment(seg_type, data, parsed, parts)
        parsed.text = "".join(parts).strip()

    def _handle_cq(
        self,
        cq_type: str,
        params: Dict[str, str],
        parsed: ParsedMessage,
        parts: List[str],
    ) -> None:
        """Handle a parsed CQ code from string format."""
        if cq_type == "image":
            url = params.get("url", "") or params.get("file", "")
            if url:
                parsed.image_urls.append(url)
                # Don't add placeholder text — let media_urls carry the image.
                # If there is no text content, the adapter sets text to "[media]"
                # and message_type to PHOTO.
        elif cq_type == "record":
            url = params.get("url", "") or params.get("file", "")
            if url:
                parsed.voice_urls.append(url)
        elif cq_type == "reply":
            parsed.reply_to_message_id = params.get("id", "")
        elif cq_type == "at":
            qq = params.get("qq", "")
            if qq == "all":
                parts.append("@全体成员")
            else:
                parts.append(f"@{qq}")
        elif cq_type == "face":
            parts.append("[表情]")
        elif cq_type == "video":
            url = params.get("url", "") or params.get("file", "")
            if url:
                parsed.image_urls.append(url)
        elif cq_type == "share":
            parts.append("[分享]")
        elif cq_type == "location":
            parts.append("[位置]")
        elif cq_type == "redbag":
            parts.append("[红包]")
        elif cq_type == "forward":
            parts.append("[合并转发]")
        elif cq_type == "json":
            parts.append("[卡片消息]")
        elif cq_type == "xml":
            parts.append("[XML消息]")
        else:
            # Unknown CQ type — preserve as-is for debugging
            cq_text = params.get("text", "")
            if cq_text:
                parts.append(cq_text)

    def _handle_segment(
        self,
        seg_type: str,
        data: Dict[str, Any],
        parsed: ParsedMessage,
        parts: List[str],
    ) -> None:
        """Handle a parsed array segment."""
        if seg_type == "text":
            parts.append(data.get("text", ""))
        elif seg_type == "image":
            url = str(data.get("url", "") or data.get("file", ""))
            if url:
                parsed.image_urls.append(url)
        elif seg_type == "record":
            url = str(data.get("url", "") or data.get("file", ""))
            if url:
                parsed.voice_urls.append(url)
        elif seg_type == "reply":
            parsed.reply_to_message_id = str(data.get("id", ""))
        elif seg_type == "at":
            qq = str(data.get("qq", ""))
            if qq == "all":
                parts.append("@全体成员")
            else:
                parts.append(f"@{qq}")
        elif seg_type == "face":
            parts.append("[表情]")
        elif seg_type == "video":
            url = str(data.get("url", "") or data.get("file", ""))
            if url:
                parsed.image_urls.append(url)
        elif seg_type == "share":
            parts.append("[分享]")
        elif seg_type == "location":
            parts.append("[位置]")
        elif seg_type == "redbag":
            parts.append("[红包]")
        elif seg_type == "forward":
            parts.append("[合并转发]")
        elif seg_type == "json":
            parts.append("[卡片消息]")
        elif seg_type == "xml":
            parts.append("[XML消息]")
        else:
            logger.debug("[NapCat] Unknown segment type: %s", seg_type)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_notice(self, text: str, group_id: str) -> MessageEvent:
        source = SessionSource(
            platform=self._platform,
            chat_id=f"group:{group_id}",
            chat_name=group_id,
            chat_type="group",
        )
        return MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _is_duplicate(self, msg_id: str) -> bool:
        now = time.monotonic()
        # Prune expired entries
        expired = [
            mid for mid, exp in self._dedup.items() if exp <= now
        ]
        for mid in expired:
            del self._dedup[mid]
        # Check and store
        if msg_id in self._dedup:
            logger.debug("[NapCat] Duplicate message ignored: %s", msg_id)
            return True
        # Enforce size limit
        if len(self._dedup) >= DEDUP_MAX_SIZE:
            oldest = min(self._dedup, key=lambda k: self._dedup[k])
            del self._dedup[oldest]
        self._dedup[msg_id] = now + DEDUP_WINDOW_SECONDS
        return False
