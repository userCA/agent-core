# HTTP SSE API 规范

> Base URL: `http://{host}:{port}`  
> 默认端口: `8000`  
> 框架: FastAPI + SSE (Server-Sent Events)

---

## 1. 对话流（核心）

### POST `/chat/stream`

发送消息并接收 SSE 流式响应。

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string | 否 | 会话 ID，不传则自动创建 |
| `persona_id` | string | 否 | 角色/专家 ID |

**Request Body:**

```json
{
  "message": "你好，帮我写一段代码",
  "provider": "openai",    // 可选，模型提供商
  "model": "gpt-4o"        // 可选，模型 ID
}
```

**Request Headers (透传):**

| Header | 说明 |
|--------|------|
| `uid` | 用户 ID（用于 Companion 系统） |
| `deviceid` | 设备 ID（AIGC 鉴权） |
| `channel` | 渠道标识（AIGC 鉴权） |
| `pacmtoken` | 鉴权 Token（AIGC 鉴权） |

**Response:** `text/event-stream`

SSE 事件格式统一为 `data: {JSON}\n\n`，每条事件都有 `event` 字段标识类型。

---

### SSE 事件类型

#### `session_id` — 会话标识（首个事件）

```json
{"event": "session_id", "session_id": "scene-1780069413346"}
```

#### `text_delta` — 文本流式输出

```json
{"event": "text_delta", "text": "你好"}
```

逐 token 推送 assistant 回复文本。

#### `thinking_delta` — 思考过程流式输出

```json
{"event": "thinking_delta", "text": "让我想想..."}
```

模型 thinking/reasoning 内容（仅部分模型支持）。

#### `tool_start` — 工具开始执行

```json
{
  "event": "tool_start",
  "tool_name": "read_file",
  "tool_call_id": "call_abc123",
  "args": {"path": "/src/main.py"}
}
```

#### `tool_update` — 工具执行中间更新

```json
{
  "event": "tool_update",
  "tool_name": "bash",
  "result": "正在执行命令..."
}
```

#### `tool_end` — 工具执行完成

```json
{
  "event": "tool_end",
  "tool_name": "read_file",
  "tool_call_id": "call_abc123",
  "result": "文件内容...",
  "is_error": false,
  "display": {"type": "image", "url": "..."}  // 可选，富媒体展示
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_name` | string | 工具名 |
| `tool_call_id` | string | 调用 ID |
| `result` | string | 结果文本 |
| `is_error` | boolean | 是否出错 |
| `display` | object? | 可选，富媒体展示数据（图片、音频、widget 等） |

#### `human_input_required` — 需要用户输入

```json
{
  "event": "human_input_required",
  "tool_call_id": "call_xyz789",
  "prompt": "请确认是否执行此操作？",
  "input_schema": {
    "type": "object",
    "properties": {
      "confirm": {"type": "boolean", "description": "是否确认"}
    }
  }
}
```

收到此事件后，前端展示交互表单，用户填写后调用 `POST /human-input` 恢复执行。

#### `message_end` — 消息完成

```json
{
  "event": "message_end",
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 350,
    "total_tokens": 1550
  }
}
```

#### `error` — 错误

```json
{"event": "error", "message": "Request timed out"}
```

#### `done` — 流结束（最后一个事件）

```json
{"event": "done"}
```

#### Companion 事件（仅当 `uid` header 存在时）

**`companion`** — 宠物状态变更:

```json
{
  "event": "companion",
  "type": "happy",          // "ear_perk" | "busy" | "happy" | "sleeping" | "concerned" | "emotion"
  "uid": "user_123",
  "emotion": "joyful",
  "eye_override": "sparkle",
  "frontend_mood": "awake"
}
```

**`companion_bubble`** — 宠物气泡消息:

```json
{
  "event": "companion_bubble",
  "uid": "user_123",
  "text": "加油！",
  "ttl_ms": 5000,
  "priority": "normal"
}
```

---

### SSE 事件完整时序

```
session_id          ← 必定首个
text_delta          ← 0~N 次（文本流）
thinking_delta      ← 0~N 次（思考流，穿插在文本间）
tool_start          ← 工具调用开始
tool_update         ← 0~N 次（执行中更新）
tool_end            ← 工具调用结束
human_input_required← 0~1 次（需用户输入时）
text_delta          ← 工具结果后继续输出
message_end         ← 一轮完成，含 usage
companion           ← 穿插在流中（宠物状态）
companion_bubble    ← 穿插在流中（宠物气泡）
error               ← 出错时（替代正常流程）
done                ← 必定最后
```

