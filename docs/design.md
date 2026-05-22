# agent-core 设计文档

> 通用 Python Agent 框架(库级别)。参考 `demo/` 中 pi-mono(`pi-agent-core` + `AgentSession`)的架构，以 Python 重新实现并适应云端部署。
> 框架只交付库与抽象，具体的服务运行时(API server、Worker、部署拓扑)由消费者按场景实现；`scene/` 目录提供示例宿主(CLI、HTTP SSE、Voice WS)。

> **本文档反映 2026-05-18 仓库现状**。已实现的模块按当前代码描述；未实现的 v1 计划项在 §8 显式列出。

---

## 0. 范围与目标

**目标**

- 提供一个 **多用户、可扩展、通用** 的 Python Agent 框架。
- 支持流式 LLM 交互、工具调用、上下文压缩、扩展(Hook)体系。
- 不绑定任何服务形态；可被 FastAPI、CLI、Notebook、WebSocket 等任意宿主消费。
- 抽象优先，实现适配：存储、LLM、工具来源均通过 Protocol 注入。

**v1 已交付**

1. Agent 运行时核心(状态 + 事件 + 工具循环 + 流式)
2. 工具体系(HTTP API、本地工具组、文件互斥队列、工具渲染)
3. 人类介入(HITL)：工具可中断流程等待用户输入
4. LLM 多提供商抽象(OpenAI / OpenAI 兼容 / Anthropic)
5. 会话与存储抽象(`SessionStore` + 内置 InMemory/JSONL)
6. 上下文压缩(`LLMSummaryCompactor` + 阈值策略)
7. 扩展/Hook 体系(事件订阅、工具拦截、扩展运行器、入口点加载)
8. 资源体系(Skills、Prompts、Themes、Context Files)
9. 动态系统 Prompt 构建(`SystemPromptBuilder`)
10. Scene 层(`scene/cli`、`scene/http_sse`、`scene/voice_ws`)

**v1 暂未实现 / 留作扩展**

- MCP(Model Context Protocol)工具适配 —— 设计文档预留，但未落地代码
- 进程内 / 子进程隔离的用户工具插件加载(entry points / 目录扫描)
- MongoDB / Redis 等 `SessionStore` 适配器(`motor` 在 extras 中列出，但实现未提供)
- 会话分支与树导航(`navigate_tree`、fork)
- 服务端沙箱执行(Docker / Firecracker)
- 客户端代理工具(WebSocket 双向 RPC)
- HTML / Markdown 会话导出
- OpenTelemetry trace / metrics 集成

---

## 1. 整体分层与模块布局

### 1.1 设计原则

- **异步优先**：全栈 `asyncio`，公共调用是 coroutine 或 async generator。
- **接口在框架内、实现在适配器**：存储/LLM/工具来源都先定义 Protocol，再附内置实现。
- **分层单向依赖**：`core ← session ← extensions`；`prompts` / `resources` 服务于 scene 层。
- **显式优于隐式**：状态用 Pydantic 模型表达；事件用判别联合(discriminated union)分发。
- **YAGNI**：v1 只做必要功能，沙箱、分支、运营能力放扩展点。
- **库 ≠ 服务**：核心库不依赖 FastAPI；`fastapi`/`uvicorn` 仅供 `scene/http_sse` 使用，作为示例宿主。

### 1.2 实际包结构

```
agent_core/
├── core/                         # 不依赖任何 IO 的纯运行时
│   ├── agent.py                  # Agent 类:状态 + 事件 + prompt 循环 + HITL
│   ├── loop.py                   # agent_loop / agent_loop_continue(async generator)
│   ├── events.py                 # AgentEvent 判别联合(含 HumanInputRequired)
│   ├── state.py                  # AgentState + ThinkingLevel
│   ├── context.py                # AgentContext / AgentLoopConfig(value object)
│   ├── messages.py               # UserMessage/AssistantMessage/ToolResultMessage/CustomMessage
│   ├── content.py                # TextContent / ImageContent / ToolCallContent
│   ├── tool_runner.py            # 并行/串行工具执行 + RequiresHumanInput 处理
│   ├── queue.py                  # PendingMessageQueue(steering / follow-up)
│   └── human_input.py            # HumanInputGate + RequiresHumanInput 异常
│
├── providers/                    # LLM 多提供商适配
│   ├── base.py                   # ModelProvider Protocol
│   ├── types.py                  # Model / ModelCost / StreamEvent 联合
│   ├── registry.py               # ModelRegistry + 凭证解析
│   ├── auth.py                   # AuthSource(static / env / dynamic) + ProviderAuth
│   ├── openai_provider.py        # OpenAI(含 OpenAI 兼容端点,如 vLLM / Minimax)
│   └── anthropic_provider.py     # Anthropic
│
├── tools/                        # 工具抽象与内置工具
│   ├── base.py                   # Tool / ToolResult / ToolDefinition / ToolRegistry / ToolContext
│   ├── http_tool.py              # HTTP API 工具适配 + BearerAuth
│   ├── operations.py             # FileOperations / BashOperations Protocol + 数据类
│   ├── operations_local.py       # LocalFileOperations / LocalBashOperations
│   ├── mutation_queue.py         # FileMutationQueue(按路径 asyncio.Lock)
│   ├── render.py                 # ToolRenderer Protocol + RenderedOutput
│   ├── truncate.py               # 文本截断工具(头/尾/行/字节)
│   ├── music.py                  # TextToMusicTool(咪兔音乐 API,示例长耗时工具)
│   └── local/                    # 内置本地工具组
│       ├── bash.py / read.py / write.py / edit.py
│       ├── ls.py / grep.py / find.py
│       ├── confirm.py            # ConfirmTool(HITL 示例:文本/多行/图片/语音)
│       └── __init__.py           # create_all_tools / create_coding_tools / create_read_only_tools
│
├── session/                      # 会话与持久化
│   ├── store.py                  # SessionStore Protocol + Entry 类型
│   ├── session.py                # AgentSession(组合 Agent + Store + Extensions + Compactor)
│   ├── inmemory_store.py         # 测试用内存实现
│   └── jsonl_store.py            # 每会话一个 .jsonl 文件
│
├── compaction/
│   ├── compactor.py              # Compactor Protocol + LLMSummaryCompactor
│   └── strategies.py             # estimate_tokens / 阈值判定
│
├── extensions/
│   ├── base.py                   # Extension Protocol + ExtensionContext + ExtensionRunner
│   └── loader.py                 # 显式 spec / 入口点加载
│
├── prompts/                      # 动态 system prompt 构建
│   ├── builder.py                # SystemPromptBuilder / SystemPrompt
│   ├── guidelines.py             # 基于工具集合的动态指南
│   └── snippets.py               # 工具 prompt_snippet 提取
│
├── resources/                    # 资源加载(skills / prompts / themes / context)
│   ├── loader.py                 # ResourceLoader(搜索路径 / 名称冲突 / 诊断)
│   ├── skills.py                 # SKILL.md 解析与校验
│   ├── prompts.py                # *.md prompt template 解析(yaml frontmatter)
│   ├── themes.py                 # 主题 JSON 加载
│   ├── context_files.py          # AGENTS.md / CLAUDE.md 向上查找
│   ├── extensions.py             # 文件系统扫描扩展 spec
│   ├── diagnostics.py            # ResourceDiagnostics 收集器
│   └── types.py                  # SourceInfo / Skill / PromptTemplate / Theme / ContextFile
│
├── logging_config.py             # get_logger / configure_logging(AGENT_CORE_LOG_LEVEL)
├── skills/                       # 占位包(skill 实现位于 resources/skills.py)
└── __init__.py                   # 仅暴露 __version__,无顶层再导出

scene/                            # 示例宿主(非框架本体)
├── cli/                          # 交互式 CLI:cli.py + chat_assistant.py
├── http_sse/                     # FastAPI + SSE:server.py + manager.py + chat_assistant.py + events.py + static/
└── voice_ws/                     # WebSocket 语音(占位/TODO)

tests/                            # 镜像源代码结构 + tests/scene + tests/screenshot
```

