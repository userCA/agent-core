# agent_core/core 核心交互文档

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      HTTP SSE Server                         │
│  POST /chat/stream  ← SSE →  浏览器 / 客户端                  │
│  POST /abort /human-input /session …                        │
└──────────┬──────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│                    ChatAssistant                             │
│  组装: Agent + SessionStore + Skills + ToolRegistry           │
│  send_message() / abort() / provide_human_input()            │
└──────────┬──────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│                    AgentSession                              │
│  组合: Agent + Store + Compactor + Extensions                │
│  ← 监听 AgentEvent → 持久化 MessageEnd / ToolExecutionEnd     │
│  ← 自动触发 Compaction                                       │
└──────────┬──────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│                       Agent                                  │
│  状态化包装: AgentState + subscribe(listener)                 │
│  steer() / follow_up() / abort() / provide_human_input()     │
│  ← prompt() → agent_loop() 异步生成器                         │
└──────────┬──────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│                    agent_loop()                               │
│  纯异步生成器: 流式 LLM → 执行工具 → 循环                      │
│  产出 AgentEvent 区分联合类型                                  │
└─────────────────────────────────────────────────────────────┘
```

**分层单向依赖**: `core` (无 IO) → `session` (依赖 core) → `extensions` (依赖 core, 接入 session)

---

## 2. 数据模型

### 2.1 Content 块 (`content.py`)

消息和工具结果的基本构建块，三个纯数据模型：

| 类型 | 字段 | 用途 |
|------|------|------|
| `TextContent` | `type="text"`, `text: str` | 文本内容 |
| `ImageContent` | `type="image"`, `data: str`, `mime_type: str` | 图片内容（base64） |
| `ToolCallContent` | `type="tool_call"`, `id: str`, `name: str`, `arguments: dict` | 工具调用声明 |

### 2.2 消息 (`messages.py`)

**`AgentMessage` 区分联合** — 按 `role` 字段判别的 4 种消息：

```
AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | CustomMessage
```

| 消息类型 | role | 关键字段 |
|----------|------|----------|
| `UserMessage` | `"user"` | `content: list[TextContent\|ImageContent]`, `timestamp` |
| `AssistantMessage` | `"assistant"` | `content: list[TextContent\|ToolCallContent]`, `usage: Usage`, `stop_reason`, `error_message?`, `retryable_error`, `overflow_error`, `provider`, `model`, `timestamp` |
| `ToolResultMessage` | `"tool_result"` | `tool_call_id`, `tool_name?`, `content: list[TextContent\|ImageContent]`, `is_error`, `timestamp` |
| `CustomMessage` | `"custom"` | `custom_type`, `content: Any`, `display?`, `details?`, `timestamp` |

**`Usage`** 模型: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` + `total_tokens` 属性。

**`StopReason`**: `"stop" | "tool_use" | "length" | "content_filter" | "error" | "aborted"`

**序列化**: `deserialize_message(data: dict) -> AgentMessage` 通过 Pydantic `TypeAdapter` 从 JSON dict 还原。

### 2.3 事件 (`events.py`)

**`AgentEvent` 区分联合** — agent loop 产出的 12 种事件：

```
AgentEvent = AgentStart | AgentEnd | TurnStart | TurnEnd |
             MessageStart | MessageUpdate | MessageEnd |
             ToolExecutionStart | ToolExecutionUpdate | ToolExecutionEnd |
             HumanInputRequired
```

#### 生命周期事件

| 事件 | 触发时机 | 关键字段 |
|------|----------|----------|
| `AgentStart` | 一次 `prompt()` 调用开始 | — |
| `AgentEnd` | 一次 `prompt()` 调用结束 | `messages: list` (本轮所有 AssistantMessage) |
| `TurnStart` | 每个 LLM 往返开始 | — |
| `TurnEnd` | 每个 LLM 往返结束 | `message`, `tool_results` |

#### 消息流事件

