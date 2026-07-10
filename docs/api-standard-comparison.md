# API 规范对标分析：当前 vs 行业标准

## 对标对象

| 标准 | 适用场景 | 事件模型 |
|------|----------|----------|
| **OpenAI Chat Completions** | 纯对话（无工具执行） | `data: {chunk}\n\ndata: [DONE]` |
| **OpenAI Responses API** (2025) | Agent + 多工具 + 多模态 | 24 种语义化事件，三层树状结构 |
| **OpenAI Assistants API** | Agent（Thread + Run） | `thread.run.*` + `thread.message.*` 命名空间 |
| **Anthropic Messages API** | 纯对话 + content blocks | `message_start/delta/stop` |
| **阿里 DashScope Assistant API** | Agent（类似 OpenAI Assistants） | `thread.run.*` + `thread.message.*` |

---

## 1. 核心问题清单

### P0 — 必须修复

#### 1.1 SSE 格式不符合标准

**当前**: 只有 `data:` 字段，事件类型编码在 JSON body 内
```
data: {"event": "text_delta", "text": "你好"}\n\n
```

**标准 SSE 协议**（W3C + OpenAI/Anthropic 均采用）: 使用 `event:` 字段
```
event: text_delta
data: {"text": "你好"}\n\n
```

**影响**: 前端不能用浏览器原生 `EventSource` API，必须手动解析 `data` 中的 `event` 字段。标准 `EventSource` 会自动按 `event` 字段分发回调。

**修复方案**: `_format_sse()` 增加 `event` 字段
```python
def _format_sse(data: dict) -> str:
    event = data.pop("event", "message")
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

---

#### 1.2 缺少 API 版本前缀

**当前**: `/chat/stream`, `/sessions`, `/abort`
**标准**: `/v1/chat/stream`, `/v1/sessions`, `/v1/abort`

**影响**: 无法做破坏性变更时平滑迁移。这是所有标准 API 的基本规范。

---

#### 1.3 缺少 Response/Run ID

**当前**: 事件流没有请求级唯一标识
**标准**: 每个响应有 `id: "resp_abc123"` 或 `id: "run_xyz789"`

```json
// OpenAI Responses API
{"type": "response.created", "response": {"id": "resp_abc123", "status": "in_progress"}}

// OpenAI Assistants API  
event: thread.run.created
data: {"id": "run_abc", "thread_id": "thread_xyz", "status": "queued"}
```

**影响**: 前端无法追踪请求状态，调试困难，日志无法关联。

---

#### 1.4 缺少终止信号

**当前**: `{"event": "done"}` — 非标准
**标准**: 
- OpenAI Chat: `data: [DONE]\n\n`
- OpenAI Responses: `{"type": "response.completed"}`
- Anthropic: `event: message_stop` + `data: [DONE]`

**建议**: 保留 `done` 事件但增加标准终止符
```python
# 最后发送
yield f"event: done\ndata: {json.dumps({...})}\n\n"
yield "data: [DONE]\n\n"
```

---

### P1 — 强烈建议

#### 1.5 事件命名无命名空间

**当前**: `text_delta`, `tool_start`, `tool_end`, `message_end`
**标准**: 使用层级命名
- OpenAI Responses: `response.output_text.delta`, `response.function_call_arguments.delta`
- OpenAI Assistants: `thread.message.delta`, `thread.run.step.completed`
- Anthropic: `message_start`, `content_block_delta`, `message_stop`

**建议**: 至少使用两级命名空间
```
run.created          ← 替代 session_id
message.delta        ← 替代 text_delta
message.completed    ← 替代 message_end
tool.call.started    ← 替代 tool_start
tool.call.completed  ← 替代 tool_end
run.completed        ← 替代 done
```

---

#### 1.6 缺少 `stop_reason`

**当前 `message_end`**:
```json
{"event": "message_end", "usage": {...}}
```

**标准**: 必须包含停止原因
```json
// Anthropic
{"type": "message_delta", "stop_reason": "end_turn", "usage": {...}}