### 1.3 依赖矩阵

| 层 | 依赖 |
|---|---|
| `core/` | stdlib + pydantic |
| `tools/` | `core` + httpx |
| `providers/` | `core` + httpx + 各 SDK(可选) |
| `session/` | `core` |
| `compaction/` | `core` |
| `extensions/` | `core`,通过事件耦合 `session` |
| `prompts/` | `core` + `tools` + `resources` |
| `resources/` | stdlib + pyyaml + pathspec |
| `scene/` | 全部 + fastapi/uvicorn/python-dotenv |

### 1.4 可选 extras(`pyproject.toml` 现状)

```toml
[project.optional-dependencies]
mongo     = ["motor>=3.4"]            # 预留:Mongo store 适配器尚未实现
mcp       = ["mcp>=1.0"]              # 预留:MCP 适配器尚未实现
openai    = ["openai>=1.40"]          # 可选:当前 OpenAIProvider 用 httpx 直连
anthropic = ["anthropic>=0.34"]       # 可选:当前 AnthropicProvider 用 httpx 直连
test      = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.20"]
all       = ["motor>=3.4","mcp>=1.0","openai>=1.40","anthropic>=0.34"]
```

主依赖已包含 `fastapi` / `uvicorn[standard]` / `pathspec` / `pyyaml` —— 这是为了让 `scene/http_sse` 与 `resources` 开箱可用；后续若严格分层，可移到 `scene` extras。

---

## 2. Agent 运行时核心

### 2.1 内容块与消息(`core/content.py`、`core/messages.py`)

```python
# 内容块(judgment by `type`)
class TextContent(BaseModel):       type: Literal["text"];       text: str
class ImageContent(BaseModel):      type: Literal["image"];      data: str; mime_type: str
class ToolCallContent(BaseModel):
    type: Literal["tool_call"]; id: str; name: str; arguments: dict

# 消息(judgment by `role`)
class UserMessage(BaseModel):
    role: Literal["user"]
    content: list[TextContent | ImageContent]
    timestamp: float

class AssistantMessage(BaseModel):
    role: Literal["assistant"]
    content: list[TextContent | ToolCallContent]
    usage: Usage                       # 含 cache_read / cache_write tokens
    stop_reason: StopReason
    error_message: str | None = None
    provider: str | None = None
    model: str | None = None
    timestamp: float

class ToolResultMessage(BaseModel):
    role: Literal["tool_result"]
    tool_call_id: str
    content: list[TextContent | ImageContent]
    is_error: bool = False
    timestamp: float

class CustomMessage(BaseModel):
    role: Literal["custom"]
    custom_type: str
    content: Any
    display: Any | None = None
    details: Any | None = None
    timestamp: float

AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | CustomMessage
```

`AssistantMessage.tool_calls()` 与 `.has_tool_calls()` 是 helper 方法,供 loop 判断是否进入工具阶段。

### 2.2 AgentState(`core/state.py`)

```python
class AgentState(BaseModel):
    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    system_prompt: str = ""
    model: Model | None = None
    thinking_level: ThinkingLevel = "off"     # off|minimal|low|medium|high|xhigh
    tools: list[ToolDefinition] = []
    messages: list[AgentMessage] = []

    # readonly,由 Agent 维护
    is_streaming: bool = False
    streaming_message: AssistantMessage | None = None
    pending_tool_calls: set[str] = set()
    error_message: str | None = None
```

赋值时 Pydantic 的 `validate_assignment` 会重新校验;消息列表本身仍可被 mutate(`append` / `extend`),Agent loop 直接修改。

### 2.3 事件(`core/events.py`)

判别联合,所有事件携带 `type` 字段:

| Event | 字段 | 含义 |
|---|---|---|
| `agent_start` | — | 一次 `prompt()` 调用的起点 |
| `agent_end` | `messages` | 终点,携带本次产生的消息列表 |
| `turn_start` | — | 单轮 LLM 调用 + 后续工具执行的起点 |
| `turn_end` | `message`, `tool_results` | 当前轮的 assistant 消息与工具结果 |
| `message_start` | `message` | 消息生命周期开始 |
| `message_update` | `message`, `delta` | 流式 delta(`TextDelta` / `ThinkingDelta` / `ToolCallDelta`) |
| `message_end` | `message` | 消息完整体 |
| `tool_execution_start` | `tool_call_id`, `tool_name`, `args` | 工具调用开始 |
| `tool_execution_update` | + `partial_result` | 工具 `on_update` 推送的中间结果(串行模式) |
| `tool_execution_end` | + `result`, `is_error` | 工具调用结束 |
| `human_input_required` | `tool_call_id`, `prompt`, `input_schema` | HITL 中断,等待 `provide_human_input()` |

