# Hermes-QQ

NapCat / OneBot v11 平台适配器，让 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 接入 QQ，充当聊天机器人和 AI 助手。

## 架构

```
QQ ↔ NapCatQQ ↔ [Reverse WebSocket] ← NapCatAdapter (WS Server) → Hermes Gateway → AI
```

- **NapCatQQ** 作为 WebSocket 客户端连接我们的适配器
- **适配器** 运行 aiohttp WebSocket 服务端，负责协议转换
- **Hermes Gateway** 处理 AI 对话、工具调用等

## 功能

- 私聊 / 群聊文本收发
- 图片接收与发送
- 语音接收（STT 转文字）
- 回复引用（AI 看到上下文）
- 消息分片（超长自动切分）
- 访问控制（白名单 / 全允许）
- Token 鉴权
- 好友申请 / 群邀请自动处理
- 群管理工具（踢人、禁言、全员禁言、设置管理、查成员、查群信息）
- 嵌入式 WebUI（仪表盘、消息日志、配置管理、对话测试）

## 快速开始

### 1. 环境要求

- Python ≥ 3.11
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) 已安装
- [NapCatQQ](https://github.com/NapNeko/NapCatQQ) 已安装并登录
- aiohttp（`pip install aiohttp` 或 `uv add aiohttp`）

### 2. 部署插件

```bash
git clone https://github.com/your-org/hermes-qq.git
cd hermes-qq
make deploy
```

### 3. 启用插件

```bash
hermes plugins enable napcat-platform
```

### 4. 配置环境变量

```bash
export NAPCAT_WS_HOST=0.0.0.0     # WebSocket 服务端监听地址
export NAPCAT_WS_PORT=8080        # WebSocket 服务端端口
export NAPCAT_TOKEN=my-secret     # 与 NapCat 配置一致的鉴权 token

# 访问控制（可选）
export NAPCAT_ALLOWED_USERS=123456,789012         # 用户白名单（QQ 号，逗号分隔）
export NAPCAT_GROUP_ALLOWED_USERS=555666777       # 群白名单（群号，逗号分隔）
export NAPCAT_ALLOW_ALL_USERS=false               # 设为 true 允许所有人

# 自动处理请求（可选，默认均为 true）
export NAPCAT_AUTO_ACCEPT_FRIEND=true
export NAPCAT_AUTO_ACCEPT_GROUP_INVITE=true
```

也可以在 Hermes 的 `config.yaml` 中配置（环境变量优先）：

```yaml
gateway:
  platforms:
    napcat:
      enabled: true
      extra:
        host: "0.0.0.0"
        port: 8080
        token: "my-secret"
        auto_accept_friend: true
        auto_accept_group_invite: true
```

### 5. 配置 NapCat

编辑 NapCat 的 `onebot11_<qq号>.json` 配置文件：

```json
{
  "websocketClients": [
    {
      "name": "hermes",
      "enable": true,
      "url": "ws://127.0.0.1:8080/onebot",
      "token": "my-secret",
      "messagePostFormat": "array",
      "reconnectInterval": 3000,
      "heartInterval": 30000
    }
  ]
}
```

### 6. 启动

```bash
hermes gateway start
```

查看日志确认连接：

```
[NapCat] WS server listening on ws://0.0.0.0:8080/onebot
[NapCat] Client connected: self_id=123456789 role=Universal
```

### 7. 测试

从 QQ 给机器人发一条私聊消息 "你好"，应该能收到 AI 回复。

## 项目结构

```
hermes-qq/
├── src/napcat/
│   ├── plugin.yaml          # 插件元数据
│   ├── __init__.py           # 导出 register()
│   ├── adapter.py            # NapCatAdapter 主类 + register() 入口
│   ├── constants.py          # 常量
│   ├── onebot_client.py      # WebSocket 连接管理器
│   ├── onebot_event.py       # OneBot 事件 → MessageEvent 解析
│   ├── onebot_api.py         # OneBot API 封装
│   ├── tools.py              # QQ 群管理工具
│   ├── webui_routes.py       # WebUI API 路由
│   └── webui/
│       └── index.html        # WebUI 前端
├── Makefile                  # 部署脚本
├── README.md
├── USER_GUIDE.md
├── GUIDE.md
└── SETUP_GUIDE.md
```

## 开发

```bash
# 修改源码（src/napcat/ 下的文件）
vim src/napcat/adapter.py

# 重新部署
make deploy

# 重启 gateway
hermes gateway restart
```

## 工具列表

| 工具名 | 功能 | 所需权限 |
|--------|------|---------|
| `qq_kick` | 踢出群成员 | 管理员 |
| `qq_mute` | 禁言群成员 | 管理员 |
| `qq_mute_all` | 全员禁言 | 管理员 |
| `qq_set_admin` | 设置/取消管理员 | 群主 |
| `qq_get_member_info` | 查询群成员信息 | 无 |
| `qq_get_group_info` | 查询群信息 | 无 |

AI 可以在对话中自动调用这些工具，例如用户说 "帮我把那个发广告的踢了"，AI 会调用 `qq_kick`。

## 许可证

MIT