| 事件 | 触发时机 | 关键字段 |
|------|----------|----------|
| `MessageStart` | 一条消息开始（用户消息送入 / 助手消息开始流式输出） | `message` |
| `MessageUpdate` | 助手消息流式增量更新 | `message`, `delta: MessageDelta` |
| `MessageEnd` | 一条消息完成（用户消息送入完毕 / 助手消息流式结束） | `message` |

#### MessageDelta 子类型

```
MessageDelta = TextDelta | ThinkingDelta | ToolCallDelta
```

| Delta | 字段 | 说明 |
|-------|------|------|
| `TextDelta` | `text: str` | 文本增量 |
| `ThinkingDelta` | `text: str` | 思考链增量 |
| `ToolCallDelta` | `id`, `name?`, `arguments_delta?` | 工具调用增量（名称/参数 delta） |

#### 工具执行事件

| 事件 | 触发时机 | 关键字段 |
|------|----------|----------|
| `ToolExecutionStart` | 工具开始执行 | `tool_call_id`, `tool_name`, `args` |
| `ToolExecutionUpdate` | 工具执行中间结果（仅 sequential 模式） | `tool_call_id`, `tool_name`, `args`, `partial_result` |
| `ToolExecutionEnd` | 工具执行完成 | `tool_call_id`, `tool_name`, `result`, `is_error` |

#### 人机对话

| 事件 | 触发时机 | 关键字段 |
|------|----------|----------|
| `HumanInputRequired` | 工具抛出 `RequiresHumanInput` | `tool_call_id`, `prompt`, `input_schema` |

---

## 3. 核心循环 (`loop.py`)

### 3.1 agent_loop 签名

```python
async def agent_loop(
    new_messages: list[Any],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[AgentEvent]:
```

### 3.2 AgentContext

```python
@dataclass
class AgentContext:
    system_prompt: str = ""
    messages: list[AgentMessage]   # 完整对话历史
    tools: list[Any]               # 工具定义列表
```

### 3.3 AgentLoopConfig

控制循环行为的所有参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `Model` | 必填 | LLM 模型标识 |
| `stream_fn` | Callable | 必填 | 调用 LLM 的流式函数，返回 `AsyncIterator[StreamEvent]` |
| `convert_to_llm` | `ConvertToLlm` | 必填 | 将 `AgentMessage` 列表转为 provider 格式 |
| `auth_resolver` | `AuthResolver` | 必填 | 按 provider 名解析认证 |
| `transform_context` | `TransformContext?` | None | 在 LLM 调用前转换消息列表 |
| `thinking_level` | `Literal["off".."xhigh"]` | `"off"` | 思考深度 |
| `tool_execution` | `"parallel" \| "sequential"` | `"parallel"` | 工具执行模式 |
| `temperature` | `float?` | None | LLM temperature |
| `max_tokens` | `int?` | None | LLM 最大输出 token |
| `tool_registry` | `ToolRegistry?` | None | 工具注册表 |
| `before_tool_call` | `BeforeToolCallHook?` | None | 工具调用前钩子 |
| `after_tool_call` | `AfterToolCallHook?` | None | 工具调用后钩子 |
| `tool_timeout` | `float?` | 120.0 | 单个工具超时 (秒) |
| `max_turns` | `int?` | None | 最大 LLM 往返次数 |
| `max_retries` | `int` | 3 | LLM 调用最大重试次数 |
| `retry_base_delay` | `float` | 1.0 | 重试退避基值 |
| `retry_max_delay` | `float` | 60.0 | 重试退避上限 |
| `tool_result_max_chars` | `int` | 4000 | 工具结果最大字符数 |
| `compact_callback` | `CompactCallback?` | None | 上下文溢出时的压缩回调 |
| `mutation_queue` | `Any?` | None | 文件写入串行化队列 |
| `get_steering_messages` | `MessageDrainer?` | None | 拉取 steering 队列消息 |
| `get_follow_up_messages` | `MessageDrainer?` | None | 拉取 follow_up 队列消息 |
| `human_input_gate` | `Any?` | None | HITL 人机对话门控 |

### 3.4 循环流程图

