# Hermes-QQ 开发指南

## 目录

1. [协议概述](#1-协议概述)
2. [组件架构](#2-组件架构)
3. [连接生命周期](#3-连接生命周期)
4. [消息处理流程](#4-消息处理流程)
5. [如何扩展](#5-如何扩展)
6. [故障排查](#6-故障排查)

## 1. 协议概述

### OneBot v11 反向 WebSocket

NapCat 作为 **WS 客户端** 主动连接我们的服务端。

**连接建立时 NapCat 发送的 HTTP 升级请求：**

```
GET /onebot HTTP/1.1
Host: 127.0.0.1:8080
Upgrade: websocket
X-Self-ID: 123456789      # 机器人 QQ 号
X-Client-Role: Universal   # Universal | API | Event
Authorization: my-secret   # 鉴权 token
```

**连接建立后，所有数据以 JSON 帧传递：**

- 事件（NapCat → 我们）：`{"post_type":"message", "message_type":"private", ...}`
- API 请求（我们 → NapCat）：`{"action":"send_msg", "params":{...}, "echo":"uuid"}`
- API 响应（NapCat → 我们）：`{"status":"ok", "retcode":0, "data":{...}, "echo":"uuid"}`

### 消息格式

OneBot 支持两种消息格式：

**CQ Code 字符串：**
```
[CQ:reply,id=-123]你好 [CQ:image,file=pic.jpg,url=https://...]
```

**Array 分段（推荐）：**
```json
[
  {"type": "reply", "data": {"id": "-123"}},
  {"type": "text",  "data": {"text": "你好 "}},
  {"type": "image", "data": {"file": "pic.jpg", "url": "https://..."}}
]
```

## 2. 组件架构

```
src/napcat/
├── adapter.py            ← 主类 + 生命周期管理 + register() 入口
├── onebot_client.py      ← WS 连接管理 + API 请求/响应协程
├── onebot_event.py       ← 事件解析（OneBot JSON → MessageEvent）
├── onebot_api.py         ← API 封装（send_msg, kick, mute, ...）
├── tools.py              ← QQ 工具注册（供 AI 调用）
├── webui_routes.py       ← WebUI API 路由（/api/status, /api/logs, ...）
├── webui/
│   └── index.html        ← WebUI 单页前端
├── constants.py          ← 全局常量
└── plugin.yaml           ← 插件清单
```

### adapter.py — NapCatAdapter

继承 `BasePlatformAdapter`，是整个适配器的入口。

```
connect()
  ├── 启动 aiohttp WS server
  ├── 注册 /onebot 路由 → _handle_ws
  ├── 注册 /health 路由 → _handle_health
  └── 注册 WebUI 路由（/api/*）+ 静态文件（/）

disconnect()
  ├── 关闭所有 WS 连接
  └── 停止 aiohttp server

send(chat_id, content, reply_to, metadata)
  ├── 解析 chat_id → (chat_type, target_id)
  ├── 分片（超 4000 字符自动切分）
  ├── 构建 OneBot 消息（含回复引用）
  └── 调用 onebot_api 发送

_handle_ws(request)
  ├── 验证 Token
  ├── 提取 X-Self-ID + X-Client-Role
  ├── 注册到 OneBotClientManager
  └── 进入 receive loop
```

### onebot_client.py — OneBotClientManager

管理 1+ NapCat 实例的 WS 连接。

```
add_client(ws, self_id, role)
  ├── 注册连接（self_id → ClientInfo）
  └── 替换旧连接（同 self_id）

remove_client(self_id)
  ├── 注销连接
  └── 失败所有挂起的 API 响应

send_action(action, params, self_id)
  ├── 生成 echo UUID
  ├── 发送 JSON 请求帧
  ├── 注册 Future 等待响应
  └── 超时 30s → TimeoutError

route_message(payload, self_id)
  ├── "echo" + "status" → API 响应 → resolve Future
  ├── "post_type" → 事件 → dispatch to event handler
  └── 其他 → debug log + ignore
```

### onebot_event.py — OneBotEventParser

将 OneBot v11 JSON 事件转换为 Hermes MessageEvent。

```
parse(payload, self_id)
  ├── post_type=message    → _parse_message
  ├── post_type=notice     → _parse_notice
  ├── post_type=request    → _parse_request
  └── post_type=meta_event → _parse_meta (heartbeat/lifecycle → ignore)

_parse_message(payload, self_id)
  ├── 去重检查（message_id + TTL）
  ├── 自消息过滤（user_id == self_id）
  ├── 解析消息内容 → 文本 + 图片 URL + 语音 URL + 回复引用
  ├── 构建 SessionSource（含 chat_id, user_id, chat_type）
  └── 构建 MessageEvent
```

### onebot_api.py — OneBotAPI

封装所有 OneBot v11 API，每个方法对应一个 OneBot action。

| 方法 | OneBot Action |
|------|--------------|
| `send_private_msg` | `send_private_msg` |
| `send_group_msg` | `send_group_msg` |
| `get_group_info` | `get_group_info` |
| `get_group_member_info` | `get_group_member_info` |
| `set_group_kick` | `set_group_kick` |
| `set_group_ban` | `set_group_ban` |
| `set_group_whole_ban` | `set_group_whole_ban` |
| `set_group_admin` | `set_group_admin` |
| `set_friend_add_request` | `set_friend_add_request` |
| `set_group_add_request` | `set_group_add_request` |

### webui_routes.py — WebUI API

在 `connect()` 时注册到 aiohttp app，提供四个管理端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 状态 JSON（连接、计数、配置摘要） |
| `/api/logs` | GET | 分页消息日志（支持 direction/chat_type 筛选） |
| `/api/config` | GET | 读取当前配置（含来源标注） |
| `/api/config` | POST | 写入配置 overrides（内存生效，重启丢失） |
| `/api/chat/ws` | WS | 对话测试 WebSocket |

静态文件 `/` 指向 `webui/index.html`（纯 HTML + vanilla JS）。

## 3. 连接生命周期

```
Hermes Gateway 启动
  │
  ├── discover_plugins()        ← 扫描 ~/.hermes/plugins/
  │   └── 发现 napcat-platform
  │       └── register(ctx)     ← ctx.register_platform()
  │
  ├── _create_adapter("napcat") ← platform_registry → adapter_factory
  │   └── NapCatAdapter.__init__()
  │
  └── adapter.connect()
      ├── 启动 aiohttp WS server (host:port)
      ├── _mark_connected()
      └── 等待 NapCat 连接...

NapCat 连接
  │
  └── WS → /onebot
      ├── _handle_ws()
      │   ├── 验证 token
      │   ├── 注册 client (self_id → manager)
      │   └── receive loop
      │       ├── JSON 帧 → route_message()
      │       ├── event → parse → MessageEvent → handle_message()
      │       └── response → resolve Future
      │
      └── NapCat 断开 → remove_client() → fail pending

Hermes Gateway 停止
  │
  └── adapter.disconnect()
      ├── close_all() WS 连接
      ├── _cleanup_server()
      └── _mark_disconnected()
```

## 4. 消息处理流程

### 入站（QQ → AI）

```
QQ 用户发消息
  → NapCat 接收
  → 转为 OneBot JSON
  → WS 帧发送到适配器
  → _handle_ws receive loop
  → route_message()
  → OneBotEventParser.parse()
  → MessageEvent 构建
  → adapter.handle_message(event)
  → GatewayRunner._handle_message_with_agent()
  → LLM API 调用
  → AI 生成回复
```

### 出站（AI → QQ）

```
AI 生成回复
  → GatewayRunner.send_response()
  → adapter.send(chat_id, content, reply_to)
  → OneBotAPI.send_msg() / send_group_msg()
  → client_manager.send_action()
  → WS 帧发送到 NapCat
  → NapCat 调用 QQ 发送
  → 用户在 QQ 看到回复
```

## 5. 如何扩展

### 添加新的 CQ 类型支持

编辑 `src/napcat/onebot_event.py`：

```python
# 在 _handle_cq() 和 _handle_segment() 中添加分支
elif cq_type == "my_type":
    # 处理逻辑
    pass
```

### 添加新的 QQ 工具

编辑 `src/napcat/tools.py`：

```python
# 1. 定义 schema
MY_TOOL_SCHEMA = {"type": "object", "properties": {...}}

# 2. 实现 handler
async def my_tool(ctx, param1: int, param2: str) -> dict:
    api = _get_api()
    result = await api.some_action(param1=param1, param2=param2)
    return {"success": True, "data": result}

# 3. 在 register_tools() 中注册
ctx.register_tool(
    name="qq_my_tool",
    toolset="napcat",
    schema=MY_TOOL_SCHEMA,
    handler=my_tool,
)
```

### 添加新的 OneBot API

编辑 `src/napcat/onebot_api.py`：

```python
async def some_new_action(self, param: str = "", self_id=None) -> dict:
    return await self._cm.send_action(
        "some_new_action", {"param": param}, self_id=self_id
    )
```

### 调整消息分片长度

编辑 `src/napcat/constants.py`，修改 `MAX_MESSAGE_LENGTH`。

## 6. 故障排查

### NapCat 连不上

- 检查 Hermes gateway 日志：`[NapCat] WS server listening on ws://...`
- 检查端口是否被占用：`lsof -i :8080`
- 检查 NapCat 日志中的 WS 连接状态
- 检查 token 是否匹配（`NAPCAT_TOKEN` 与 NapCat 配置的 `token`）
- 网络连通性：如果 NapCat 在远程，确保 `ws://host:port` 可达

### 消息收不到

- 检查 gateway 日志是否有 `[NapCat] Client connected`
- 检查访问控制：`NAPCAT_ALLOWED_USERS` 是否包含发消息的 QQ 号
- 检查是否为自消息被过滤（机器人自己发的消息会被跳过）
- 检查去重：短时间重复发送相同消息会被过滤

### AI 回复发不出去

- 检查 gateway 日志是否有 OneBot API 错误
- 检查消息长度是否超过 4000 字符（会自动分片）
- 检查 NapCat 是否仍在线

### 日志级别

设置 `HERMES_LOG_LEVEL=DEBUG` 查看详细日志：

```bash
HERMES_LOG_LEVEL=DEBUG hermes gateway start
```

会输出每一条 NapCat 事件的详细内容。

### 查看健康状态

```bash
curl http://localhost:8080/health
```

返回：

```json
{"status": "ok", "connections": 1, "self_ids": ["123456789"]}
```

`status` 为 `"waiting"` 表示没有 NapCat 连接，但服务端正在监听。
