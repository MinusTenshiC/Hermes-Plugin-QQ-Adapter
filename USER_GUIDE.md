# Hermes-QQ 使用指南

部署完成后，Hermes AI 就已经接入 QQ 了。本文档介绍如何使用各个功能。

## 目录

1. [基础使用](#1-基础使用)
2. [斜杠命令](#2-斜杠命令)
3. [群管理工具](#3-群管理工具)
4. [图片与语音](#4-图片与语音)
5. [访问控制](#5-访问控制)
6. [WebUI 管理面板](#6-webui-管理面板)
7. [配置参考](#7-配置参考)

---

## 1. 基础使用

### 私聊

在 QQ 里直接给机器人发消息即可，就像跟一个普通好友聊天：

```
你: 你好
机器人: 你好！有什么可以帮你的？

你: 帮我写一段 Python 代码，计算斐波那契数列
机器人: [返回代码]

你: 解释一下这段代码
机器人: [解释逻辑]
```

机器人有完整的上下文记忆，同一个私聊对话里它会记得之前聊过的内容。

### 群聊

把机器人拉进群，群成员都可以跟它互动：

```
群友 A: @机器人 今天天气怎么样
机器人: 我无法获取实时天气，但可以帮你搜索。需要我搜索吗？

群友 B: @机器人 帮我翻译成英文：今天天气很好
机器人: The weather is great today.
```

机器人能识别 @ 提及，也会收到群里的系统通知（有人进群、退群、被禁言等）。

### 回复引用

在 QQ 里长按某条消息选择"引用"再回复，机器人能看到你引用的内容，理解上下文：

```
群友 A: Python 和 Go 哪个适合做 Web 后端？
群友 B: [引用 A 的消息] 都很好，看你需求
机器人: [引用 B 的消息] 补充一下：Python 生态更丰富，Go 性能更强...
```

---

## 2. 斜杠命令

在私聊或群聊中发送以下命令，机器人会立即响应（不经过 AI 思考）：

| 命令 | 作用 |
|------|------|
| `/new` | 开始新对话，清除之前的记忆 |
| `/reset` | 同 /new |
| `/stop` | 停止当前正在生成的回复 |
| `/status` | 查看当前会话状态 |

示例：

```
你: /new
机器人: 已开始新会话。

你: /status
机器人: 当前会话: user_123456789 | 消息数: 3 | 工具调用: 1
```

---

## 3. 群管理工具

AI 可以在对话中自动调用 QQ 管理功能。所有工具都需要机器人有对应的群权限。

### 踢人 — `qq_kick`

```
群主: 把 987654321 踢出去，他在发广告
机器人: [调用 qq_kick 工具]
机器人: 已将 987654321 踢出群。

# 也可以禁止此人重新加群
群主: 把 987654321 踢了，别让他再加进来
机器人: [调用 qq_kick 设置 reject_add_request=true]
```

### 禁言 — `qq_mute`

```
管理员: 把 987654321 禁言 10 分钟
机器人: [调用 qq_mute duration=600]
机器人: 已将 987654321 禁言 600 秒。

管理员: 把 987654321 解除禁言
机器人: [调用 qq_mute duration=0]
机器人: 已解除 987654321 的禁言。
```

禁言时长单位是**秒**，设为 0 解禁，默认 1800 秒（30 分钟）。

### 全员禁言 — `qq_mute_all`

```
管理员: 开启全员禁言
机器人: [调用 qq_mute_all enable=true]
机器人: 已开启全员禁言。

管理员: 关闭全员禁言
机器人: [调用 qq_mute_all enable=false]
机器人: 已关闭全员禁言。
```

### 设置管理员 — `qq_set_admin`

```
群主: 把 987654321 设置为管理员
机器人: [调用 qq_set_admin enable=true]
机器人: 已将 987654321 设为管理员。

群主: 取消 987654321 的管理员
机器人: [调用 qq_set_admin enable=false]
```

### 查询成员信息 — `qq_get_member_info`

```
管理员: 查一下 987654321 在群里的信息
机器人: [调用 qq_get_member_info]
机器人: 用户 987654321
  昵称: 小明
  群名片: 小明-技术部
  角色: member
  入群时间: 2025-03-15
```

返回信息包括：QQ 号、昵称、群名片、角色（owner/admin/member）、入群时间、最后发言时间。

### 查询群信息 — `qq_get_group_info`

```
任何人: 这个群有多少人？
机器人: [调用 qq_get_group_info]
机器人: 群名称: 技术交流群
  群号: 123456789
  成员数: 256
  最大成员数: 500
```

---

## 4. 图片与语音

### 发送图片给机器人

在 QQ 中直接发图片给机器人（私聊或群聊），机器人能"看到"图片内容：

```
你: [发了一张代码截图]
你: 这段代码有什么问题？
机器人: [分析图中代码]
```

### 机器人发送图片

当 AI 生成图表、截图等内容时，会自动以图片形式发送到 QQ。

### 语音消息

在 QQ 中给机器人发语音消息，机器人会通过 STT（语音转文字）转换成文本后再理解：

```
你: [发送语音："帮我查一下今天的天气"]
机器人: 我无法获取实时天气，需要我帮你搜索吗？
```

语音转录优先级：
1. QQ 内置 ASR（免费，NapCat 自动提供）
2. 配置的第三方 STT 服务（需额外配置）

---

## 5. 访问控制

### 决策流程

收到消息后，按以下顺序判断是否放行：

```
1. NAPCAT_ALLOW_ALL_USERS=true  →  直接放行
2. DM 配对白名单                →  放行
3. NAPCAT_ALLOWED_USERS 含此用户  →  放行
4. GATEWAY_ALLOWED_USERS 含此用户 →  放行
5. 以上全部为空                  →  检查 GATEWAY_ALLOW_ALL_USERS
   GATEWAY_ALLOW_ALL_USERS=true  →  放行（全局）
   GATEWAY_ALLOW_ALL_USERS 未设  →  拒绝

群聊额外检查（在转发给 AI 之前）：
  NAPCAT_GROUP_ALLOWED_USERS 已配置 → 仅群号在列表内的放行
  NAPCAT_GROUP_ALLOWED_USERS 未配置 → 跳过此检查（所有群放行）
```

### 三种模式

| NAPCAT_ALLOWED_USERS | NAPCAT_ALLOW_ALL_USERS | 效果 |
|---------------------|------------------------|------|
| 空 | `false` / 未设 | **所有人被拒绝**（除非设了 `GATEWAY_ALLOW_ALL_USERS=true`） |
| `123,456` | `false` / 未设 | 仅 QQ 号 123 和 456 可用 |
| 任意 | `true` | 所有人可用 |

> **注意**：如果两个都不设，gateway 启动时会打印 WARNING，且默认**拒绝所有消息**。生产环境务必至少配置其中一项。

### 白名单模式

只允许指定的 QQ 号使用机器人：

```bash
export NAPCAT_ALLOWED_USERS=123456789,987654321
```

不在白名单中的用户发消息会被静默忽略。

### 全允许模式

允许所有人使用（**公网部署不推荐**）：

```bash
export NAPCAT_ALLOW_ALL_USERS=true
```

### 全局放行

如果部署了多个平台，可以用全局变量统一放行：

```bash
export GATEWAY_ALLOW_ALL_USERS=true
```

但这样是**所有平台**全部放行，不够精细。推荐按平台配置。

### 群聊单独控制

如果只想在特定群启用机器人，可以设置群白名单：

```bash
# 只允许这些群号（逗号分隔）
export NAPCAT_GROUP_ALLOWED_USERS=555666777,888999000

# 使用 * 允许所有群（与不设置效果相同）
export NAPCAT_GROUP_ALLOWED_USERS=*
```

设置后，只有群号在该列表中的群消息会被机器人处理，其他群的消息会被静默忽略。私聊不受此变量影响。

> **注意**：QQ 的用户号和群号共用同一套数字空间，"123456" 可能既是一个用户的 QQ 号，也是一个群号。因此 `NAPCAT_ALLOWED_USERS`（控制哪些**人**能用）和 `NAPCAT_GROUP_ALLOWED_USERS`（控制哪些**群**能用）是两个独立变量，各管各的，避免混淆。

### 好友申请

```bash
# 自动通过好友申请（默认 true）
export NAPCAT_AUTO_ACCEPT_FRIEND=false   # 改为手动处理

# 自动接受群邀请（默认 true）
export NAPCAT_AUTO_ACCEPT_GROUP_INVITE=false
```

关闭自动处理后，好友申请和群邀请会以系统消息的形式通知你，由你决定是否通过。

---

## 6. WebUI 管理面板

启动 Hermes Gateway 后，浏览器访问 `http://<服务器IP>:8080/` 即可打开 WebUI。

### 仪表盘

首页展示系统运行概况：连接状态（绿点=已连接，黄点=等待中）、在线 QQ 号、运行时长、收/发消息计数、API 错误次数、工具调用次数、每连接详情（QQ 号、角色、在线时长、上次事件时间）。页面每 10 秒自动刷新。

### 消息日志

按方向（入站/出站）和类型（私聊/群聊）筛选最近 500 条消息，支持分页浏览。每条记录显示时间、方向、聊天类型、聊天 ID、发送者、消息摘要。

### 配置管理

在线查看和修改以下配置，保存后立即生效（内存修改，网关重启后恢复为 `.env` 中的值）：

- `NAPCAT_ALLOWED_USERS` — 用户白名单
- `NAPCAT_GROUP_ALLOWED_USERS` — 群白名单
- `NAPCAT_ALLOW_ALL_USERS` — 全放行开关
- `NAPCAT_AUTO_ACCEPT_FRIEND` — 自动通过好友申请
- `NAPCAT_AUTO_ACCEPT_GROUP_INVITE` — 自动接受群邀请

每项配置显示当前生效值及其来源（env / override / default）。只读项（host、port、token）需重启网关修改。

### 对话测试

在浏览器中直接与 AI 对话，模拟 QQ 私聊或群聊场景。通过 WebSocket 连接，输入消息后 AI 回复会实时显示。适合快速验证 AI 是否正常工作，无需打开 QQ。

---

## 7. 配置参考

### 环境变量一览

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NAPCAT_WS_HOST` | `0.0.0.0` | WS 服务端监听地址 |
| `NAPCAT_WS_PORT` | `8080` | WS 服务端端口 |
| `NAPCAT_TOKEN` | — | 与 NapCat 一致的鉴权 token |
| `NAPCAT_ALLOWED_USERS` | — | 允许的用户 QQ 号（逗号分隔） |
| `NAPCAT_GROUP_ALLOWED_USERS` | — | 允许的群号（逗号分隔，`*` = 全部放行） |
| `NAPCAT_ALLOW_ALL_USERS` | `false` | 允许所有人（私聊+群聊） |
| `NAPCAT_AUTO_ACCEPT_FRIEND` | `true` | 自动通过好友申请 |
| `NAPCAT_AUTO_ACCEPT_GROUP_INVITE` | `true` | 自动接受群邀请 |

### config.yaml 示例

```yaml
gateway:
  platforms:
    napcat:
      enabled: true
      extra:
        host: "127.0.0.1"
        port: 8080
        token: "my-secret-token"
        auto_accept_friend: true
        auto_accept_group_invite: true
```

环境变量优先级高于 config.yaml。

### NapCat 配置

NapCat 的 `onebot11_<QQ号>.json` 参考配置：

```json
{
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
```

关键字段：
- `url`：指向 Hermes 的 WebSocket 地址
- `token`：必须与 `NAPCAT_TOKEN` 一致
- `messagePostFormat`：推荐 `"array"`（分段格式，解析更准确）
- `reconnectInterval`：断线重连间隔（毫秒），推荐 3000-5000