`subscribe` 监听器同步异步均可(`inspect.isawaitable`)。Listener 在 `_handle_event` 中按顺序 await。

### 2.4 Agent 类(`core/agent.py`)

```python
class Agent:
    def __init__(self, *,
        provider: ModelProvider,
        auth_source: AuthSource,                 # 必填:决定凭证来源
        initial_state: AgentState | None = None,
        convert_to_llm: ConvertToLlm | None = None,
        transform_context: TransformContext | None = None,
        tool_registry: ToolRegistry | None = None,
        before_tool_call: Callable | None = None,
        after_tool_call: Callable | None = None,
        tool_execution: Literal["parallel","sequential"] = "parallel",
        steering_mode: QueueMode = "one-at-a-time",
        followup_mode: QueueMode = "one-at-a-time",
    ): ...

    state: AgentState

    def subscribe(self, listener) -> Unsubscribe: ...

    async def prompt(self, text_or_message, *, images=None) -> None: ...
    async def continue_(self) -> None: ...     # 要求最后一条是 user / tool_result

    def steer(self, message) -> None: ...
    def follow_up(self, message) -> None: ...
    def provide_human_input(self, tool_call_id: str, values: dict) -> bool: ...
    def clear_all_queues(self) -> None: ...

    def abort(self) -> None: ...
    async def wait_for_idle(self) -> None: ...
    def reset(self) -> None: ...
```

**与设计初稿差异**：
- `auth_source` 是构造必填参数(不再藏在 Provider 内),Agent loop 通过它即时解析凭证。
- `provide_human_input` 是新增 API,用于配合 `RequiresHumanInput` 工具中断。
- 不再有 `session_id` 构造参数 —— session 信息属于 `AgentSession`。
- 默认 `convert_to_llm` 会把工具结果文本硬截断到 **4000 字符**,防止意外的巨型 payload 撑爆上下文。这是 Agent 层的安全网,而非 loop 层职责。

### 2.5 Agent Loop(`core/loop.py`)

纯 async generator,Agent 类只是有状态包装:

```python
async def agent_loop(
    new_messages: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event,
) -> AsyncIterator[AgentEvent]:
    yield AgentStart()
    # ...append new_messages, drain steering...
    while True:
        yield TurnStart()
        llm_messages = await config.convert_to_llm(context.messages)
        if config.transform_context:
            llm_messages = await config.transform_context(llm_messages, signal)

        auth = await config.auth_resolver(config.provider.name)
        async for stream_evt in config.provider.stream(...):
            # 翻译 StreamEvent → AgentEvent,累积 AssistantMessage,emit MessageStart/Update/End
            ...

        if assistant.has_tool_calls():
            async for evt in execute_tools(
                assistant.tool_calls(),
                registry=config.tool_registry,
                mode=config.tool_execution,
                before=config.before_tool_call,
                after=config.after_tool_call,
                human_input_gate=config.human_input_gate,
                signal=signal,
            ):
                yield evt

        yield TurnEnd(message=assistant, tool_results=...)
        # drain steering / follow_up,决定是否再来一轮
        if not (more_tool_results or steering_drained or followup_drained):
            break
    yield AgentEnd(messages=...)
```

`AgentContext` / `AgentLoopConfig`(`core/context.py`)是值对象,把所有可变依赖收敛为参数,使 loop 本身不持有可变状态。

### 2.6 工具执行(`core/tool_runner.py`)

- **parallel**(默认):`asyncio.gather([_run_single_tool(call) for call in calls])`,每个工具独立的 `ToolContext.on_update` 不会有 update 事件穿插。
- **sequential**:每个工具单独运行,`on_update` 写入 `asyncio.Queue`,执行期间以 `asyncio.sleep(0.5)` 轮询并 emit `ToolExecutionUpdate`。
- `_run_single_tool`:before-hook → tool.execute → after-hook,异常包成 `ToolResult(is_error=True)`;`RequiresHumanInput` 被特殊放行 —— 不视为错误,由上层挂到 `HumanInputGate` 上。
- `before_tool_call` 返回 `{block: True, reason}` 时,工具被跳过并返回错误结果。
- `after_tool_call` 可改写 `result.content / details / display`。

### 2.7 HITL(Human In The Loop)

新增子系统,由三个组件构成:

```python
# core/human_input.py
class RequiresHumanInput(Exception):
    def __init__(self, prompt: str, input_schema: dict): ...

class HumanInputGate:
    async def require_input(self, tool_call_id: str, prompt, input_schema) -> dict: ...
    def provide_input(self, tool_call_id: str, values: dict) -> bool: ...
    def is_waiting(self, tool_call_id: str) -> bool: ...
    def cancel_all(self) -> None: ...        # 由 Agent.abort 调用
```

工具内部:

```python
class ConfirmTool(Tool):
    async def execute(self, tool_call_id, params, ctx):
        values = await ctx.metadata["human_input_gate"].require_input(
            tool_call_id,
            prompt=params["prompt"],
            input_schema={"type": "object", ...},
        )
        return ToolResult(content=[TextContent(text=values["answer"])])
```

执行 loop 捕获 `RequiresHumanInput` → emit `HumanInputRequired` 事件 → 持有 Future 等待 `Agent.provide_human_input(tool_call_id, values)` 解决 → 工具内 `require_input()` 返回 → 继续执行。

`scene/cli` 与 `scene/http_sse` 都演示了 HITL 流转:HTTP scene 暴露 `POST /human-input` 端点。

### 2.8 队列(`core/queue.py`)

`PendingMessageQueue` 支持 `"one-at-a-time"`(默认)与 `"all"` 两种 drain 模式:
- 流式过程中 `Agent.steer(msg)` 把消息加入 steering 队列,在当前轮结束后被 drain 并参与下一轮。
- `Agent.follow_up(msg)` 加入 follow_up 队列,在整次 `prompt()` 结束前 drain;若有内容,继续追加一轮。

`steering_mode` / `followup_mode` 是可读写属性,运行时可切换。

---

## 3. 工具体系

### 3.1 Tool 抽象(`tools/base.py`)

