# agent-core 设计文档

> 通用 Python Agent 框架(库级别)。参考 `demo/` 中 pi-mono(`pi-agent-core` + `AgentSession`)的架构,以 Python 重新实现并适应云端部署。
> 框架只交付库与抽象,具体的服务运行时(API server、Worker、部署拓扑)由消费者按场景实现。

---

## 0. 范围与目标

**目标**

- 提供一个 **多用户、可扩展、通用** 的 Python Agent 框架。
- 支持流式 LLM 交互、工具调用、上下文压缩、扩展(Hook)体系。
- 不绑定任何服务形态;可被 FastAPI、Celery、CLI、Notebook 等任意宿主消费。
- 抽象优先,实现适配:存储、LLM、工具来源均通过 Protocol 注入。

**v1 包含**

1. Agent 运行时核心(状态 + 事件 + 工具循环 + 流式)
2. 工具体系(HTTP API、MCP、用户自定义插件)
3. LLM 多提供商抽象(OpenAI / Anthropic + 自定义)
4. 会话与存储抽象(`SessionStore` + 内置 InMemory/JSONL,可选 MongoDB)
5. 上下文压缩(自动 + 手动 + 溢出恢复)
6. 扩展/Hook 体系(生命周期、工具拦截、命令注册、动态工具)

**v1 不包含**(留作上层或扩展)

- 服务运行时(API/Worker/Gateway/SSE)
- 多租户运营能力(billing/quota/rate-limit/audit)
- 会话分支与树导航(`navigateTree`、`branch_summary`)
- 服务端沙箱执行(Bash/Python/Docker)
- 客户端代理工具
- Skill/Prompt template 文件加载
- HTML/Markdown 导出

---

## 1. 整体分层与模块布局

### 1.1 设计原则

- **异步优先**:全栈 `asyncio`,公共调用是 coroutine 或 async generator。
- **接口在框架内、实现在适配器**:存储/LLM/工具来源都先定义 Protocol,再附内置实现。
- **分层单向依赖**:`core ← session ← extensions`,上层依赖下层。
- **显式优于隐式**:状态用 Pydantic 模型表达;事件用判别联合(discriminated union)分发。
- **YAGNI**:v1 只做必要功能,沙箱、分支、运营能力放扩展点。

### 1.2 包结构

```
agent_core/
├── core/                         # 不依赖任何 IO 的纯运行时
│   ├── agent.py                  # Agent 类:状态 + 事件 + prompt 循环
│   ├── loop.py                   # agent_loop / agent_loop_continue
│   ├── types.py                  # AgentState / AgentMessage / AgentEvent
│   ├── queue.py                  # SteeringQueue / FollowUpQueue
│   └── tokens.py                 # token 估算工具
├── tools/                        # 工具抽象与适配器
│   ├── base.py                   # Tool / ToolResult / ToolRegistry
│   ├── http_tool.py              # HTTP API 工具适配
│   ├── mcp_tool.py               # MCP 客户端 → AgentTool
│   └── plugin_tool.py            # 用户插件加载(入口点 + 动态导入)
├── providers/                    # LLM 多提供商适配
│   ├── base.py                   # ModelProvider Protocol / StreamEvent
│   ├── registry.py               # ModelRegistry / 凭证解析
│   ├── openai_provider.py        # OpenAI(含 OpenAI 兼容端点)
│   └── anthropic_provider.py     # Anthropic
├── session/                      # 会话与持久化
│   ├── session.py                # AgentSession(组合 Agent + Store + Extensions)
│   ├── store.py                  # SessionStore Protocol
│   ├── inmemory_store.py         # 默认内存实现
│   ├── jsonl_store.py            # 文件 JSONL 实现
│   └── mongo_store.py            # 可选 MongoDB 适配器(extras 依赖)
├── compaction/
│   ├── compactor.py              # 自动 + 手动压缩
│   └── strategies.py             # 阈值/溢出策略
├── extensions/
│   ├── base.py                   # Extension / Hook 协议
│   ├── runner.py                 # 事件分发 + 命令注册
│   └── events.py                 # ExtensionEvent 联合类型
└── __init__.py                   # 顶层导出
```

### 1.3 依赖矩阵