// OpenAI
{"finish_reason": "stop"}  // or "tool_calls", "length", "content_filter"
```

**建议**:
```json
{"event": "message.completed", "stop_reason": "end_turn", "usage": {...}}
```

---

#### 1.7 错误响应格式不标准

**当前**:
```json
{"event": "error", "message": "Request timed out"}
```

**标准** (OpenAI):
```json
{
  "error": {
    "type": "timeout_error",
    "message": "Request timed out",
    "code": "request_timeout",
    "param": null
  }
}
```

**标准** (HTTP 非流式):
```json
// HTTP 400/401/404/500
{
  "error": {
    "type": "invalid_request_error",
    "message": "...",
    "code": "..."
  }
}
```

---

#### 1.8 session_id 应放在 Request Body

**当前**: `POST /chat/stream?session_id=xxx`
**标准**: REST 资源操作应通过 body 或 path
```
POST /v1/threads/{thread_id}/runs   (OpenAI Assistants)
POST /v1/chat/completions            (body 中传 messages)
```

**建议**: `session_id` 移入 body
```json
{
  "session_id": "scene-xxx",
  "message": "你好",
  "provider": "openai",
  "model": "gpt-4o"
}
```

---

### P2 — 建议优化

#### 1.9 REST 端点命名不规范

| 当前 | 问题 | 建议 |
|------|------|------|
| `GET /session` | 单数，不明确 | `GET /v1/sessions/{id}/messages` |
| `DELETE /session` | 缺少 path 参数 | `DELETE /v1/sessions/{id}` |
| `POST /abort` | 不是 RESTful | `POST /v1/sessions/{id}/abort` |
| `POST /human-input` | query 传 session_id | `POST /v1/sessions/{id}/tool-results` |
| `GET /capabilities` | OK | `GET /v1/capabilities` |
| `GET /models` | OK | `GET /v1/models` |

---

#### 1.10 工具事件过于定制化

当前 `tool_start` / `tool_update` / `tool_end` 是你独有的事件类型。

行业标准处理方式:
- **OpenAI Responses**: 工具调用是 `response.output_item`，用 `type: "function_call"` 区分
- **OpenAI Assistants**: 工具调用是 `thread.run.step`，用 `step_details.type: "tool_calls"` 区分
- **Anthropic**: 工具调用是 `content_block`，用 `type: "tool_use"` 区分

**核心区别**: 行业标准中，工具调用是 **消息的一部分**（content block），不是独立事件。而你的 Agent 自己执行工具，所以需要额外的执行状态事件 — 这是合理的，但命名应该更规范。

---

## 2. 推荐的目标事件格式

综合 OpenAI Responses API + Anthropic Messages API，推荐以下目标格式:

### SSE 格式
```
event: run.created
data: {"id": "run_abc123", "session_id": "scene-xxx", "status": "in_progress"}

event: message.delta
data: {"text": "你好"}

event: thinking.delta  
data: {"text": "让我想想..."}

event: tool_call.started
data: {"id": "call_xyz", "name": "read_file", "arguments": {"path": "/src/main.py"}}

event: tool_call.completed
data: {"id": "call_xyz", "name": "read_file", "output": "...", "is_error": false}

event: message.delta
data: {"text": "根据文件内容..."}

event: human_input.required
data: {"tool_call_id": "call_xyz", "prompt": "确认执行？", "schema": {...}}

event: run.completed
data: {"id": "run_abc123", "stop_reason": "end_turn", "usage": {"input_tokens": 1200, "output_tokens": 350, "total_tokens": 1550}}

event: companion.state
data: {"type": "happy", "uid": "user_123", "emotion": "joyful"}

event: companion.bubble
data: {"uid": "user_123", "text": "加油！", "ttl_ms": 5000}

data: [DONE]
```

### 完整 REST 端点

```
POST   /v1/sessions/{id}/runs          ← 创建对话 run（SSE）
POST   /v1/sessions/{id}/runs/{rid}/tool-results  ← 提交工具结果
POST   /v1/sessions/{id}/abort         ← 中止
GET    /v1/sessions/{id}/messages       ← 获取历史
GET    /v1/sessions                    ← 列表
DELETE /v1/sessions/{id}               ← 删除
GET    /v1/capabilities               ← 能力
GET    /v1/models                     ← 模型
```

---

## 3. 改造优先级与工作量

| 优先级 | 改造项 | 工作量 | 影响范围 |
|--------|--------|--------|----------|
| P0 | SSE `event:` 字段 | 极小（改 `_format_sse`） | 前端解析方式需同步改 |
| P0 | `/v1/` 前缀 | 小 | 所有端点 |
| P0 | Run ID | 小 | `_event_stream` 入口 |
| P0 | `[DONE]` 终止符 | 极小 | 前端判断逻辑 |
| P1 | 事件命名空间 | 中 | events.py 全部重写 |
| P1 | `stop_reason` | 小 | `MessageEnd` 处理 |
| P1 | 错误格式 | 小 | 错误处理统一化 |
| P1 | session_id 移入 body | 小 | ChatRequest + 路由 |
| P2 | REST 路径规范化 | 中 | 所有端点 + 前端 |

---

## 4. 向后兼容策略

建议 **双版本并行** 过渡：

1. 新增 `/v1/` 端点，使用标准格式
2. 旧端点保留 3 个月，加 `Deprecation` header
3. 前端逐步迁移到 `/v1/`

```python
# server.py 示例
@app.post("/v1/sessions/{session_id}/runs")
async def v1_create_run(session_id: str, body: RunRequest):
    ...

@app.post("/chat/stream", deprecated=True)
async def legacy_chat_stream(...):
    # 保留旧逻辑
    ...
```