```
agent_loop(new_messages, context, config, signal)
│
├── yield AgentStart()
├── 将 new_messages 追加到 context.messages
│   └── 每个新消息 → MessageStart + MessageEnd
│
└── while True:  ──────────────────────────────────────────────┐
    │                                                           │
    ├── 检查 signal / max_turns 是否终止                          │
    ├── yield TurnStart()                                       │
    │                                                           │
    ├── convert_to_llm(context.messages) → llm_messages         │
    ├── (可选) transform_context(llm_messages)                   │
    ├── auth_resolver(provider) → auth                          │
    ├── tools_to_provider_format(context.tools) → tool_defs      │
    │                                                           │
    ├── ┌─ LLM 调用 + 重试 ──────────────────────────────────┐  │
    │   │                                                    │  │
    │   │ 首次尝试: 流式实时推送                                │  │
    │   │   yield MessageStart(assistant)                    │  │
    │   │   _stream_assistant → yields MessageUpdate(delta)  │  │
    │   │                                                    │  │
    │   │ 重试: 缓冲后批量推送 (避免部分失败输出)               │  │
    │   │   _stream_assistant → buffer → 再 emit              │  │
    │   │                                                    │  │
    │   │ 重试条件:                                           │  │
    │   │   - stop_reason=="error" && retryable_error         │  │
    │   │     → 指数退避重试                                   │  │
    │   │   - overflow_error && compact_callback              │  │
    │   │     → 触发压缩 → 重新构建 llm_messages → 重试        │  │
    │   │                                                    │  │
    │   │ _stream_assistant 内部:                             │  │
    │   │   StreamTextDelta    → text_buf += text              │  │
    │   │                      → MessageUpdate(TextDelta)     │  │
    │   │   StreamThinkingDelta → MessageUpdate(ThinkingDelta) │  │
    │   │   StreamToolCallStart → tool_buffers[id] = {...}    │  │
    │   │                      → MessageUpdate(ToolCallDelta) │  │
    │   │   StreamToolCallDelta → MessageUpdate(ToolCallDelta)│  │
    │   │   StreamToolCallEnd  → tool_buffers[id].args = args │  │
    │   │   StreamMessageEnd   → usage + stop_reason          │  │
    │   │   StreamError        → stop_reason="error"          │  │
    │   │  结束时: text_buf → TextContent                     │  │
    │   │         tool_buffers → ToolCallContent              │  │
    │   └────────────────────────────────────────────────────┘  │
    │                                                           │
    ├── yield MessageEnd(assistant)                             │
    ├── context.messages.append(assistant)                      │
    │                                                           │
    ├── ┌─ 工具执行 ─────────────────────────────────────────┐  │
    │   │ if assistant.has_tool_calls() && tool_registry:    │  │
    │   │   execute_tools(...)                               │  │
    │   │   ├── parallel: 并发执行所有工具                      │  │
    │   │   │   yield ToolExecutionStart × N                 │  │
    │   │   │   asyncio.gather → 全部完成                     │  │
    │   │   │   yield ToolExecutionEnd × N                   │  │
    │   │   │                                                │  │
    │   │   └── sequential: 逐个顺序执行                        │  │
    │   │       for each tool_call:                          │  │
    │   │         yield ToolExecutionStart                   │  │
    │   │         yield ToolExecutionUpdate × N (中间结果)     │  │
    │   │         yield ToolExecutionEnd                     │  │
    │   └────────────────────────────────────────────────────┘  │
    │                                                           │
    ├── yield TurnEnd(message, tool_results)                    │
    │                                                           │
    ├── 判断是否继续:                                            │
    │   ├── stop_reason in ("error","aborted") → break          │
    │   ├── 有 tool_results → continue (下一轮 LLM)              │
    │   ├── steering 队列有消息 → 注入 → continue                │
    │   ├── follow_up 队列有消息 → 注入 → continue               │
    │   └── 以上皆否 → break (对话自然结束)                       │
    │                                                           │
    └───────────────────────────────────────────────────────────┘
│
yield AgentEnd(messages=new_assistant_messages)
```

---

## 4. Agent (`agent.py`)

`Agent` 是 `agent_loop` 的状态化包装，提供面向使用者的 API。