| 层 | 依赖 |
|---|---|
| `core/` | stdlib + pydantic |
| `tools/` | `core` + httpx + mcp(可选) |
| `providers/` | `core` + httpx + 各 SDK(可选) |
| `session/` | `core` + motor(可选 extras) |
| `compaction/` | `core` + `providers` |
| `extensions/` | `core`,通过事件耦合 `session` |

### 1.4 可选 extras(`pyproject.toml`)

```toml
[project.optional-dependencies]
mongo     = ["motor>=3.4"]
mcp       = ["mcp>=1.0"]
openai    = ["openai>=1.40"]
anthropic = ["anthropic>=0.34"]
all       = ["motor>=3.4","mcp>=1.0","openai>=1.40","anthropic>=0.34"]
```

---

## 2. Agent 运行时核心

### 2.1 核心类型

```python
# 消息内容块
class TextContent(BaseModel):       type: Literal["text"];      text: str
class ImageContent(BaseModel):      type: Literal["image"];     data: str; mime_type: str
class ToolCallContent(BaseModel):
    type: Literal["tool_call"]; id: str; name: str; arguments: dict

# 四类 AgentMessage(用 role 字段做判别联合)
class UserMessage(BaseModel):
    role: Literal["user"]
    content: list[TextContent | ImageContent]
    timestamp: float

class AssistantMessage(BaseModel):
    role: Literal["assistant"]
    content: list[TextContent | ToolCallContent]
    usage: Usage
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

AgentMessage = Annotated[
    Union[UserMessage, AssistantMessage, ToolResultMessage, CustomMessage],
    Field(discriminator="role"),
]
```

### 2.2 AgentState

```python
class AgentState(BaseModel):
    system_prompt: str = ""
    model: Model | None = None
    thinking_level: Literal["off","minimal","low","medium","high","xhigh"] = "off"
    tools: list[ToolDefinition] = []
    messages: list[AgentMessage] = []

    # readonly,由 Agent 维护
    is_streaming: bool = False
    streaming_message: AssistantMessage | None = None
    pending_tool_calls: set[str] = set()
    error_message: str | None = None
```

为对齐 pi-mono 的 setter 语义,`tools`/`messages` 在赋值时由 Agent 拷贝顶层列表(浅拷贝),mutate 已返回引用仍生效。

### 2.3 事件(AgentEvent)

判别联合,所有事件携带 `type` 字段:

| Event | 含义 |
|---|---|
| `agent_start` / `agent_end` | 一次 `prompt()` 调用的起止 |
| `turn_start` / `turn_end` | 单轮 LLM 调用 + 后续工具执行 |
| `message_start` / `message_update` / `message_end` | 消息生命周期(`message_update` 仅 assistant 携带流式 delta) |
| `tool_execution_start` / `tool_execution_update` / `tool_execution_end` | 工具调用生命周期 |

`subscribe` 监听器同步异步均可。`agent_end` 作为 await 屏障:`prompt()` 直到所有 `agent_end` 异步监听器完成才返回。

### 2.4 Agent 类

```python
class Agent:
    def __init__(self, *,
        initial_state: AgentState | None = None,
        provider: ModelProvider,
        convert_to_llm: ConvertToLlm | None = None,
        transform_context: TransformContext | None = None,
        before_tool_call: BeforeToolCall | None = None,
        after_tool_call: AfterToolCall | None = None,
        tool_execution: Literal["parallel","sequential"] = "parallel",
        steering_mode: Literal["all","one-at-a-time"] = "one-at-a-time",
        followup_mode: Literal["all","one-at-a-time"] = "one-at-a-time",
        session_id: str | None = None,
        thinking_budgets: ThinkingBudgets | None = None,
    ): ...

    state: AgentState

    def subscribe(self, listener: Callable[[AgentEvent], Awaitable | None]) -> Callable[[], None]: ...

    async def prompt(self, text_or_message: str | AgentMessage, *,
                     images: list[ImageContent] | None = None) -> None: ...
    async def continue_(self) -> None: ...     # 从现有上下文继续,要求最后一条是 user / tool_result

    def steer(self, msg: AgentMessage) -> None: ...
    def follow_up(self, msg: AgentMessage) -> None: ...
    def clear_all_queues(self) -> None: ...

    def abort(self) -> None: ...
    async def wait_for_idle(self) -> None: ...
    def reset(self) -> None: ...
```

