# Hermes-QQ 配置与对接指南

本文档面向不熟悉各个组件的使用者，从零开始讲清楚如何把 NapCat、Hermes-QQ 适配器、Hermes Agent 三者串起来。

## 目录

1. [组件关系](#1-组件关系)
2. [准备工作](#2-准备工作)
3. [安装 NapCatQQ](#3-安装-napcatqq)
4. [安装 Hermes Agent](#4-安装-hermes-agent)
5. [部署 Hermes-QQ 插件](#5-部署-hermes-qq-插件)
6. [配置三方对接](#6-配置三方对接)
7. [启动与验证](#7-启动与验证)
8. [常见问题](#8-常见问题)

---

## 1. 组件关系

你最终会拥有三个东西：

```
你的手机/电脑上的 QQ
        ↕
   NapCatQQ             ← 负责登录 QQ，收发消息
        ↕  (WebSocket)
   Hermes-QQ 插件        ← 负责翻译协议（OneBot ↔ Hermes）
        ↕
   Hermes Agent          ← 负责 AI 对话、调用工具
        ↕
   AI 模型 (Claude / GPT / ...)
```

- **NapCatQQ**：一个运行在你服务器上的程序，它登录你的 QQ 账号，把 QQ 消息转成标准格式（OneBot v11 协议）发送出去，同时接收外部指令来发消息。
- **Hermes-QQ 插件**：我们写的适配器。它启动一个 WebSocket 服务端，等 NapCat 连上来，收到消息后翻译给 Hermes。
- **Hermes Agent**：AI 代理框架，负责调用大模型、执行工具、管理对话。

三者之间的数据流：

```
QQ 用户发消息
  → NapCat 收到消息 → 转成 JSON → 通过 WebSocket 发给插件
  → 插件转成 Hermes 格式 → 交给 Hermes Agent
  → Hermes Agent 调用 AI 模型生成回复
  → 插件把回复通过 WebSocket 发回 NapCat
  → NapCat 在 QQ 里发送回复
```

---

## 2. 准备工作

你需要：

| 条件 | 说明 |
|------|------|
| 一台服务器或电脑 | Linux / Windows / macOS 均可，需要能跑 Python 和 Node.js |
| 一个 QQ 账号 | 用作机器人。**建议用小号**，有封号风险 |
| Python ≥ 3.11 | 运行 Hermes Agent 和插件 |
| Node.js ≥ 18 | 运行 NapCatQQ |
| AI API Key | Claude / OpenAI / 其他兼容的 API Key |

---

## 3. 安装 NapCatQQ

NapCatQQ 是让 QQ 变成机器人的桥梁。

### 3.1 下载安装

根据你的系统选择安装方式：

**Linux（推荐 Docker）：**

```bash
docker run -d \
  --name napcat \
  -p 6099:6099 \
  -v /opt/napcat/config:/app/config \
  -v /opt/napcat/data:/app/data \
  mlikiowa/napcat-docker:latest
```

**或使用一键安装脚本（Linux）：**

```bash
curl -fsSL https://napneko.github.io/install.sh | bash
```

**Windows：**

从 [NapCatQQ Release](https://github.com/NapNeko/NapCatQQ/releases) 下载 exe 安装包。

### 3.2 登录 QQ

启动 NapCat 后，打开浏览器访问 WebUI：

```
http://127.0.0.1:6099/webui
```

初始 token 在启动日志中找 `[WebUi]` 那一行，或者查看 `webui.json`：

```bash
cat /opt/QQ/resources/app/app_launcher/napcat/config/webui.json
# 找到 "token": "xxxxx"
```

在 WebUI 中扫码登录你的机器人 QQ 号。登录成功后，NapCat 就准备好了。

---

## 4. 安装 Hermes Agent

### 4.1 克隆并安装

```bash
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent
uv sync
```

### 4.2 配置 AI 模型

编辑 `~/.hermes/.env`：

```bash
# 以 Claude API 为例
ANTHROPIC_API_KEY=sk-ant-xxx

# 或以 OpenAI 为例
# OPENAI_API_KEY=sk-xxx
```

### 4.3 验证安装

```bash
uv run hermes status
```

如果正常输出版本信息，说明 Hermes 装好了。

---

## 5. 部署 Hermes-QQ 插件

### 5.1 克隆插件仓库

```bash
git clone <hermes-qq-repo-url> hermes-qq
cd hermes-qq
```

### 5.2 部署

```bash
make deploy
```

这会把插件复制到 `~/.hermes/plugins/napcat/`。

### 5.3 启用插件

```bash
cd hermes-agent
uv run hermes plugins enable napcat-platform
```

检查插件是否被识别：

```bash
uv run hermes plugins list
# 应该看到 napcat-platform 显示为 enabled
```

---

## 6. 配置三方对接

这是最关键的一步，需要让三个组件互相知道对方的存在。

### 6.1 总体配置图

```
配置项分布在三个地方：

  NapCat 侧（onebot11_xxx.json）
    └── 告诉 NapCat：去连接 ws://插件地址:端口/onebot

  插件侧（环境变量或 config.yaml）
    └── 告诉插件：在哪个端口监听、用什么 token 验证

  Hermes 侧（config.yaml）
    └── 告诉 Hermes：启用 napcat 平台、配置访问控制
```

### 6.2 配置 NapCat（让它连接插件）

NapCat 的配置文件位于：

```
/opt/QQ/resources/app/app_launcher/napcat/config/onebot11_<你的QQ号>.json
```

编辑它，在 `network.websocketClients` 中添加：

```json
{
  "network": {
    "websocketClients": [
      {
        "name": "hermes",
        "enable": true,
        "url": "ws://127.0.0.1:8080/onebot",
        "token": "my-secret-token",
        "messagePostFormat": "array",
        "reconnectInterval": 3000,
        "heartInterval": 30000
      }
    ]
  }
}
```

各字段含义：

| 字段 | 说明 |
|------|------|
| `name` | 随便起，唯一就行 |
| `enable` | `true` 启用 |
| `url` | **插件 WebSocket 地址**。如果插件和 NapCat 在同一台机器上，用 `127.0.0.1`；如果插件在另一台机器上，写插件那台机器的 IP |
| `token` | 鉴权密码，**必须和插件侧的一致** |
| `messagePostFormat` | `"array"` 推荐，消息用结构化格式 |
| `reconnectInterval` | 断线后多少毫秒重连（3000 = 3 秒） |
| `heartInterval` | 心跳间隔（30000 = 30 秒） |

也可以通过 NapCat WebUI 配置：`网络配置 → 新建 → WebSocket 客户端 → 填入以上参数`。

### 6.3 配置插件（设置监听和鉴权）

**方式一：环境变量（推荐，简单直接）**

```bash
# 在 ~/.hermes/.env 中添加：

NAPCAT_WS_HOST=0.0.0.0       # 监听地址。0.0.0.0 表示接受任何 IP 的连接
NAPCAT_WS_PORT=8080          # 监听端口，要和 NapCat 的 url 中的端口一致
NAPCAT_TOKEN=my-secret-token # 鉴权 token，要和 NapCat 的 token 一致
```

**方式二：config.yaml**

编辑 `~/.hermes/config.yaml`：

```yaml
gateway:
  platforms:
    napcat:
      enabled: true
      extra:
        host: "0.0.0.0"
        port: 8080
        token: "my-secret-token"
```

环境变量和 config.yaml 二选一即可，环境变量优先级更高。

### 6.4 配置访问控制（必须！）

不配置访问控制，任何人都不能使用机器人。

**只允许特定用户（推荐）：**

```bash
# 在 ~/.hermes/.env 中添加
NAPCAT_ALLOWED_USERS=123456789,987654321
```

**允许所有人（仅限内网测试）：**

```bash
NAPCAT_ALLOW_ALL_USERS=true
```

**全局放行（如果有多个平台，不推荐）：**

```bash
GATEWAY_ALLOW_ALL_USERS=true
```

### 6.5 三端对照检查

| 配置项 | NapCat 侧 | 插件侧 | 必须一致？ |
|--------|----------|--------|-----------|
| 地址 | `url: "ws://IP:8080/onebot"` | `NAPCAT_WS_HOST=0.0.0.0` / `NAPCAT_WS_PORT=8080` | IP 可达，端口一致 |
| Token | `token: "xxx"` | `NAPCAT_TOKEN=xxx` | **必须完全一致** |
| 路径 | `/onebot` | 固定 `/onebot` | 不需要配，固定值 |

---

## 7. 启动与验证

### 7.1 启动顺序

```
1. NapCatQQ  ← 先启动，登录 QQ
2. Hermes Gateway ← 后启动，启动 WS 服务端等 NapCat 连接
```

### 7.2 启动 NapCat

```bash
# Docker
docker start napcat

# 或 Linux 一键安装
napcat start
```

确认 NapCat 已登录且 WebUI 可访问：`http://127.0.0.1:6099/webui`。

### 7.3 启动 Hermes Gateway

```bash
cd hermes-agent
uv run hermes gateway start
```

### 7.4 检查连接

查看 gateway 日志，应该看到：

```
[NapCat] WS server listening on ws://0.0.0.0:8080/onebot
[NapCat] Token authentication enabled
```

稍等几秒（NapCat 自动连接），应该看到：

```
[NapCat] Client connected: self_id=123456789 role=Universal
```

如果没看到 `Client connected`，说明 NapCat 没连上，参考[常见问题](#8-常见问题)。

### 7.5 功能测试

**WebUI：**

浏览器访问 `http://<服务器IP>:8080/`，打开管理面板。仪表盘应显示连接状态、消息计数等信息。

**健康检查：**

```bash
curl http://localhost:8080/health
# {"status": "ok", "connections": 1, "self_ids": ["123456789"]}
```

- `status: "ok"` — 有 NapCat 连接
- `status: "waiting"` — 服务端在等 NapCat 来连
- `connections: 0` — 还没 NapCat 连上来

**发消息测试：**

用另一个 QQ 号（非机器人自己），给机器人发 "你好"。

- **私聊**：直接发
- **群聊**：@机器人 或直接发（取决于配置）

如果收到 AI 回复，对接成功。

---

## 8. 常见问题

### NapCat 连不上

**现象**：gateway 日志没有 `Client connected`，health 接口显示 `status: waiting`。

**排查：**

```bash
# 1. 确认插件端口在监听
curl http://127.0.0.1:8080/health
# 如果连不上，说明 gateway 没启动或端口配错了

# 2. 确认端口没被占用
lsof -i :8080

# 3. 确认 NapCat 配置的 url 能访问到插件
# NapCat 在另一台机器？检查防火墙：
#   - 插件机器：放行 8080 端口
#   - NapCat 配置里 url 写插件机器的实际 IP（不能写 127.0.0.1）

# 4. 检查 token 是否一致
# 插件侧：echo $NAPCAT_TOKEN
# NapCat 侧：看 websocketClients 配置里的 token
```

### Token 不匹配

**现象**：gateway 日志出现 `Token mismatch`，NapCat 反复断线重连。

**解决**：确保 NapCat 配置里的 `token` 和插件的 `NAPCAT_TOKEN` 完全一致。注意不要有多余空格。

### 消息发不出去

**现象**：能收到消息，但 AI 回复发不出去。

**排查：**

```bash
# 1. 检查 NapCat 是否还连着
curl http://localhost:8080/health

# 2. 查看详细日志
HERMES_LOG_LEVEL=DEBUG uv run hermes gateway start
# 搜索 [NapCat] 相关的日志

# 3. 确认 AI API Key 配置正确
cat ~/.hermes/.env | grep API_KEY
```

### 消息收不到

**现象**：QQ 发了消息，gateway 日志完全没反应。

**排查：**

1. 确认 NapCat 已连上（health 接口 connections > 0）
2. 确认访问控制：检查 `NAPCAT_ALLOWED_USERS` 是否包含发消息的 QQ 号
3. 如果两者都没配，所有消息都会被拒绝（见第 6.4 节）
4. 确认发的不是机器人自己（机器人自己发的消息会被过滤）

### 重启 NapCat 后连不上

NapCat 重启后会自动重连（`reconnectInterval` 配置的重连间隔）。如果长时间连不上：

1. 确认 Hermes gateway 还在运行
2. 确认插件端口没有被重启后的其他进程占用
3. 如果换过机器，检查 IP 地址是否变了

### 如何看更详细的日志

```bash
# 启动时加日志级别
HERMES_LOG_LEVEL=DEBUG uv run hermes gateway start

# 或者
export HERMES_LOG_LEVEL=DEBUG
uv run hermes gateway start
```

DEBUG 级别会输出每条消息的详细内容，适合排查协议层面的问题。

---

## 附：完整配置示例

### ~/.hermes/.env

```bash
# AI 模型
ANTHROPIC_API_KEY=sk-ant-xxx

# NapCat 插件
NAPCAT_WS_HOST=0.0.0.0
NAPCAT_WS_PORT=8080
NAPCAT_TOKEN=my-secret-token

# 访问控制
NAPCAT_ALLOWED_USERS=123456789,987654321       # 白名单（哪些人可用）
# NAPCAT_ALLOW_ALL_USERS=true                  # 全放行
# NAPCAT_GROUP_ALLOWED_USERS=111222333         # 群白名单（哪些群可用，可选）
```

### NapCat onebot11_<QQ号>.json（关键部分）

```json
{
  "network": {
    "websocketClients": [
      {
        "name": "hermes",
        "enable": true,
        "url": "ws://127.0.0.1:8080/onebot",
        "token": "my-secret-token",
        "messagePostFormat": "array",
        "reconnectInterval": 3000,
        "heartInterval": 30000
      }
    ]
  }
}
```

### ~/.hermes/config.yaml（可选，环境变量也能完成配置）

```yaml
gateway:
  platforms:
    napcat:
      enabled: true
      extra:
        host: "0.0.0.0"
        port: 8080
        token: "my-secret-token"
        auto_accept_friend: true
        auto_accept_group_invite: true
```
