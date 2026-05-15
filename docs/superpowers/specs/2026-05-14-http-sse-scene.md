# HTTP SSE 聊天助手场景设计

> 日期: 2026-05-14
> 范围: 实现 `scene/http_sse/` 下的完整服务端，包含 SSE 流式聊天接口和 HTML demo 页面

---

## 1. 背景

`scene/http_sse/` 已在目录重构中创建骨架（`chat_assistant.py`、`system_prompt.py`、`server.py` 占位），但 `server.py` 仅包含 TODO 注释。本任务将其替换为可工作的 FastAPI HTTP SSE 服务端。

## 2. 目标

- 提供基于 FastAPI 的 HTTP SSE 流式聊天接口
- 支持会话持久化（`JsonlStore`）
- 提供内嵌 HTML demo 页面，可直接在浏览器测试
- 每个场景自包含，不改动 `scene/cli/` 和 `scene/voice_ws/`

## 3. 非目标 (YAGNI)

- 不实现多租户 / 认证 / 限流
- 不实现 WebSocket（由 `voice_ws/` 场景负责）
- 不实现会话列表 / 历史分页查询 API
- 不实现图片 / 文件上传
- 不实现对话分支或导航

## 4. API 设计

### 4.1 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat/stream?session_id=<可选>` | Body: `ChatRequest`。返回 `text/event-stream` |
| GET | `/` | 返回 HTML demo 页面 |

### 4.2 请求体

```python
class ChatRequest(BaseModel):
    message: str
```

### 4.3 SSE 事件格式

每条 event 为 JSON，通过 `data:` 推送。事件类型由 `event` 字段区分：

| `event` 值 | 字段 | 说明 |
|---|---|---|
| `session_id` | `session_id: str` | 首条 event，告知客户端会话 ID |
| `text_delta` | `text: str` | LLM 输出的文本片段 |
| `thinking_delta` | `text: str` | 模型思考内容（如有） |
| `tool_start` | `tool_name: str, args: dict` | 工具调用开始 |
| `tool_end` | `tool_name: str, result: str, is_error: bool` | 工具调用结束 |
| `message_end` | `usage: dict\|None` | 单条消息结束，含 token 用量 |
| `done` | — | 本次响应全部结束，流关闭 |

示例：

```
data: {"event": "session_id", "session_id": "scene-1778690130638"}

data: {"event": "text_delta", "text": "Hello"}

data: {"event": "text_delta", "text": "!"}

data: {"event": "message_end", "usage": {"input_tokens": 12, "output_tokens": 2}}

data: {"event": "done"}
```

## 5. 内部架构

### 5.1 SessionManager (`manager.py`)

职责：管理 `ChatAssistant` 实例的生命周期和 `JsonlStore` 持久化。

```python
class SessionManager:
    def __init__(self, store: SessionStore | None = None, cwd: str = "") -> None
    async def get_or_create(self, session_id: str | None) -> tuple[str, ChatAssistant]
    async def dispose(self, session_id: str) -> None
```

- `get_or_create`：若 `session_id` 为空则生成新 ID；若已有实例则复用，否则通过 `ChatAssistant.create()` 新建
- `dispose`：清理指定会话的 assistant 资源
- 内部维护 `dict[str, ChatAssistant]` 作为运行时缓存
- 使用 `JsonlStore`（默认 `./sessions`）持久化消息历史

### 5.2 EventStreamer (`events.py`)

职责：把 `AgentEvent` 转成 SSE JSON 事件，并提供 `async for` 迭代器。

```python
def agent_event_to_sse_json(evt: AgentEvent) -> dict | None:
    """把 AgentEvent 转成 SSE JSON dict。不关心的 event 返回 None。"""
```

支持的转换映射：
- `MessageUpdate` + `TextDelta` → `{"event": "text_delta", "text": ...}`
- `MessageUpdate` + `ThinkingDelta` → `{"event": "thinking_delta", "text": ...}`
- `ToolExecutionStart` → `{"event": "tool_start", "tool_name": ..., "args": ...}`
- `ToolExecutionEnd` → `{"event": "tool_end", "tool_name": ..., "result": ..., "is_error": ...}`
- `MessageEnd` → `{"event": "message_end", "usage": ...}`
- `ToolCallDelta` → `None`（不单独推送，工具元数据由 ToolExecutionStart/End 提供）
- `AgentStart` / `AgentEnd` / `TurnStart` / `TurnEnd` → `None`