```python
class ToolResult(BaseModel):
    content: list[TextContent | ImageContent]
    details: Any | None = None              # 不送 LLM,供 UI/扩展使用
    display: dict | None = None             # 渲染层 hint

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict                        # JSON Schema
    prompt_snippet: str | None = None
    prompt_guidelines: list[str] = []
    renderer: ToolRenderer | None = None    # 可选自定义渲染

class Tool(Protocol):
    definition: ToolDefinition
    async def execute(self, tool_call_id: str, params: dict, ctx: ToolContext) -> ToolResult: ...

@dataclass
class ToolContext:
    signal: asyncio.Event
    on_update: Callable[[ToolResult], None] | None
    metadata: dict                          # 含 session_id / human_input_gate 等
    mutation_queue: FileMutationQueue | None
```

`ToolRegistry` 提供 `register / get / list / to_definitions / __contains__ / __iter__`。`AgentState.tools` 持有轻量 `ToolDefinition`,运行时由 `tool_registry` 解析到具体 `Tool` 实例 —— 允许同名替换、按需启用、按来源标记。

### 3.2 HTTP 工具适配器(`tools/http_tool.py`)

```python
search_tool = HttpTool(
    name="web_search",
    description="Search the web",
    method="POST",
    url="https://api.example.com/search",
    auth=BearerAuth(env_var="SEARCH_API_KEY"),
    parameters={...JSON Schema...},
    request_template={"q": "{{query}}", "n": "{{limit}}"},   # {{}} 双花括号占位
    response_transform=lambda r: r["results"],
)
```

模板渲染 → `httpx.AsyncClient` 请求 → JSON 反序列化 → 包装为 `ToolResult`(`json.dumps` 后作为文本内容)。URL 占位使用单花括号 `{key}`。

### 3.3 本地工具组(`tools/local/`)

| 工具 | 实现 | 备注 |
|---|---|---|
| `read` | `LocalFileOperations.read_file` | 截断尾部 + 行号注释 |
| `write` | `LocalFileOperations.write_file` | 经 `FileMutationQueue` 互斥 |
| `edit` | `LocalFileOperations.edit_file` | 精确字符串替换,经互斥 |
| `ls` | `LocalFileOperations.ls` | 类 ls,过滤隐藏文件 |
| `grep` | `LocalFileOperations.grep` | `re` + `os.walk` |
| `find` | `LocalFileOperations.find` | glob + 递归 |
| `bash` | `LocalBashOperations.execute` | subprocess shell,带 timeout,超时返回 `truncated=True` |
| `confirm` | 直接 raise `RequiresHumanInput` | HITL 示例,支持 text/multiline/image/voice |

便利工厂(`tools/local/__init__.py`):

```python
create_all_tools(cwd)        # 完整工具组
create_coding_tools(cwd)     # read + bash + write
create_read_only_tools(cwd)  # read + grep + find + ls
```

### 3.4 `FileMutationQueue`(`tools/mutation_queue.py`)

每条路径一把 `asyncio.Lock`,避免并行工具调用对同一文件的写冲突。提供 `acquire(path)` 上下文管理器与便利方法 `read_locked / write_locked / edit_locked`,后者把锁与 `FileOperations` 桥接起来。

### 3.5 渲染与截断(`tools/render.py`、`tools/truncate.py`)

- `ToolRenderer` Protocol:`render_call(args)`、`render_result(result)` —— 工具可附带自定义渲染逻辑供 CLI/Web UI 使用。
- `RenderedOutput(text, display, mime_type)` Pydantic 模型,作为 renderer 输出统一形态。
- `truncate.py` 提供 `truncate_tail / truncate_head / truncate_line / format_size` 等纯函数,被 read / bash 等工具使用。

### 3.6 长耗时工具示例(`tools/music.py`)

`TextToMusicTool`(咪兔 AI 文本→音乐 API)演示了"提交→轮询→流式进度"的模式:每 3 秒轮询一次查询接口,通过 `ctx.on_update(ToolResult(...))` 推送进度,最多 60 次后超时。从多种响应形态中提取音频 URL,并支持中文参数描述。

### 3.7 Hook(before / after tool call)

```python
async def before_tool_call(ctx: BeforeToolCallContext) -> dict | None:
    if ctx.tool_call.name == "delete_database":
        return {"block": True, "reason": "forbidden"}

async def after_tool_call(ctx: AfterToolCallContext) -> dict | None:
    if not ctx.is_error:
        return {"result": {"details": {**ctx.result.details, "audited": True}}}
```

挂在 `Agent` 构造参数,loop 在工具边界调用。

### 3.8 MCP / 用户插件(未实现)

`mcp` 与 `plugin loader` 在 v1 留作扩展点 —— extras 中 `mcp>=1.0` 已预留依赖位,但 `tools/mcp_tool.py` 与 `plugin_tool.py` 尚未提交。计划中通过 `agent_core.tools` entry point 与 `MCPClient` 接入,使用方式参考 §3.4 / §3.5 草案(已删除以避免误导,后续在 v2 草案中重写)。

---

## 4. LLM 多提供商抽象

### 4.1 核心契约(`providers/base.py`、`providers/types.py`)

```python
class Model(BaseModel):
    provider: str
    id: str
    context_window: int
    max_output_tokens: int
    supports_reasoning: bool = False
    supports_xhigh_thinking: bool = False
    cost: ModelCost                         # 单价,统计用

class StreamEvent(BaseModel):               # provider 中立
    type: Literal[
        "text_delta","thinking_delta",
        "tool_call_start","tool_call_delta","tool_call_end",
        "message_end","error",
    ]
    # 各 type 携带不同字段(判别联合)

class ModelProvider(Protocol):
    name: str
    def list_models(self) -> list[Model]: ...
    async def stream(
        self,
        model: Model,
        messages: list[dict],                 # 已经 convert_to_llm 处理过
        tools: list[dict],                    # provider-native tool schema
        *,
        system_prompt: str,
        thinking_level: ThinkingLevel,
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
        auth: ProviderAuth,
    ) -> AsyncIterator[StreamEvent]: ...
```

### 4.2 ModelRegistry(`providers/registry.py`)