### 4.1 构造参数

```python
Agent(
    provider: ModelProvider,        # LLM 提供者
    auth_source: AuthSource,        # 认证源
    initial_state: AgentState,      # 初始状态
    convert_to_llm: ConvertToLlm,   # 消息转换器
    transform_context: TransformContext, # 上下文转换钩子
    tool_registry: ToolRegistry,    # 工具注册表
    before_tool_call / after_tool_call, # 工具钩子
    tool_execution: "parallel" | "sequential",
    tool_timeout: float = 120.0,
    max_turns: int | None,
    max_retries: int = 3,
    retry_base_delay: float = 1.0,
    retry_max_delay: float = 60.0,
    compact_callback: Callable | None,
    tool_result_max_chars: int = 4000,
    steering_mode: QueueMode = "one-at-a-time",
    followup_mode: QueueMode = "one-at-a-time",
)
```

### 4.2 公共 API

| 方法 | 说明 |
|------|------|
| `prompt(text_or_message, *, images?)` | 发送用户消息。内部将 str 包装为 `UserMessage`，调用 `_run()`。运行中再次调用会抛 `RuntimeError` |
| `continue_()` | 从当前状态继续对话（最后一条消息必须是 user/tool_result） |
| `subscribe(listener) -> unsubscribe` | 订阅事件流。listener 签名为 `(AgentEvent) -> None \| Awaitable` |
| `steer(message)` | 注入 steering 消息（运行中执行，下一次 turn 消费） |
| `follow_up(message)` | 注入 follow_up 消息（运行结束后下一个 turn 消费） |
| `provide_human_input(tool_call_id, values) -> bool` | 为等待人工输入的工具提供输入 |
| `abort()` | 触发 abort signal，取消全部 HITL pending |
| `wait_for_idle()` | 等待当前 run 完成 |
| `reset()` | 清空消息历史，保留 system_prompt / model / thinking_level / tools |

### 4.3 AgentState (`state.py`)

```python
class AgentState(BaseModel):
    system_prompt: str = ""
    model: Any | None = None
    thinking_level: ThinkingLevel = "off"  # "off"|"minimal"|"low"|"medium"|"high"|"xhigh"
    tools: list[Any] = []
    messages: list[AgentMessage] = []

    # 运行时状态
    is_streaming: bool = False
    streaming_message: Any | None = None  # 当前正在流式输出的 AssistantMessage
    error_message: str | None = None
```

### 4.4 事件分发

`Agent._handle_event()` 在消费 `agent_loop` 产出的每个事件时：
1. 更新 `AgentState`（streaming_message、messages、error_message、pending_tool_calls）
2. 调用所有已注册的 `listener(event)`

---

## 5. AgentSession (`session/session.py`)

`AgentSession` 是 Agent + SessionStore + Compactor + Extensions 的组合层。

### 5.1 职责

- **持久化**: 监听 `MessageEnd` → 写入 `MessageEntry`；监听 `ToolExecutionEnd` → 写入 `ToolResultMessage`
- **压缩**: 监听 `AgentEnd` → 检查是否需要 `Compaction`（阈值或溢出自动）
- **恢复**: `start()` 时从 `SessionStore.load_session()` 还原历史消息
- **扩展**: 将 Extensions 注册为 Agent 的 before/after tool hooks 和 transform_context hooks

### 5.2 与 Agent 的关系

```
AgentSession.start()
  ├── 从 Store 加载历史 → hydrate Agent.state.messages
  ├── agent.subscribe(_on_agent_event)  ← 监听 Agent 事件用于持久化
  └── 注册 Extensions 到 Agent hooks

AgentSession.prompt(text)
  └── agent.prompt(text, compact_callback=self._compact_callback)
      └── agent_loop → yield events → _handle_event → dispatch to listeners
                                          └── AgentSession._on_agent_event
                                                ├── MessageEnd → _persist_message
                                                ├── ToolExecutionEnd → _persist_tool_result
                                                ├── AgentEnd → _maybe_compact
                                                └── ext_runner.on_event(evt)
```

---

## 6. HTTP SSE 交互