---

## 2. 会话管理

### POST `/human-input`

提供用户输入，恢复暂停的工具执行。

**Query:** `session_id` (必填)

**Body:**
```json
{
  "tool_call_id": "call_xyz789",
  "values": {"confirm": true}
}
```

**Response:**
```json
{"success": true}
```

---

### POST `/abort`

中止当前会话的正在执行操作。

**Query:** `session_id` (必填)

**Response:**
```json
{"success": true}
```

---

### GET `/sessions`

列出持久化的会话列表（分页）。

**Query:**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `limit` | int | 50 | 每页数量（最大 100） |
| `offset` | int | 0 | 偏移量 |

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "scene-1780069413346",
      "created_at": "2025-01-01T12:00:00Z",
      "entry_count": 42,
      "title": "帮我写一段代码"
    }
  ],
  "total": 100,
  "offset": 0,
  "limit": 50
}
```

---

### GET `/session`

获取会话历史消息。

**Query:** `session_id` (必填)

**Response:**
```json
{
  "success": true,
  "session_id": "scene-1780069413346",
  "messages": [
    {
      "role": "user",
      "content": [{"type": "text", "text": "你好"}],
      "timestamp": 1780069413.0
    },
    {
      "role": "assistant",
      "content": [{"type": "text", "text": "你好！有什么可以帮你的？"}],
      "usage": {"input_tokens": 100, "output_tokens": 50},
      "stop_reason": "stop",
      "timestamp": 1780069415.0
    }
  ]
}
```

---

### GET `/session/export`

导出会话为文本文件。

**Query:** `session_id` (必填)

**Response:** `text/plain`，`Content-Disposition: attachment`

---

### DELETE `/session`

删除会话。

**Query:** `session_id` (必填)

**Response:**
```json
{"success": true}
```

---

## 3. 能力查询

### GET `/capabilities`

获取当前可用的 Skills 和 Tools（有缓存）。

**Response:**
```json
{
  "skills": [
    {"name": "dev-process-backend", "description": "后端开发流程指引"}
  ],
  "tools": [
    {"name": "read_file", "description": "读取文件内容", "parameters": {...}},
    {"name": "bash", "description": "执行 shell 命令", "parameters": {...}}
  ]
}
```

---

### GET `/models`

获取可用模型列表。

**Response:**
```json
{
  "current": {"provider": "openai", "model": "gpt-4o"},
  "available": [
    {"provider": "agnes", "model": "agnes-2.0-flash", "label": "Agnes 2.0 Flash", "desc": "256K context"},
    {"provider": "minimax", "model": "minimax-m2.7", "label": "MiniMax M2.7", "desc": "256K context"},
    {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o", "desc": "OpenAI flagship"},
    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4", "desc": "Anthropic high-perf"}
  ]
}
```

---

## 4. 知识库

### GET `/knowledge`

列出知识库文档。

**Response:**
```json
{"docs": [{"name": "产品手册", "chunks": 15, "tags": ["产品"]}]}
```

### POST `/knowledge`

添加/更新知识库文档（文本）。

**Body:**
```json
{"name": "产品手册", "content": "...长文本..."}
```

**Response:**
```json
{"success": true, "chunks": 15}
```

### POST `/knowledge/upload`

上传文件到知识库（支持 txt、md、pdf）。

**Content-Type:** `multipart/form-data`，字段名 `file`

**Response:**
```json
{"success": true, "chunks": 15}
```

### GET `/knowledge/{name}`

获取单个文档详情（含分块预览）。

### PUT `/knowledge/{name}/tags`

设置文档标签。

**Body:**
```json
{"tags": ["产品", "v2"]}
```

### DELETE `/knowledge`

删除文档。**Query:** `name` (必填)

---

## 5. 文件上传

### POST `/upload`

上传文件到 `.pi/uploads/`。

**Content-Type:** `multipart/form-data`，字段名 `file`

**Response:**
```json
{
  "success": true,
  "filename": "photo.jpg",
  "path": ".pi/uploads/a1b2c3d4e5f6.jpg",
  "size": 102400
}
```

---

## 6. Skills

### POST `/skills/import`

导入 Skill 文件到 `.pi/skills/`。

**Body:**
```json
{
  "name": "my-skill",
  "content": "---\ndescription: My custom skill\n---\n\n# Instructions\n..."
}
```

**Response:**
```json
{"success": true}
```

---

## 7. Personas（角色/专家）

### GET `/personas`

列出所有角色。

**Response:**
```json
{
  "personas": [
    {
      "id": "backend-expert",
      "name": "后端专家",
      "description": "擅长后端架构设计",
      "system_prompt": "你是一个后端架构师...",
      "enabled_tools": ["bash", "read_file"],
      "knowledge_bases": ["local"]
    }
  ]
}
```

### POST `/personas`

创建/更新角色。

**Body:**
```json
{
  "id": "backend-expert",
  "name": "后端专家",
  "description": "擅长后端架构设计",
  "system_prompt": "...",
  "enabled_tools": ["bash", "read_file"],
  "knowledge_bases": ["local"]
}
```

### DELETE `/personas`

删除角色。**Query:** `id` (必填)

---

## 8. Connectors（MCP 连接器）

### GET `/connectors`

列出所有 MCP 连接器及其工具。

### POST `/connectors`

添加/更新 MCP 连接器。

**Body:**
```json
{
  "name": "filesystem",
  "transport": "stdio",        // "stdio" | "sse" | "streamable_http"
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
  "url": null,
  "env": {}
}
```

### DELETE `/connectors`

删除连接器。**Query:** `name` (必填)

### POST `/connectors/health`

检查所有 MCP 连接健康状态。

---

## 9. Channels（渠道管理）

### GET `/channels`

列出渠道配置（密钥脱敏）。

### POST `/channels`

添加/更新渠道。

**Body:**
```json
{
  "id": "feishu-bot-1",
  "name": "飞书机器人",
  "type": "feishu",
  "enabled": true,
  "app_id": "cli_xxx",
  "app_secret": "xxx",
  "allowed_users": "user1,user2"
}
```

### DELETE `/channels/{channel_id}`

删除渠道。

---

## 10. Skill Evolution（技能自进化）

### GET `/skills/evolution/summary`

获取各 Skill 的 trace 统计。

**Response:**
```json
{
  "trace_counts": {
    "dev-process-backend": {"total": 50, "success": 42, "failure": 8}
  }
}
```

### POST `/skills/evolution/analyze`

触发进化分析。

**Body:**
```json
{"skill_name": "dev-process-backend", "min_traces": 10}
```

**Response:**
```json
{
  "status": "completed",
  "cycle_id": "cyc_abc",
  "traces_analyzed": 50,
  "proposals_generated": 3,
  "conflicts": 0,
  "discarded": 1,
  "proposals": [
    {
      "proposal_id": "prop_001",
      "skill_name": "dev-process-backend",
      "operation": "add",
      "target_rule_id": "rule-new-1",
      "new_content": "新增规则内容",
      "rationale": "基于多次失败分析...",
      "confidence": 0.8,
      "diff": "--- a/SKILL.md\n+++ b/SKILL.md\n..."
    }
  ]
}
```

### GET `/skills/evolution/proposals/{skill_name}`

获取缓存的提案列表。

### POST `/skills/evolution/proposals/{proposal_id}/accept`

接受并应用提案。

**Body:**
```json
{"skill_name": "dev-process-backend", "reason": "确认有效"}
```

### POST `/skills/evolution/proposals/{proposal_id}/reject`

拒绝提案。

**Body:**
```json
{"skill_name": "dev-process-backend", "reason": "不适用于当前场景"}
```

### GET `/skills/evolution/audit`

查看进化审计日志。**Query:** `skill_name` (可选), `limit` (默认 50)

---

## 11. Companion（宠物系统）

### GET `/api/companion/{uid}`

获取用户的宠物骨骼配置。

**Response:**
```json
{
  "uid": "user_123",
  "breed": "cat",
  "rarity": "rare",
  "eye": "round",
  "ear": "pointed",
  "accent": "stripe",
  "hat": "none",
  "quirk": "tail-wag",
  "shiny": false,
  "color": "#F5A623",
  "stats": {"energy": 80, "mood": 70}
}
```

### POST `/api/companion/{uid}/hatch`

孵化宠物（生成名字和性格）。

**Response:** 在骨骼配置基础上追加:
```json
{
  "name": "小橘",
  "personality": "活泼好动，喜欢追光",
  "hatched_at": "2025-01-01T12:00:00Z"
}
```

---

## 12. 静态资源

| 路径 | 说明 |
|------|------|
| `GET /` | 主页面（Vite 构建产物） |
| `/assets/*` | Vite 静态资源 |
| `/uploads/*` | 用户上传文件（图片、音频等） |