```python
class ModelRegistry:
    def register_provider(self, provider: ModelProvider, *, auth_source: AuthSource) -> None: ...
    def get_provider(self, name: str) -> ModelProvider: ...
    def find(self, provider: str, model_id: str) -> Model | None: ...
    def list_available(self) -> list[Model]: ...
    async def get_auth(self, model: Model) -> ProviderAuth: ...
    def has_configured_auth(self, model: Model) -> bool: ...
```

未注册 provider 抛 `UnknownProviderError`(继承 `KeyError`)。

### 4.3 凭证解析(`providers/auth.py`)

```python
class AuthSource:
    @classmethod
    def static(cls, api_key: str, extra_headers: dict | None = None) -> AuthSource: ...
    @classmethod
    def env(cls, env_var: str, *, extra_headers: dict | None = None) -> AuthSource: ...
    @classmethod
    def dynamic(cls, callback: Callable[[], Awaitable[ProviderAuth]]) -> AuthSource: ...

    async def resolve(self, provider_name: str) -> ProviderAuth: ...
```

- 缺少环境变量 / dynamic 回调失败 → `MissingCredentialsError`。
- `dynamic` 适合 OAuth 刷新场景。

### 4.4 OpenAI 与 OpenAI 兼容(`providers/openai_provider.py`)

- 直连 `chat/completions` SSE 接口,自行 httpx 流式解析,**不依赖 `openai` SDK**(SDK 在 extras 中保留以便切换)。
- 构造参数:`base_url`、`provider_name`、`models`、`timeout`、可注入的 `http_client`。
- 默认模型:`gpt-4o`、`gpt-4o-mini`。
- `_parse_sse` 跨多个 delta 重建 tool calls,emit `StreamToolCallStart/Delta/End` + `StreamMessageEnd(usage=...)`。
- `thinking_level` → `reasoning_effort`(支持 reasoning 的模型)。
- **同一适配器用于 OpenAI 兼容端点**(vLLM、Together、Minimax):

```python
vllm    = OpenAIProvider(base_url="http://localhost:8000/v1", provider_name="vllm")
minimax = OpenAIProvider(
    base_url="https://api.minimax.chat/v1",
    provider_name="minimax",
    models=[Model(provider="minimax", id="minimax-m2.7", ...)],
)
```

### 4.5 Anthropic(`providers/anthropic_provider.py`)

- 直连 Anthropic Messages API SSE,**不依赖 `anthropic` SDK**。
- 默认模型:`claude-sonnet-4-6`、`claude-opus-4-7`(均支持 reasoning + xhigh)。
- 内置 `THINKING_BUDGETS` 表(128 / 512 / 1024 / 2048 / 4096)→ `thinking.budget_tokens`。
- 消息转换:`_convert_messages` 合并连续同角色消息,`_to_anthropic_content` 处理 image / tool_result,`_assistant_to_anthropic` 处理 `tool_use` 块。
- 解析 `content_block_start/delta/stop`、`message_delta`、`message_stop` → `StreamEvent`。

### 4.6 思考等级(`ThinkingLevel`)

`off | minimal | low | medium | high | xhigh` —— 不支持 reasoning 的模型自动不下发 reasoning 字段;支持的模型按 provider 映射(OpenAI effort 字符串 / Anthropic budget tokens)。

### 4.7 自定义 streamFn / 代理

不再作为框架内置组件 —— 由 `OpenAIProvider(base_url=...)` 与 `OpenAIProvider(http_client=...)` 直接覆盖。需要浏览器代理的场景,可在 scene 层提供一个 `ProxyProvider` 实现 `ModelProvider` Protocol。

---

## 5. Session、压缩、扩展

### 5.1 AgentSession(`session/session.py`)

`Agent` 是纯运行时,`AgentSession` 是组合层:

```python
class AgentSession:
    def __init__(self, *,
        agent: Agent,
        store: SessionStore,
        session_id: str,
        compactor: Compactor | None = None,
        extensions: list[Extension] | None = None,
    ): ...

    async def start(self) -> None: ...
    async def prompt(self, text: str, **opts) -> None: ...
    async def continue_(self) -> None: ...
    async def compact(self, *, instructions: str | None = None) -> None: ...
    def abort(self) -> None: ...
    async def dispose(self) -> None: ...

    def subscribe(self, listener) -> Unsubscribe: ...
    @property
    def messages(self) -> list[AgentMessage]: ...
```

**关键变化**(相较初稿):

- 增加显式 `start()` —— 创建 store 中的 session header、订阅 agent 事件、装配 `ExtensionRunner`。这避免构造副作用与 async IO 隐式发生。
- 取消 `SessionSettings` 与 `compact()` 返回值。
- 在 `MessageEnd` 时持久化为 `MessageEntry`;在 `AgentEnd` 时根据 `compactor.should_compact(...)` 决定是否触发压缩(`reason="threshold"`),并写入 `CompactionEntry`。
- `compact(instructions=...)` 提供手动触发(`reason="manual"`)。
- **overflow 自动重试压缩** 在初稿设计中,但目前代码未实现 —— 若 provider 抛上下文溢出,需消费者在外层捕获并显式调用 `compact()` + `continue_()`。

### 5.2 SessionStore(`session/store.py`)

```python
class SessionStore(Protocol):
    async def create_session(self, session_id: str, header: SessionHeader) -> None: ...
    async def append_entry(self, session_id: str, entry: SessionEntry) -> None: ...
    async def load_session(self, session_id: str) -> SessionSnapshot: ...
    async def list_sessions(self, *, owner: str | None = None, limit: int = 50) -> list[SessionMeta]: ...
    async def close(self) -> None: ...
```

**SessionEntry**(已实现的 Pydantic 判别联合):

```python
SessionEntry = Union[
    MessageEntry,                 # type="message",  message dict + id
    CompactionEntry,              # type="compaction", summary / first_kept_entry_id / tokens_before
    ModelChangeEntry,             # type="model_change"
    ThinkingLevelChangeEntry,     # type="thinking_level_change"
    CustomEntry,                  # type="custom",  custom_type + data
]
```

**已实现 Store**

| Store | 用途 |
|---|---|
| `InMemoryStore` | 测试 / 短期会话 |
| `JsonlStore(directory)` | 每会话一个 `.jsonl`:第一行 header,后续行为 entries |

**未实现**:MongoDB / Redis / SQL —— 设计预留 `motor` extras,但 `MongoStore` 尚未提交。