### 6.1 服务端架构

```
FastAPI app (server.py)
├── POST /chat/stream          ← 核心 SSE 流式端点
├── POST /human-input          ← HITL 人工输入
├── POST /abort                ← 中止当前操作
├── GET  /session              ← 获取会话历史
├── GET  /session/export       ← 导出可读文本
├── DELETE /session            ← 删除会话
├── GET  /sessions             ← 列出会话
├── GET  /capabilities         ← 获取 skills + tools 列表
├── GET  /models               ← 可用模型列表
├── GET/POST/DELETE /personas  ← 专家/Prompt 管理
├── CRUD /knowledge            ← 知识库管理
├── CRUD /connectors           ← MCP 连接器管理
├── CRUD /channels             ← 飞书等频道管理
├── CRUD /skills/evolution/*   ← Skill 进化
└── GET /api/companion/{uid}   ← 伙伴系统
```

### 6.2 POST /chat/stream — SSE 流式端点

**请求**:
```json
POST /chat/stream?session_id=xxx&persona_id=yyy
{
  "message": "用户输入文本",
  "provider": "openai",     // 可选，覆盖默认
  "model": "gpt-4o"         // 可选，覆盖默认
}
```

**响应**: `text/event-stream` (SSE 格式)

### 6.3 SSE 事件格式

每个 SSE 消息格式为 `data: {"event": "...", ...}\n\n`，事件类型及顺序：

```
1. session_id     ← 首先发送，告知客户端 session ID
   {"event":"session_id", "session_id":"scene-1234567890"}

2. text_delta     ← LLM 流式输出文本增量
   {"event":"text_delta", "text":"你好"}

3. thinking_delta ← LLM 思考链增量 (仅 thinking_level > "off")
   {"event":"thinking_delta", "text":"…"}

4. tool_start     ← 工具开始执行
   {"event":"tool_start", "tool_call_id":"call_1", "tool_name":"read", "args":{…}}

5. tool_update    ← 工具执行中间结果 (仅 sequential 模式)
   {"event":"tool_update", "tool_name":"bash", "result":"…"}

6. tool_end       ← 工具执行完成
   {"event":"tool_end", "tool_call_id":"call_1", "tool_name":"read",
    "result":"文件内容…", "is_error":false, "display":{…}}

7. message_end    ← 一条 assistant message 完成
   {"event":"message_end", "usage":{"input_tokens":120,"output_tokens":45,"total_tokens":165}}

8. human_input_required ← 工具需要人工输入
   {"event":"human_input_required", "tool_call_id":"call_1",
    "prompt":"请输入地址", "input_schema":{…}}

9. error          ← 异常错误
   {"event":"error", "message":"Request timed out"}

10. done          ← 本次请求完成
    {"event":"done"}
```

### 6.4 客户端交互时序

```
客户端                             服务端
  │                                  │
  ├─ POST /chat/stream ────────────→│
  │  {"message":"帮我读文件"}         │
  │                                  ├─ manager.get_or_create(session_id)
  │                                  │  → 创建/复用 ChatAssistant
  │  ← {"event":"session_id",...}    │
  │                                  ├─ assistant.send_message(message)
  │  ← {"event":"text_delta",...}    │  → agent.prompt("帮我读文件")
  │  ← {"event":"text_delta",...}    │  → agent_loop → yield events
  │  ← {"event":"tool_start",...}    │
  │  ← {"event":"tool_end",...}      │
  │  ← {"event":"text_delta",...}    │
  │  ← {"event":"message_end",...}   │
  │  ← {"event":"done"}              │
  │                                  │
  │  (HITL 场景)                     │
  │  ← {"event":"human_input_required",...} │
  ├─ POST /human-input ───────────→│
  │  {"tool_call_id":"call_1",       │
  │   "values":{…}}                  │ → agent.provide_human_input()
  │  ← {"event":"tool_end",...}      │   (工具恢复执行)
  │  ← {"event":"done"}              │
  │                                  │
  │  (中止场景)                       │
  ├─ POST /abort ─────────────────→│
  │                                  │ → agent.abort()
  │  ← {"event":"done"}              │
```