### 2.5 Agent Loop(纯函数式 async generator)

```python
async def agent_loop(
    new_messages: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
) -> AsyncIterator[AgentEvent]:
    yield AgentStart()
    while True:
        yield TurnStart()
        llm_messages = await config.convert_to_llm(context.messages)
        if config.transform_context:
            llm_messages = await config.transform_context(llm_messages, signal)

        async for stream_evt in config.provider.stream(...):
            # 翻译 StreamEvent → AgentEvent,累积 AssistantMessage
            ...

        if assistant.has_tool_calls():
            await run_tool_calls(
                before=config.before_tool_call,
                after=config.after_tool_call,
                mode=config.tool_execution,
            )

        yield TurnEnd()
        if not (steering_queue or pending_tools or followup_queue):
            break
    yield AgentEnd()
```

`Agent` 类只是 `agent_loop` 的有状态包装,保留了 pi-mono 的"低阶 generator + 高阶 class"两层 API。

### 2.6 与 pi-mono 的语义差异

| 项 | TS(pi-mono) | Python 适配 |
|---|---|---|
| 事件订阅 | 同步回调 | sync/async 自动判别(`inspect.iscoroutinefunction`) |
| 状态 setter | get/set 属性 | Pydantic 模型 + `__setattr__` 钩子做拷贝 |
| `AbortSignal` | DOM AbortController | `asyncio.Event` 或 `anyio.CancelScope` |
| Schema | TypeBox | Pydantic v2 + `model_json_schema()` |
| 声明合并扩展消息 | TS declaration merging | `CustomMessage(custom_type=...)` |

---

## 3. 工具与插件体系

### 3.1 Tool 抽象

```python
class ToolResult(BaseModel):
    content: list[TextContent | ImageContent]
    details: Any | None = None              # UI/扩展用,不送 LLM

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict                        # JSON Schema
    prompt_snippet: str | None = None
    prompt_guidelines: list[str] = []

class Tool(Protocol):
    definition: ToolDefinition
    async def execute(
        self,
        tool_call_id: str,
        params: dict,
        ctx: ToolContext,
    ) -> ToolResult: ...

@dataclass
class ToolContext:
    signal: asyncio.Event
    on_update: Callable[[ToolResult], None] | None
    metadata: dict                          # session_id / user_id / 扩展注入
```

### 3.2 ToolRegistry

```python
class ToolRegistry:
    def register(self, tool: Tool, *, source: SourceInfo | None = None) -> None: ...
    def get(self, name: str) -> Tool | None: ...
    def list(self) -> list[ToolInfo]: ...
    def to_definitions(self) -> list[ToolDefinition]: ...
```

`AgentState.tools` 持有 `ToolDefinition`(轻量元数据);执行阶段由 Registry 解析到具体 `Tool` 实例。这允许同名替换、按需启用、按来源标记。

### 3.3 HTTP 工具适配器

```python
search_tool = HttpTool(
    name="web_search",
    description="Search the web",
    method="POST",
    url="https://api.example.com/search",
    auth=BearerAuth(env_var="SEARCH_API_KEY"),
    parameters={  # JSON Schema 或 Pydantic.model_json_schema()
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    request_template={"q": "{{query}}", "n": "{{limit}}"},
    response_transform=lambda r: r["results"],
)
```

执行流程:模板渲染 → `httpx.AsyncClient` 请求 → 反序列化 → 包成 `ToolResult`。失败抛异常,框架捕获后转 `is_error=True` 的 ToolResult。

### 3.4 MCP 工具适配器

```python
class MCPClient:
    """连接到 MCP server(stdio / sse / streamable-http),自动暴露其 tools。"""
    def __init__(self, transport: MCPTransport): ...
    async def connect(self) -> None: ...
    async def discover_tools(self) -> list[Tool]: ...
    async def close(self) -> None: ...
```

底层使用官方 `mcp` Python SDK。`discover_tools` 把每个 MCP 工具的描述与 JSON Schema 映射到 `ToolDefinition`,运行时通过 MCP RPC 转发调用。失败仅作为可选 extras 影响,不阻塞核心。

### 3.5 用户插件加载

**方式一:Python 入口点**(推荐)