### 5.3 Compactor(`compaction/compactor.py`)

```python
class Compactor(Protocol):
    def should_compact(self, messages: list, *, context_window: int) -> bool: ...
    async def compact(
        self,
        messages: list,
        *,
        reason: Literal["manual","threshold","overflow"],
        instructions: str | None = None,
        signal: asyncio.Event | None,
    ) -> CompactionResult: ...
```

`LLMSummaryCompactor(summarize_fn, threshold=0.8, keep_recent=4)`:
- 把 token 估算与摘要解耦:`summarize_fn(messages, instructions=...)` 由消费者提供,可对接任意 LLM。
- 阈值判定使用 `compaction.strategies.estimate_tokens`(粗略字符数模型)。
- 保留最近 `keep_recent` 条消息,对其余消息生成摘要。
- `signal` 触发时优雅退出。

**触发场景**:
1. `manual` — `session.compact(instructions=...)`
2. `threshold` — `AgentEnd` 后达阈值,**不自动 continue**
3. `overflow` — 框架未自动处理,需消费者捕获

### 5.4 Extension(`extensions/base.py`、`extensions/loader.py`)

```python
class Extension(Protocol):
    name: str
    async def on_event(self, ctx: ExtensionContext, evt: AgentEvent) -> None: ...
    async def on_before_tool_call(self, ctx, call) -> dict | None: ...     # {"block": True, "reason": ...}
    async def on_after_tool_call(self, ctx, call, result) -> dict | None:  # {"result": {"content", "details"}}
        ...

@dataclass
class ExtensionContext:
    session_id: str
    agent: Agent
    store: SessionStore
```

`ExtensionRunner` 按注册顺序 dispatch,捕获异常并 log,不中断主流程。
`ExtensionLoader`:
- `load_from_specs(specs)` —— 显式 dotted path,`importlib.import_module` 后扫描 `dir(module)` 找带 `name` 属性的类。
- `load_from_entry_points(group="agent_core.extensions")` —— setuptools entry point 加载工厂可调用对象。

**与初稿差异**:扩展 hook 已大幅收敛 —— 只暴露 `on_event` + 工具 before/after。命令注册、动态工具注册、`session_before_compact` 等高级钩子尚未实现,可由 `on_event` 内监听并调用 `ctx.agent.state.tools.append(...)` 实现。

---

## 6. Prompts、Resources 与 Scene 层

### 6.1 SystemPromptBuilder(`prompts/builder.py`)

把 system prompt 拆为有序 sections,按运行时输入动态拼装:

```python
class SystemPromptBuilder:
    def __init__(self, *, base_prompt: str | None = None) -> None: ...

    def build(self, *,
        cwd: str | None,
        active_tools: list[ToolDefinition] | None,
        skills: list[Skill] | None,
        context_files: list[ContextFile] | None,
        date: datetime | None,
    ) -> SystemPrompt: ...
```

输出 7 个 section:base → tools(按名排序,附 `prompt_snippet`) → 通用 guidelines → 工具自带 guidelines → 项目 context files → skills(`<available_skills>` XML 块,过滤 `disable_model_invocation`) → meta(日期 + CWD)。

辅助模块:
- `prompts/guidelines.py`:`generate_guidelines(tools, rules=None)` 基于工具集合的 predicate 规则(read 后查 truncate、edit 前 read、grep 优先于 bash 等)。
- `prompts/snippets.py`:`extract_snippet` 提取工具的 `prompt_snippet` → 否则截断 description 首句 → 否则 fallback 到 name。

### 6.2 ResourceLoader(`resources/`)

```python
class ResourceLoader:
    def __init__(self, *, cwd, extra_skill_paths=None, extra_prompt_paths=None,
                 extra_theme_paths=None, ignore_patterns=None): ...

    def load_skills(self) -> tuple[list[Skill], ResourceDiagnostics]: ...
    def load_prompt_templates(self) -> tuple[list[PromptTemplate], ResourceDiagnostics]: ...
    def load_themes(self) -> tuple[list[Theme], ResourceDiagnostics]: ...
    def load_context_files(self) -> list[ContextFile]: ...
    def load_extension_specs(self) -> tuple[list[ExtensionSpec], ResourceDiagnostics]: ...
```

**搜索路径顺序**:显式 `extra_*_paths` → `<cwd>/.pi/<type>` → `~/.pi/agent/<type>` → 环境变量 `AGENT_CORE_SKILLS_PATH` 等(冒号分隔)。

**Skills**:
- 文件:每个 `SKILL.md`,YAML frontmatter:`name`(≤64,kebab-case,需与父目录名匹配)、`description`(≤1024,必填)、`disable_model_invocation`(可选)。
- 名称冲突会被记录到 `ResourceDiagnostics`。

**Prompts / Themes**:`*.md` 与 `*.json`,基于 `yaml.safe_load`/`json.load`。

**Context files**:`load_project_context_files` 从 `cwd` 沿目录树向上,在遇到 `.git` 前查找 `AGENTS.md` / `CLAUDE.md`,越近的越靠前。

### 6.3 Scene 层(`scene/`)

非框架本体,作为示例宿主存在:

- **`scene/cli/`**
  - `cli.py` —— 交互式 CLI 入口(`python -m scene.cli.cli`)。`_OutputFormatter` 处理 ANSI 颜色、thinking 块独立显示,响应 `NO_COLOR`。读取 `.env`,实例化 `ChatAssistant`,事件循环逐 token 渲染。
  - `chat_assistant.py` —— `ChatAssistant.create(...)` 工厂:加载 skills/context → 构造工具集 → 解析 provider/auth → 用 `SystemPromptBuilder` 拼 system prompt → 创建 `Agent` + `AgentSession`(`JsonlStore` 或 `InMemoryStore`)。支持 `/skill:<name>` 命令展开。

- **`scene/http_sse/`**
  - `server.py` —— FastAPI 应用,端点:`POST /chat/stream`(SSE 流)、`POST /human-input`、`POST /abort`、`GET /`(静态 index.html)。
  - `manager.py` —— `SessionManager`:`session_id → ChatAssistant` 映射 + 每 id 一个 `_create_lock`。校验 `session_id` 满足 `[a-zA-Z0-9_-]+`;持久化目录 `./sessions`。
  - `chat_assistant.py` —— 与 CLI 版相同形态,额外暴露 `provide_human_input` 透传。
  - `events.py` —— `agent_event_to_sse_json(evt)` 把 `AgentEvent` 映射到前端易消费的 JSON。

