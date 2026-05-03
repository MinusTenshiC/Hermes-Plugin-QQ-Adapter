"""
Constants for the NapCat / OneBot v11 platform adapter.

Shared across all adapter modules to avoid magic numbers and
duplicated configuration defaults.
"""

# ---------------------------------------------------------------------------
# Server defaults (overridable via env vars or config.yaml extra)
# ---------------------------------------------------------------------------
DEFAULT_WS_HOST = "0.0.0.0"
DEFAULT_WS_PORT = 8080
WS_PATH = "/onebot"

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------
ENV_WS_HOST = "NAPCAT_WS_HOST"
ENV_WS_PORT = "NAPCAT_WS_PORT"
ENV_TOKEN = "NAPCAT_TOKEN"
ENV_ALLOWED_USERS = "NAPCAT_ALLOWED_USERS"
ENV_ALLOW_ALL_USERS = "NAPCAT_ALLOW_ALL_USERS"
ENV_GROUP_ALLOWED_USERS = "NAPCAT_GROUP_ALLOWED_USERS"
ENV_GROUP_ALLOW_ALL_USERS = "NAPCAT_GROUP_ALLOW_ALL_USERS"
ENV_AUTO_ACCEPT_FRIEND = "NAPCAT_AUTO_ACCEPT_FRIEND"
ENV_AUTO_ACCEPT_GROUP_INVITE = "NAPCAT_AUTO_ACCEPT_GROUP_INVITE"

# ---------------------------------------------------------------------------
# OneBot v11 WebSocket protocol
# ---------------------------------------------------------------------------
# Client roles (X-Client-Role header)
ROLE_UNIVERSAL = "Universal"
ROLE_API = "API"
ROLE_EVENT = "Event"

# API response fields
ONEBOT_STATUS_OK = "ok"
ONEBOT_STATUS_FAILED = "failed"

# ---------------------------------------------------------------------------
# Timeouts (seconds)
# ---------------------------------------------------------------------------
API_RESPONSE_TIMEOUT = 30.0
FILE_DOWNLOAD_TIMEOUT = 30.0
WS_HEARTBEAT = 30.0  # aiohttp WS ping interval
CONNECT_TIMEOUT = 30.0  # how long to wait for first NapCat connection
SERVER_START_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# Message limits
# ---------------------------------------------------------------------------
MAX_MESSAGE_LENGTH = 4000  # characters per chunk (matches qqbot's value)
MESSAGE_INDICATOR_RESERVE = 10  # room for " (XX/XX)" chunk indicator

# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
DEDUP_WINDOW_SECONDS = 5.0
DEDUP_MAX_SIZE = 2000

# ---------------------------------------------------------------------------
# Reconnection (NapCat-side — adapter just keeps the server running)
# ---------------------------------------------------------------------------
# How long to wait for a new NapCat connection before treating the adapter
# as disconnected for the purposes of send() retry.
RECONNECT_WAIT_SECONDS = 15.0

# ---------------------------------------------------------------------------
# OneBot v11 event types
# ---------------------------------------------------------------------------
POST_TYPE_MESSAGE = "message"
POST_TYPE_NOTICE = "notice"
POST_TYPE_REQUEST = "request"
POST_TYPE_META = "meta_event"

MESSAGE_TYPE_PRIVATE = "private"
MESSAGE_TYPE_GROUP = "group"

NOTICE_GROUP_INCREASE = "group_increase"
NOTICE_GROUP_DECREASE = "group_decrease"
NOTICE_GROUP_ADMIN = "group_admin"
NOTICE_GROUP_BAN = "group_ban"

REQUEST_TYPE_FRIEND = "friend"
REQUEST_TYPE_GROUP = "group"

META_HEARTBEAT = "heartbeat"
META_LIFECYCLE = "lifecycle"

# ---------------------------------------------------------------------------
# WebUI
# ---------------------------------------------------------------------------
MAX_LOG_ENTRIES = 500
WEBUI_ROUTE_PREFIX = "/api"
WEBUI_STATIC_DIR = "webui"