### 6.5 AgentEvent → SSE JSON 映射 (`events.py`)

| AgentEvent | SSE event | 发送条件 |
|------------|-----------|----------|
| `MessageStart` | — | **不发送** |
| `MessageUpdate(TextDelta)` | `text_delta` | 始终发送 |
| `MessageUpdate(ThinkingDelta)` | `thinking_delta` | 始终发送 |
| `MessageUpdate(ToolCallDelta)` | — | **不发送** (工具调用参数增量走 tool_start/end) |
| `ToolExecutionStart` | `tool_start` | 始终发送 |
| `ToolExecutionUpdate` | `tool_update` | 始终发送 |
| `ToolExecutionEnd` | `tool_end` | 始终发送 |
| `HumanInputRequired` | `human_input_required` | 始终发送 |
| `MessageEnd` | `message_end` | 始终发送 (含 usage) |
| `AgentStart/AgentEnd` | — | **不发送** (AgentEnd 触发 done) |
| `TurnStart/TurnEnd` | — | **不发送** |

---

## 7. 消息队列 (`queue.py`)

`Agent` 维护两个 `PendingMessageQueue`，支持运行时和运行后的消息注入：

### 7.1 队列模式

| 模式 | drain() 行为 |
|------|-------------|
| `"one-at-a-time"` (默认) | 每次 drain 返回队首的 1 条消息 |
| `"all"` | 每次 drain 返回全部积压消息并清空 |

### 7.2 Steering Queue

- **消费时机**: 每个 turn 的 `TurnEnd` 之后，在检查 `tool_results` 之后
- **用途**: 运行时注入中断/引导消息（如用户点击 "停止生成，换一种方式"）
- **方法**: `agent.steer(message)`

### 7.3 Follow-up Queue

- **消费时机**: steering 队列为空时
- **用途**: 当前 run 结束后自动排入下一条消息（如 "继续"）
- **方法**: `agent.follow_up(message)`

### 7.4 队列在循环中的位置

```
TurnEnd → 有 tool_results? → continue (下一轮 LLM)
        → steering 有消息?  → 注入 → continue
        → follow_up 有消息? → 注入 → continue
        → break (自然结束)
```

---

## 8. 工具执行 (`tool_runner.py`)

### 8.1 execute_tools 流程

```
execute_tools(assistant, config, context, signal, …)
│
├── 从 assistant 提取 tool_calls
│
├── parallel 模式:
│   ├── yield ToolExecutionStart × N
│   ├── _run_tools_parallel()
│   │   ├── Semaphore(8) 限流
│   │   └── asyncio.gather(所有 _run_single_tool)
│   ├── yield ToolExecutionEnd × N
│   └── 每个结果 → ToolResultMessage → 追加到 context.messages
│
└── sequential 模式:
    for each tool_call:
      ├── yield ToolExecutionStart
      ├── create_task(_run_single_tool)
      ├── while task 未完成: yield ToolExecutionUpdate (中间结果)
      ├── yield ToolExecutionEnd
      └── 结果 → ToolResultMessage → 追加到 context.messages
```

### 8.2 _run_single_tool 流程

```
_run_single_tool(tool_call, registry, before, after, signal, …)
│
├── registry.get(tool_call.name) → tool
│   └── 未找到 → 返回错误 ToolResult
│
├── before_tool_call hook
│   ├── block → 返回阻止结果
│   ├── inject_metadata → 注入到 ToolContext.metadata
│   └── mutated_args → 修改 tool_call.arguments
│
├── args 验证 (如果 tool.definition.args_model 存在)
│   └── 验证失败 → 返回错误 ToolResult
│
├── 构建 ToolContext(signal, mutation_queue, on_update, metadata)
│
├── asyncio.wait_for(tool.execute(...), timeout)
│   ├── 正常完成 → 结果 + is_error=False
│   ├── TimeoutError → 超时结果 + is_error=True
│   ├── RequiresHumanInput → 向上抛出 (由 sequential 模式处理 HITL)
│   └── Exception → 异常结果 + is_error=True
│
└── after_tool_call hook
    └── 可修改 ToolResult (content / details / display)
```