- **`scene/voice_ws/`** —— 占位/TODO:WebSocket 语音(ASR→Agent→TTS)。

---

## 7. 公共 API 与使用示例

### 7.1 顶层导出

> **注意**:`agent_core/__init__.py` **仅暴露 `__version__`**。所有 API 通过子模块路径导入 —— 这是显式且稳定的选择,避免循环依赖与隐式重导出。

```python
# 运行时
from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.core.events import AgentEvent, MessageEnd, MessageUpdate
from agent_core.core.messages import UserMessage, AssistantMessage, ToolResultMessage
from agent_core.core.content import TextContent, ImageContent, ToolCallContent
from agent_core.core.loop import agent_loop, agent_loop_continue

# 工具
from agent_core.tools.base import Tool, ToolDefinition, ToolResult, ToolRegistry, ToolContext
from agent_core.tools.http_tool import HttpTool, BearerAuth
from agent_core.tools.mutation_queue import FileMutationQueue
from agent_core.tools.local import (
    create_all_tools, create_coding_tools, create_read_only_tools,
)

# Providers
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model, ModelCost, StreamEvent
from agent_core.providers.registry import ModelRegistry, UnknownProviderError
from agent_core.providers.auth import AuthSource, ProviderAuth, MissingCredentialsError
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.anthropic_provider import AnthropicProvider

# Session / Compaction
from agent_core.session.session import AgentSession
from agent_core.session.store import SessionStore, SessionEntry, MessageEntry, CompactionEntry
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.compaction.compactor import Compactor, LLMSummaryCompactor

# Extensions
from agent_core.extensions.base import Extension, ExtensionContext, ExtensionRunner

# Prompts & Resources
from agent_core.prompts.builder import SystemPromptBuilder, SystemPrompt
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.types import Skill, ContextFile, PromptTemplate, Theme
```

### 7.2 最小示例:流式问答

```python
import asyncio
from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.auth import AuthSource

async def main():
    provider = OpenAIProvider()
    model = provider.list_models()[0]               # gpt-4o
    agent = Agent(
        initial_state=AgentState(
            system_prompt="You are a helpful assistant.",
            model=model,
        ),
        provider=provider,
        auth_source=AuthSource.env("OPENAI_API_KEY"),
    )

    async def on_event(evt):
        if evt.type == "message_update" and evt.delta.type == "text_delta":
            print(evt.delta.text, end="", flush=True)

    agent.subscribe(on_event)
    await agent.prompt("Hello!")

asyncio.run(main())
```

### 7.3 完整示例:Session + 本地工具 + Skill + 扩展

```python
from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.auth import AuthSource
from agent_core.tools.base import ToolRegistry
from agent_core.tools.local import create_all_tools
from agent_core.session.session import AgentSession
from agent_core.session.jsonl_store import JsonlStore
from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.loader import ResourceLoader
from agent_core.extensions.base import Extension

async def build_session():
    cwd = "/var/projects/foo"
    loader = ResourceLoader(cwd=cwd)
    skills, _   = loader.load_skills()
    context_files = loader.load_context_files()

    tool_registry = ToolRegistry()
    for tool in create_all_tools(cwd).values():
        tool_registry.register(tool)

    prompt = SystemPromptBuilder(base_prompt="You are a coding assistant.").build(
        cwd=cwd,
        active_tools=tool_registry.to_definitions(),
        skills=skills,
        context_files=context_files,
    )

    provider = OpenAIProvider()
    agent = Agent(
        initial_state=AgentState(
            system_prompt=prompt.text,
            model=provider.list_models()[0],
            tools=tool_registry.to_definitions(),
        ),
        provider=provider,
        auth_source=AuthSource.env("OPENAI_API_KEY"),
        tool_registry=tool_registry,
    )

    class AuditExt:
        name = "audit"
        async def on_event(self, ctx, evt): ...
        async def on_before_tool_call(self, ctx, call): return None
        async def on_after_tool_call(self, ctx, call, result):
            log({"tool": call.name, "is_error": result.is_error})
            return None

    session = AgentSession(
        agent=agent,
        store=JsonlStore("/var/agent-sessions"),
        session_id="user-123-conv-456",
        extensions=[AuditExt()],
    )
    await session.start()
    return session
```

更直接的做法 —— 走 scene 层:

```python
from scene.cli.chat_assistant import ChatAssistant

assistant = await ChatAssistant.create(
    provider_name="openai",
    model_id="gpt-4o",
    session_id="user-123-conv-456",
)
await assistant.send_message("帮我重构 src/utils.py")
```

### 7.4 公共 API 表

| API | 用途 |
|---|---|
| `Agent.prompt / continue_ / abort / wait_for_idle / reset` | 触发与控制 |
| `Agent.steer / follow_up / clear_all_queues` | 流式中插入消息 |
| `Agent.provide_human_input(tool_call_id, values)` | 解决 HITL |
| `Agent.subscribe(listener) -> Unsubscribe` | 事件订阅 |
| `AgentSession.start / prompt / continue_ / compact / dispose` | 会话生命周期 |
| `ToolRegistry.register / list / to_definitions` | 动态工具管理 |
| `ModelRegistry.register_provider / find / list_available / get_auth` | 多 provider 管理 |
| `AuthSource.static / env / dynamic` | 凭证来源 |
| `SystemPromptBuilder.build` | 动态拼装 system prompt |
| `ResourceLoader.load_skills / load_context_files / ...` | 资源发现 |

### 7.5 技术栈