```toml
# 用户插件包的 pyproject.toml
[project.entry-points."agent_core.tools"]
weather = "my_pkg.tools:WeatherTool"
```

框架启动调 `importlib.metadata.entry_points(group="agent_core.tools")`,自动 import 并注册。

**方式二:目录扫描**(轻量)

```python
PluginLoader.load_from_dir("/path/plugins")
```

扫描每个 `.py`,寻找 `register(registry)` 函数或继承 `Tool` 的类。

**隔离策略**

| 级别 | 实现 | 适用 |
|---|---|---|
| 进程内导入 | `importlib` | 受信任插件,v1 默认 |
| 子进程 | `asyncio.subprocess` + JSON-RPC | 不受信插件,v2+ |

v1 仅做"进程内导入 + 异常隔离":每个工具调用包在 try/except,异常转为 `is_error=True`。沙箱化留作扩展点。

### 3.6 Hook(before/after tool call)

```python
async def before_tool_call(ctx: BeforeToolCallContext) -> BeforeToolCallResult | None:
    if ctx.tool_call.name == "delete_database":
        return BeforeToolCallResult(block=True, reason="forbidden")

async def after_tool_call(ctx: AfterToolCallContext) -> AfterToolCallResult | None:
    if not ctx.is_error:
        return AfterToolCallResult(details={**ctx.result.details, "audited": True})
```

挂在 `Agent` 构造参数上,Loop 在工具执行边界调用。

---

## 4. LLM 多提供商抽象

### 4.1 核心契约

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
    async def stream(
        self,
        model: Model,
        messages: list[Message],
        tools: list[ToolDefinition],
        *,
        system_prompt: str,
        thinking_level: ThinkingLevel,
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
        auth: ProviderAuth,
    ) -> AsyncIterator[StreamEvent]: ...

    def list_models(self) -> list[Model]: ...
```

所有 provider 输出统一 `StreamEvent` 流,Agent loop 不感知任何 provider 细节。

### 4.2 ModelRegistry

```python
class ModelRegistry:
    def register_provider(self, name: str, provider: ModelProvider,
                          *, auth_source: AuthSource) -> None: ...
    def find(self, provider: str, model_id: str) -> Model | None: ...
    def list_available(self) -> list[Model]: ...
    async def get_auth(self, model: Model) -> ProviderAuth: ...
    def has_configured_auth(self, model: Model) -> bool: ...
```

**凭证解析顺序**

1. 显式注入(`AuthSource.static(api_key=...)`)
2. 环境变量(`AuthSource.env("OPENAI_API_KEY")`)
3. 异步回调(`AuthSource.dynamic(async_callback)`,适合 OAuth 刷新)
4. 失败抛 `MissingCredentialsError`,`prompt()` 启动前校验

### 4.3 OpenAI 适配器

- 输入 `AgentMessage[]` → OpenAI `chat.completions` 消息(经 `convert_to_llm` 钩子)
- 流式调用 → 把 `delta.content` / `tool_calls` / `usage` 映射成 `StreamEvent`
- `thinking_level` 映射为 OpenAI `reasoning_effort`(支持模型)
- **复用同一适配器适配 OpenAI 兼容端点**(vLLM、Together、自部署):构造时传 `base_url`

```python
openai = OpenAIProvider(base_url="https://api.openai.com/v1")
vllm   = OpenAIProvider(base_url="http://localhost:8000/v1", default_provider_name="vllm")
```

### 4.4 Anthropic 适配器

- 合并连续同角色消息(Anthropic 协议要求)
- `thinking_level` → `thinking.budget_tokens`(用 `ThinkingBudgets` 查表)
- 工具走 `tool_use` / `tool_result` 块
- 流式 `content_block_delta` / `message_delta` 映射

### 4.5 思考等级映射

```python
class ThinkingBudgets(BaseModel):
    minimal: int = 128
    low: int = 512
    medium: int = 1024
    high: int = 2048
    xhigh: int = 4096