`EventStreamer` 还会负责：
- 在流开始时推送 `session_id` 事件
- 在流结束时推送 `done` 事件
- 使用 `asyncio.Queue` 桥接回调式 `on_event` 和 `async for` 流式输出

### 5.3 FastAPI Server (`server.py`)

职责：路由定义、请求处理、HTML demo 页面返回。

```python
app = FastAPI(title="Agent Core HTTP SSE Chat")

@app.post("/chat/stream")
async def chat_stream(session_id: str | None = None, request: ChatRequest = ...) -> StreamingResponse

@app.get("/")
async def index() -> HTMLResponse
```

`chat_stream` 处理流程：
1. 从 `SessionManager` 获取或创建 assistant
2. 注册事件处理器 → `asyncio.Queue`
3. 调用 `assistant.send_message(request.message)`
4. 返回 `StreamingResponse`，通过 `EventStreamer` 从 Queue 读取并格式化为 SSE
5. 流关闭后取消事件订阅

`/` 路由直接读取 `scene/http_sse/static/index.html` 文件内容并作为 `HTMLResponse` 返回。

启动入口：
```python
if __name__ == "__main__":
    uvicorn.run("scene.http_sse.server:app", host="0.0.0.0", port=8000, reload=False)
```

### 5.4 HTML Demo 页面 (`static/index.html`)

单独的 HTML 文件，维护在 `scene/http_sse/static/index.html`。

功能：
- 输入框 + 发送按钮
- 聊天记录显示区
- 使用 `EventSource` 连接 POST `/chat/stream`
- 流式显示文本（增量追加）
- 显示工具调用（折叠或可展开）
- 新会话时自动获取并记录 `session_id`
- 可选："新会话"按钮清空上下文

样式：极简 CSS（内嵌在 HTML 的 `<style>` 中），无需外部依赖。

## 6. 文件结构

```
scene/http_sse/
├── __init__.py
├── chat_assistant.py          # 已有（复制自 cli，不改动）
├── system_prompt.py           # 已有（复制自 cli，不改动）
├── manager.py                 # 新增：SessionManager
├── events.py                  # 新增：EventStreamer + 转换函数
├── server.py                  # 新增：FastAPI app
└── static/
    └── index.html             # 新增：HTML demo 页面
```

## 7. 依赖变更

`pyproject.toml` 增加：

```toml
dependencies = [
    "pydantic>=2.5",
    "httpx>=0.27",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.30",
]
```

## 8. 验证方式

### 8.1 手动验证

启动：
```bash
cd /Users/yuanbaishu/pythonProject/agent-core
python -m scene.http_sse.server
```

浏览器打开 `http://localhost:8000/` 测试。

或用 curl：
```bash
curl -N -X POST "http://localhost:8000/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"message": "请介绍一下你自己"}'
```

### 8.2 单元测试

新增 `tests/scene/test_http_sse.py`：

1. `test_event_to_sse_json_text_delta` — 验证 TextDelta 转换
2. `test_event_to_sse_json_tool_execution` — 验证 ToolExecutionStart/End 转换
3. `test_event_to_sse_json_message_end` — 验证 MessageEnd 转换
4. `test_event_streamer_flow` — 验证 EventStreamer 的 Queue + async iter 流程
5. `test_session_manager_get_or_create` — 验证 SessionManager 新建和复用

## 9. 风险与回退

- **依赖风险**：新增 `fastapi` 和 `uvicorn`。如后续不需要，可从 `pyproject.toml` 移除（对 `agent_core` 库本身无侵入）。
- **并发风险**：`ChatAssistant` 内部状态不是为并发设计的。`SessionManager` 按 session 隔离，同一会话的并发请求可能产生竞态。v1 不处理（留文档说明）。
- **回退方式**：删除 `scene/http_sse/manager.py`、`events.py`、`server.py`，恢复占位 `server.py` 即可回退到骨架状态。