### 8.3 ToolResult 结构

```python
class ToolResult(BaseModel):
    content: list[TextContent | ImageContent]  # 必须
    details: Any = None                         # 可选额外详情
    display: Any = None                         # 可选前端渲染指令
```

---

## 9. Human-in-the-Loop (`human_input.py`)

### 9.1 机制

工具通过抛出 `RequiresHumanInput(prompt, input_schema)` 来请求人工输入。

### 9.2 流程

```
Tool 执行中
  │
  ├── raise RequiresHumanInput("请输入地址", {"type":"object","properties":{…}})
  │
  ├── sequential 模式捕获异常
  │   ├── human_input_gate.require_input(tool_call_id) → Future
  │   ├── yield HumanInputRequired(tool_call_id, prompt, input_schema)
  │   │   ← SSE 发送给客户端
  │   │   ← 客户端展示输入表单
  │   │   ← 用户填写并提交 POST /human-input
  │   │   ← server → agent.provide_human_input(tool_call_id, values)
  │   │   ← gate.provide_input(tool_call_id, values)
  │   │   ← future.set_result(values)
  │   ├── await future  → 获得用户输入
  │   └── 继续执行 → 构建 ToolResult
  │
  └── parallel 模式不支持 HITL (RequiresHumanInput 转为错误)
```

### 9.3 HumanInputGate

```python
class HumanInputGate:
    require_input(tool_call_id) -> Future[dict]  # 创建等待 Future
    provide_input(tool_call_id, values) -> bool  # 解析 Future
    is_waiting(tool_call_id) -> bool             # 检查是否在等待
    cancel_all()                                  # 取消所有 pending
```

---

## 10. 扩展钩子系统 (`extensions/`)

Extension 通过 `ExtensionRunner` 在 AgentSession 层集成：

| 钩入点 | 注册方式 | 调用时机 |
|--------|----------|----------|
| `before_tool_call` | `agent.add_before_tool_call_hook()` | 每个工具执行前 |
| `after_tool_call` | `agent.add_after_tool_call_hook()` | 每个工具执行后 |
| `transform_context` | `agent.add_transform_context_hook()` | LLM 调用前转换消息 |
| `on_event` | `ext_runner` 内部 | 每个 AgentEvent 触发 |

---

## 11. 快速参考

### 11.1 构建最小 Agent 并订阅事件

```python
from agent_core.core.agent import Agent
from agent_core.core.state import AgentState

agent = Agent(
    provider=my_provider,
    auth_source=my_auth,
    initial_state=AgentState(
        system_prompt="You are a helpful assistant.",
        model=my_model,
        tools=[...],
    ),
    tool_registry=my_registry,
)

async def on_event(evt):
    if isinstance(evt, MessageUpdate):
        print(evt.delta.text, end="", flush=True)

unsub = agent.subscribe(on_event)
await agent.prompt("Hello!")
unsub()
```

### 11.2 通过 AgentSession 持久化

```python
from agent_core.session.session import AgentSession
from agent_core.session.jsonl_store import JsonlStore

session = AgentSession(
    agent=agent,
    store=JsonlStore("sessions/"),
    session_id="my-session",
)
await session.start()
await session.prompt("Hello!")
# 所有 MessageEnd 自动持久化到 sessions/my-session.jsonl
```

### 11.3 HTTP SSE 关键文件

| 文件 | 职责 |
|------|------|
| `scene/http_sse/server.py` | FastAPI 路由 + SSE 流 |
| `scene/http_sse/chat_assistant.py` | ChatAssistant 工厂 |
| `scene/http_sse/events.py` | AgentEvent → SSE JSON 转换 |
| `scene/http_sse/manager.py` | SessionManager (会话池) |
| `agent_core/core/events.py` | AgentEvent 定义 |
| `agent_core/core/messages.py` | AgentMessage 定义 |
| `agent_core/core/loop.py` | 核心循环 |
| `agent_core/core/agent.py` | 状态化 Agent |