```

- token-based provider(Anthropic / Bedrock):用预算字段
- effort-based provider(OpenAI o-series):用字符串(`low/medium/high`)
- 不支持 reasoning 的 provider:`thinking_level="off"`,不下发任何字段

### 4.6 自定义/代理 streamFn

类似 pi-mono `streamProxy`,提供 `ProxyProvider(base_url, auth_token)` 让浏览器/Edge 把请求转发给中转后端。框架只交付客户端协议契约(JSON-Lines stream),不实现服务端。

---

## 5. Session、压缩与扩展

### 5.1 AgentSession

`Agent` 是纯运行时;`AgentSession` 是组合层 —— Agent + 存储 + 压缩 + 扩展:

```python
class AgentSession:
    def __init__(self, *,
        agent: Agent,
        store: SessionStore,
        session_id: str,
        compactor: Compactor | None = None,
        extensions: list[Extension] | None = None,
        settings: SessionSettings | None = None,
    ): ...

    async def prompt(self, text: str, **opts) -> None: ...
    async def compact(self, *, instructions: str | None = None) -> CompactionResult: ...
    async def abort(self) -> None: ...
    async def dispose(self) -> None: ...

    def subscribe(self, listener) -> Unsubscribe: ...

    @property
    def messages(self) -> list[AgentMessage]: ...
    @property
    def context_usage(self) -> ContextUsage | None: ...
```

**内部职责**

1. 订阅 `Agent` 事件 → 在 `message_end` 写入 `SessionStore`(事件追加,非全量覆盖)
2. `agent_end` 后检查上下文阈值,触发 `Compactor`
3. 把 `ExtensionRunner` 挂到 `before_tool_call` / `after_tool_call` 钩子,并把所有事件转发给扩展

### 5.2 SessionStore

```python
class SessionStore(Protocol):
    async def create_session(self, session_id: str, header: SessionHeader) -> None: ...
    async def append_entry(self, session_id: str, entry: SessionEntry) -> None: ...
    async def load_session(self, session_id: str) -> SessionSnapshot: ...
    async def list_sessions(self, *, owner: str | None = None, limit: int = 50) -> list[SessionMeta]: ...
    async def close(self) -> None: ...
```

**SessionEntry**(JSONL 风格的追加项):

```python
SessionEntry = Union[
    MessageEntry,                  # {type:"message", message:AgentMessage, parent_id, id}
    CompactionEntry,               # {type:"compaction", summary, first_kept_entry_id, tokens_before}
    ModelChangeEntry,
    ThinkingLevelChangeEntry,
    CustomEntry,                   # 扩展用,custom_type + data
]
```

**内置实现**

| Store | 用途 |
|---|---|
| `InMemoryStore` | 测试 / 短期会话,只在进程内 |
| `JsonlStore(dir)` | 本地开发 / 单机部署,每会话一个 `.jsonl` |
| `MongoStore(db)`(extras) | 生产推荐;`sessions` collection 存 header,`session_entries` 存追加项,按 `(session_id, seq)` 复合索引 |

`MongoStore` 使用 `motor` 异步驱动,实现 `SessionStore` 协议;调用方不感知 Mongo 细节。

### 5.3 Compactor

```python
class Compactor(Protocol):
    def should_compact(self, ctx_tokens: int, ctx_window: int) -> bool: ...
    async def compact(
        self,
        branch: list[SessionEntry],
        *,
        reason: Literal["manual","threshold","overflow"],
        instructions: str | None = None,
        signal: asyncio.Event,
    ) -> CompactionResult: ...
```

**默认策略 `LLMSummaryCompactor`**

- 触发阈值:`tokens >= window * threshold`(默认 80%)
- 算法:保留最近 N 条消息(可配)+ 对早期消息用同 provider 生成摘要,产出 `CompactionEntry`
- **三种触发场景**(沿用 pi-mono):
  1. `manual` — 用户调 `session.compact()`
  2. `threshold` — `agent_end` 后达阈值,执行后**不自动重试**
  3. `overflow` — provider 返回 context overflow 错误,压缩后**自动 `continue_()`**,且只重试一次防止死循环

策略可替换(`StructuredCompactor`、`RollingWindowCompactor` 等)。

### 5.4 Extension

```python
class Extension(Protocol):
    name: str
    async def on_session_start(self, ctx: ExtensionContext) -> None: ...
    async def on_message_end(self, ctx: ExtensionContext, msg: AgentMessage) -> None: ...
    async def on_tool_call(self, ctx, evt: ToolCallEvent) -> ToolCallResult | None: ...
    async def on_tool_result(self, ctx, evt: ToolResultEvent) -> ToolResultResult | None: ...
    async def on_before_agent_start(self, ctx, text, images) -> BeforeAgentStartResult | None: ...
    # ... 完整事件参见 extensions/events.py