| 用途 | 选型 | 理由 |
|---|---|---|
| 异步运行时 | `asyncio`(stdlib) | 标准、生态最广 |
| 数据模型 | `pydantic >= 2.5` | JSON Schema 输出、判别联合、严格校验 |
| HTTP 客户端 | `httpx >= 0.27` | async/sync 双栈、SSE 友好;同时是 provider 直连基础 |
| 路径匹配 | `pathspec >= 0.12` | gitignore 风格匹配,资源 ignore 用 |
| YAML | `pyyaml >= 6.0` | skill / prompt frontmatter |
| Scene HTTP | `fastapi >= 0.110`, `uvicorn[standard] >= 0.30` | `scene/http_sse` 使用 |
| MCP(预留) | `mcp >= 1.0`(extras) | 官方 Python SDK,适配器尚未实现 |
| MongoDB(预留) | `motor >= 3.4`(extras) | 异步 MongoDB,Store 适配器尚未实现 |
| 取消信号 | `asyncio.Event` | 跨任务取消,贯穿 loop / tool / HITL |
| 测试 | `pytest` + `pytest-asyncio`(`asyncio_mode = "auto"`) + `respx` | mock httpx;`tests/conftest.py` 提供 `FakeProvider` |
| 打包 | `pyproject.toml` + `hatchling` | PEP 621 |

**Python 版本**:>= 3.11(使用 `typing.Self`、`asyncio.timeout`、`tomllib`、判别联合语法)。

---

## 8. 与 pi-mono 的对应关系(参考索引)

| pi-mono(TS) | agent-core(Python) | 状态 |
|---|---|---|
| `demo/agent/src/agent.ts` | `agent_core/core/agent.py` | ✅ |
| `demo/agent/src/agent-loop.ts` | `agent_core/core/loop.py` + `core/tool_runner.py` | ✅ |
| `demo/agent/src/types.ts` | 拆分为 `core/state.py` + `messages.py` + `content.py` + `events.py` | ✅ |
| `demo/core/agent-session.ts` | `agent_core/session/session.py` | ✅ |
| `demo/core/session-manager.ts` | `session/store.py` + `inmemory_store.py` / `jsonl_store.py` | ✅(无 Mongo) |
| `demo/core/compaction/` | `agent_core/compaction/` | ✅(无 overflow 自动重试) |
| `demo/core/extensions/` | `agent_core/extensions/` | ✅(钩子集合较窄) |
| `demo/core/tools/` | `agent_core/tools/`(HTTP + local + music + 渲染) | ✅(无 MCP / 插件加载) |
| `demo/core/model-registry.ts` | `agent_core/providers/registry.py` + `auth.py` | ✅ |
| `demo/ai/` 各 provider | `agent_core/providers/*.py`(直连 httpx) | ✅ |
| `demo/core/system-prompt.ts` | `agent_core/prompts/builder.py` + `guidelines.py` + `snippets.py` | ✅ |
| `demo/core/resources/` | `agent_core/resources/` | ✅ |
| `demo/core/skills/` | `agent_core/resources/skills.py`(实现) + `agent_core/skills/`(占位包) | ✅ |
| `demo/extensions/cli` 等 scene | `scene/cli` / `scene/http_sse` / `scene/voice_ws` | ✅(语音 TODO) |
| pi-mono `session-manager` 的树状分支 | — | 未实现,留 v2 |
| `tools/bash.ts` / `read.ts` 等 | `agent_core/tools/local/*.py` | ✅(在框架内提供) |

---

## 9. 后续路线(v2+ 草案)

1. **MCP 工具适配**:`tools/mcp_tool.py` + `MCPClient`(stdio / sse / streamable-http transport),把 MCP server 工具映射成 `Tool`。
2. **用户工具插件**:`agent_core.tools` entry point + 目录扫描 + 进程内/子进程隔离两档。
3. **会话分支与树导航**:`navigate_tree`、`branch_summary`、forked sessions。
4. **MongoDB Store**:基于 `motor` 实现 `SessionStore` 协议,索引 `(session_id, seq)`。
5. **服务端沙箱**:Bash/Python 在容器(Docker / Firecracker)中执行;`LocalBashOperations` 的远程版本。
6. **客户端代理工具**:WebSocket 双向 RPC,工具在浏览器/IDE 端执行。
7. **会话导出**:HTML / Markdown 报告。
8. **观察性**:OpenTelemetry trace / metrics / structured logs,扩展 `logging_config.py`。
9. **多租户运营**:owner/tenant 字段、quota、rate limit、审计聚合(可作为扩展实现)。
10. **压缩 overflow 自动重试**:provider 抛上下文溢出 → `LLMSummaryCompactor.compact(reason="overflow")` → 自动 `continue_()`,带防抖。
11. **扩展钩子扩面**:补齐 `register_command` / `register_tool` / `session_before_compact` / `before_agent_start` 等。
12. **`scene/voice_ws`**:完成 ASR/TTS 桥接。

以上均可在 v1 现有抽象之上叠加,不会破坏核心 API。

---

## 10. Memory & Retrieval

两个可选子系统，基于现有 Extension 和 Tool Protocol。`agent_core/core/` 零改动。

### 10.1 Protocols

- `Retriever`（`retrieval/base.py`）：无状态 query→chunks 接口
- `MemoryStore`（`memory/base.py`）：session 范围的读写接口（remember / recall / forget）

两者有意分开 —— 合并会迫使 mem0（事实提取）和 Pinecone（向量搜索）等后端采用别扭的 API 形状。

### 10.2 运行时桥接

| 桥接 | 模块 | 机制 |
|---|---|---|
| `RetrieverTool` | `retrieval/tool.py` | Tool Protocol — 智能体 RAG，模型按需调用 |
| `AutoRetrievalExtension` | `retrieval/extension.py` | Extension + `transform_context` — 经典 RAG，每 turn 自动注入 |
| `MemoryExtension` | `memory/extension.py` | Extension + `transform_context` — 持久化用户消息，召回为系统注释 |

`AgentSession.start()` 链式组合 Extension 的 `transform_context` 方法到 `AgentLoopConfig.transform_context` 槽，与 `before_tool_call` 使用相同的 monkey-patch 模式。

### 10.3 内置适配器

- `InMemoryRetriever`（关键词重叠评分）—— 测试、演示
- `InMemoryMemoryStore`（token 重叠 + 时间回退排序）—— 测试、单进程状态

真实后端（mem0、Pinecone、PGVector、Chroma）在后续工作中加入，由 `pyproject.toml` extras 控制。

### 10.4 设计提示

- `MemoryExtension` 当前**原样持久化用户消息**。生产环境建议外接带事实抽取的后端（如 mem0），否则连续追问会把上一轮提问本身当作"记忆"召回。
- Extension 注册顺序决定 `transform_context` 包裹顺序：**后注册的更靠近模型**。