```

**能力分类**(对齐 pi-mono)

| 类别 | 作用 |
|---|---|
| 生命周期事件 | `session_start/shutdown`、`agent_start/end`、`turn_*`、`message_*` |
| 工具拦截 | `tool_call` / `tool_result`(可改写/阻断) |
| 上下文修改 | `before_agent_start`(注入额外消息、改 system prompt) |
| 命令注册 | `register_command("/foo", handler)` |
| 工具注册 | `register_tool(my_tool)` —— 动态向 Registry 注入 |
| 资源发现 | `resources_discover(cwd)` —— 返回 skills/prompts 路径 |
| 压缩拦截 | `session_before_compact`(扩展提供自定义摘要) |

**ExtensionRunner**

- 按注册顺序 await 各扩展的 hook
- 异常隔离:一个扩展抛错不影响其他扩展,通过 `on_error` 上报
- 提供 `ExtensionContext`,注入 session 操作能力(`send_message` / `set_model` / `compact` / `get_active_tools` ...)

**加载方式**

- 显式:`AgentSession(extensions=[MyExt(), AuditExt()])`
- 入口点:`[project.entry-points."agent_core.extensions"]`

---

## 6. 公共 API、使用示例与技术栈

### 6.1 顶层导出

```python
# 运行时
from agent_core.core import Agent, AgentEvent, AgentState, AgentMessage
from agent_core.core import UserMessage, AssistantMessage, ToolResultMessage, CustomMessage

# 工具
from agent_core.tools import Tool, ToolDefinition, ToolResult, ToolRegistry
from agent_core.tools import HttpTool, MCPClient, PluginLoader

# Provider
from agent_core.providers import Model, ModelProvider, ModelRegistry, StreamEvent
from agent_core.providers import OpenAIProvider, AnthropicProvider

# Session / Store / Compaction
from agent_core.session import AgentSession, SessionStore
from agent_core.session import InMemoryStore, JsonlStore
from agent_core.compaction import Compactor, LLMSummaryCompactor

# Extensions
from agent_core.extensions import Extension, ExtensionContext
```

### 6.2 最小示例:流式问答

```python
import asyncio
from agent_core import Agent, AgentState, OpenAIProvider, Model

async def main():
    provider = OpenAIProvider(api_key_env="OPENAI_API_KEY")
    agent = Agent(
        initial_state=AgentState(
            system_prompt="You are a helpful assistant.",
            model=Model(provider="openai", id="gpt-4o", context_window=128_000, max_output_tokens=4096),
        ),
        provider=provider,
    )

    async def on_event(evt):
        if evt.type == "message_update" and evt.delta.type == "text_delta":
            print(evt.delta.text, end="", flush=True)

    agent.subscribe(on_event)
    await agent.prompt("Hello!")

asyncio.run(main())
```

### 6.3 完整示例:Session + 自定义工具 + MCP + 扩展

```python
from agent_core import (
    AgentSession, Agent, AgentState, JsonlStore, ToolRegistry,
    OpenAIProvider, AnthropicProvider, ModelRegistry, AuthSource,
    HttpTool, MCPClient, Extension,
)
from agent_core.compaction import LLMSummaryCompactor

async def build_session():
    # 1. Providers
    registry = ModelRegistry()
    registry.register_provider("openai", OpenAIProvider(), auth_source=AuthSource.env("OPENAI_API_KEY"))
    registry.register_provider("anthropic", AnthropicProvider(), auth_source=AuthSource.env("ANTHROPIC_API_KEY"))

    # 2. Tools
    tools = ToolRegistry()
    tools.register(HttpTool(
        name="weather",
        url="https://api.weather.com/v1/forecast",
        method="GET",
        parameters={"type":"object","properties":{"city":{"type":"string"}},"required":["city"]},
    ))
    mcp = MCPClient(transport=StdioTransport("knowledge-mcp"))
    await mcp.connect()
    for t in await mcp.discover_tools():
        tools.register(t)

    # 3. 自定义扩展
    class AuditExt(Extension):
        name = "audit"
        async def on_tool_result(self, ctx, evt):
            await log({"tool": evt.tool_name, "is_error": evt.is_error})

    # 4. Session
    model = registry.find("anthropic", "claude-sonnet-4-6")
    agent = Agent(
        initial_state=AgentState(
            system_prompt="You are a planner.",
            model=model,
            tools=tools.to_definitions(),
        ),
        provider=registry.get_provider("anthropic"),
    )
    session = AgentSession(
        agent=agent,
        store=JsonlStore("/var/agent-sessions"),
        session_id="user-123-conv-456",
        compactor=LLMSummaryCompactor(threshold=0.8),
        extensions=[AuditExt()],
    )
    return session
```

### 6.4 公共 API 表

| API | 用途 |
|---|---|
| `Agent.prompt / continue_ / abort` | 触发与控制 |
| `Agent.steer / follow_up / clear_all_queues` | 流式中插入消息 |
| `Agent.subscribe(listener) -> Unsubscribe` | 事件订阅 |
| `AgentSession.compact / set_model / set_thinking_level` | 会话能力 |
| `ToolRegistry.register / list / set_active_tools` | 动态工具管理 |
| `ModelRegistry.register_provider / find / list_available` | 多 provider 管理 |
| `ExtensionContext.send_message / set_model / compact / get_active_tools` | 扩展能力 |

### 6.5 技术栈

| 用途 | 选型 | 理由 |
|---|---|---|
| 异步运行时 | `asyncio`(stdlib) | 标准、生态最广 |
| 数据模型 | `pydantic >= 2.5` | JSON Schema 输出、判别联合、严格校验 |
| HTTP 客户端 | `httpx >= 0.27` | async/sync 双栈、SSE 友好 |
| MongoDB(可选) | `motor >= 3.4` | 异步 MongoDB |
| MCP(可选) | `mcp >= 1.0` | 官方 Python SDK |
| 取消信号 | `asyncio.Event` / `anyio.CancelScope` | 跨任务取消 |
| 测试 | `pytest` + `pytest-asyncio` + `respx` | mock httpx |
| 打包 | `pyproject.toml` + `hatchling` | PEP 621 |

**Python 版本**:>= 3.11(使用 `typing.Self`、`asyncio.timeout`、`tomllib`)。

---

## 7. 与 pi-mono 的对应关系(参考索引)

| pi-mono(TS) | agent-core(Python) |
|---|---|
| `demo/agent/src/agent.ts` | `agent_core/core/agent.py` |
| `demo/agent/src/agent-loop.ts` | `agent_core/core/loop.py` |
| `demo/agent/src/types.ts` | `agent_core/core/types.py` |
| `demo/core/agent-session.ts` | `agent_core/session/session.py` |
| `demo/core/session-manager.ts` | `agent_core/session/store.py` + 内置 stores |
| `demo/core/compaction/` | `agent_core/compaction/` |
| `demo/core/extensions/` | `agent_core/extensions/` |
| `demo/core/tools/` | `agent_core/tools/`(只保留 HTTP/MCP/Plugin,不带 bash/edit/read/write 等本地工具) |
| `demo/core/model-registry.ts` | `agent_core/providers/registry.py` |
| `demo/ai/` 各 provider | `agent_core/providers/*.py` |

不实现的 pi-mono 模块:`session-manager` 的树状分支(branch/fork)、`extensions/loader.ts` 的文件路径扫描(由入口点替代)、`tools/bash.ts` 等本地系统工具。

---

## 8. 后续路线(v2+ 草案)

1. **会话分支与树导航**:`navigate_tree`、`branch_summary`、forked sessions
2. **多租户运营**:owner/tenant 字段、quota、rate limit、审计日志聚合
3. **服务端沙箱执行**:Bash/Python 在容器(Docker/Firecracker)内运行
4. **客户端代理工具**:WebSocket 双向 RPC,工具在浏览器/IDE 执行
5. **资源加载器**:Skill / Prompt 模板从文件系统加载并注入 system prompt
6. **会话导出**:HTML / Markdown 报告
7. **观察性**:OpenTelemetry trace、metrics、structured logs

这些都可基于 v1 扩展点叠加,不会破坏核心 API。
