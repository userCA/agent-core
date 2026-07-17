# Agent 核心框架设计文档

> 本文档提炼自 agent-core（Python）项目的架构设计理念，旨在为其他语言/场景的复刻提供完整的设计蓝图。
> 文档聚焦**设计理念与架构决策**，不绑定任何具体语言实现。

---

## 1. 设计哲学

### 1.1 六大核心原则

| 原则 | 含义 | 为什么重要 |
|------|------|-----------|
| **异步优先** | 全栈异步运行时，所有公共 API 是协程或异步生成器 | LLM 调用天然异步，工具执行可并行，阻塞式 API 会浪费并发能力 |
| **Protocol 驱动** | 存储/LLM/工具均先定义接口协议，再附内置实现 | 实现可任意替换，框架不绑定任何具体后端 |
| **分层单向依赖** | core ← session ← extensions，绝不引入循环依赖 | 核心层零 IO 依赖，可独立测试和推理 |
| **显式优于隐式** | 状态用数据模型表达，事件用判别联合分发 | 消灭隐式副作用，让状态流转可追踪 |
| **YAGNI** | 只做必要功能，沙箱/分支/运营能力放扩展点 | 避免过早抽象，让架构在真实需求驱动下演进 |
| **库 ≠ 服务** | 核心库不依赖任何 Web 框架，服务运行时由消费者实现 | 同一个 Agent 核心可被 FastAPI、CLI、Notebook、WebSocket 等任意宿主消费 |

### 1.2 核心设计精髓：纯异步生成器驱动的 Agent Loop

整个框架的设计围绕一个核心理念展开：**Agent Loop 是一个纯异步生成器**。

- Loop 本身不持有任何可变状态，所有依赖通过值对象（Context + Config）注入
- Loop 产出事件流（Event Stream），由外部消费者决定如何处理（持久化、渲染、转发）
- 这种设计使得核心循环可以被独立测试、推理和组合

**为什么不用面向对象封装？** 面向对象倾向于把状态藏在对象内部，导致并发调试困难、状态流转不透明。纯生成器 + 值对象的组合，让每一轮循环的输入输出完全可预测。

### 1.3 渐进式复杂度

框架的使用复杂度与场景需求匹配，不存在"必须全量引入"的负担：

| 场景 | 所需组件 | 代码量级 |
|------|---------|---------|
| 最简问答 | run_agent_loop + Provider（库级） | ~30 行 |
| 带工具 | run_agent_loop + ToolRegistry | ~50 行 |
| 生产会话 | AgentHarness + Store + Compactor + Extensions | ~60 行 |
| 完整服务 | Scene 层 + 路由 + 认证 | 宿主应用职责 |

### 1.4 AgentHarness 成熟度边界（相对 pi-mono）

| 状态 | 能力 |
|------|------|
| **已做** | emit-sink loop、phase、turn snapshot、save point、pending writes、active tools（含首 turn）、stream options、provider hooks、resources snapshot、next_turn、run_when_idle、session 配置重放、persist/hook 错误码 |
| **不做** | Session tree / `navigateTree` / durable leaf（YAGNI；宿主可自建） |
| **planned** | `skill()` + SkillStart/SkillEnd、`HarnessSession` facade、更广的 reentrancy 矩阵（持续补测） |

生产宿主应始终使用 `AgentHarness`，直接调用 `run_agent_loop`；低层集成可直接使用 `run_agent_loop` + emit sink。

---

## 2. 分层架构

### 2.1 五层模型

```
┌─────────────────────────────────────────────────────────┐
│  Scene 层（示例宿主，非框架本体）                         │
│  CLI / HTTP SSE / WebSocket / 飞书 / 任意前端             │
├─────────────────────────────────────────────────────────┤
│  Session 层（Harness 编排层）                            │
│  AgentHarness → run_agent_loop + Store + Extensions     │
├─────────────────────────────────────────────────────────┤
│  Agent Loop（纯异步生成器）                               │
│  流式 LLM → 执行工具 → 循环，产出 AgentEvent              │
├─────────────────────────────────────────────────────────┤
│  基础设施层                                              │
│  Providers │ Tools │ Prompts │ Resources │ Compaction   │
└─────────────────────────────────────────────────────────┘
```

**调用链（生产）：** `Scene → AgentHarness.prompt → AgentHarness._execute_turn → run_agent_loop`

**Breaking change（2026-07-17）：** 删除 Python `Agent` 编排类与 `AgentSession` 别名。迁移：`Agent(...) + AgentSession(...)` → 单个 `AgentHarness(...)`。

### 2.2 依赖矩阵与边界规则

| 层 | 允许依赖 | 禁止依赖 |
|---|---------|---------|
| Core（Loop/Events/State/Messages） | 标准库 + 数据模型库（如 Pydantic） | 任何 IO 库、网络库、文件系统 |
| Tools | Core + HTTP 客户端 | Session、Scene |
| Providers | Core + HTTP 客户端 + 各 SDK（可选） | Session、Scene |
| Session | Core | Scene、具体 Web 框架 |
| Extensions | Core，通过事件耦合 Session | 具体 Web 框架 |
| Prompts | Core + Tools + Resources | Session、Scene |
| Resources | 标准库 + YAML/路径匹配库 | Core 运行时 |
| Scene | 全部 + Web 框架 | — |

**核心边界规则**：Core 层是"零 IO"的。它不知道网络、文件、数据库的存在。所有 IO 通过 Protocol 接口注入，由上层提供实现。

### 2.3 每层的职责边界

**Core 层**
- 职责：定义消息模型、事件模型、状态模型、Agent Loop 算法
- 不包含：持久化、网络通信、具体工具实现

**Provider 层**
- 职责：将不同 LLM 厂商的 API 统一为同一个流式接口
- 不包含：消息历史管理、工具执行逻辑

**Tools 层**
- 职责：定义工具协议，提供工具注册表和内置工具实现
- 不包含：工具的 LLM 调用逻辑（那是 Loop 的职责）

**Session 层**
- 职责：组合 Agent + Store + Compactor + Extensions，管理会话生命周期
- 不包含：HTTP 路由、WebSocket 管理

**Scene 层**
- 职责：对接具体前端协议（HTTP SSE、CLI、WebSocket），处理认证和路由
- 不包含：Agent 核心逻辑

---

## 3. 核心抽象

### 3.1 消息模型

消息是 Agent 与世界交互的唯一载体。设计采用**两层结构**：Content Block → Message。

```
Content Block（内容块，按 type 字段判别）
├── TextContent        — 纯文本
├── ImageContent       — base64 图片（多模态输入）
└── ToolCallContent    — 工具调用声明（id + name + arguments）

Message（消息，按 role 字段判别，4 种角色）
├── UserMessage        — 用户输入，content: [Text | Image]
├── AssistantMessage   — LLM 输出，content: [Text | ToolCall]，附带 Usage + StopReason
├── ToolResultMessage  — 工具执行结果，附带 is_error 标志
└── CustomMessage      — 扩展用途（如压缩摘要、系统注入）
```

**设计决策**：
- **为什么用判别联合而非继承？** 判别联合（Discriminated Union）在序列化/反序列化时天然支持，且避免了继承层次的复杂性
- **为什么 AssistantMessage 同时包含 Text 和 ToolCall？** LLM 的单次响应可能同时输出文本思考和工具调用请求，拆开会导致时序混乱
- **为什么有 CustomMessage？** 为扩展预留通道，避免每新增一种消息类型就要修改核心

### 3.2 Agent Loop：ReAct 循环

Agent Loop 是整个框架的心脏，遵循经典的 ReAct（Reasoning + Acting）模式：

```
agent_loop(new_messages, context, config, signal)
│
├── 发出 AgentStart 事件
├── 将新消息追加到上下文
│
└── while True:  ← 核心循环
    │
    ├── 检查终止条件（signal / max_turns）
    ├── 发出 TurnStart 事件
    │
    ├── 【Reason 阶段】
    │   ├── 将内部消息转换为 Provider 格式
    │   ├── （可选）transform_context 注入 RAG/Memory
    │   ├── 解析认证凭证
    │   └── 流式调用 LLM，发出 MessageStart → MessageUpdate(delta) → MessageEnd
    │
    ├── 【Act 阶段】
    │   └── 如果 LLM 输出了工具调用：
    │       ├── 发出 ToolExecutionStart
    │       ├── 执行工具（并行/串行）
    │       ├── 发出 ToolExecutionUpdate（串行模式中间结果）
    │       └── 发出 ToolExecutionEnd
    │
    ├── 发出 TurnEnd 事件
    │
    └── 循环判断：
        ├── stop_reason ∈ {error, aborted} → 终止
        ├── 有工具执行结果 → 继续（下一轮 LLM 观察结果）
        ├── steering 队列有消息 → 注入 → 继续
        ├── follow_up 队列有消息 → 注入 → 继续
        └── 以上皆否 → 终止
│
└── 发出 AgentEnd 事件
```

**关键设计决策**：

1. **Loop 是纯函数式生成器** — 不持有 Agent、不持有 Store、不持有任何可变引用。所有依赖通过 `context`（值对象）和 `config`（值对象）注入。这使得 Loop 可以被独立测试（mock 所有注入），也可以在 Worker 进程中运行。

2. **重试逻辑内嵌于 Loop** — 可重试错误（如 429/503）使用指数退避重试；上下文溢出错误触发压缩后重试。这避免了将重试逻辑分散到多个层。

3. **工具执行模式可配置** — parallel（默认，`asyncio.gather` + Semaphore 限流）和 sequential（逐个执行，支持中间结果推送和 HITL 中断）。

### 3.3 事件系统

事件是整个系统的神经系统，贯穿从 Loop 到 Scene 的所有层。

**13 种 AgentEvent（按 type 字段判别）**：

| 类别 | 事件 | 触发时机 |
|------|------|---------|
| **生命周期** | AgentStart | 一次 prompt() 调用的起点 |
| | TurnStart | 单轮 LLM + 工具执行的起点 |
| | TurnEnd | 当前轮结束，携带 assistant 消息和工具结果 |
| | AgentEnd | 整个循环结束，携带本次产生的消息列表 |
| **消息流** | MessageStart | 新消息开始生成 |
| | MessageUpdate | 流式 delta（TextDelta / ThinkingDelta / ToolCallDelta） |
| | MessageEnd | 消息完整体 |
| **工具执行** | ToolExecutionStart | 工具调用开始 |
| | ToolExecutionUpdate | 工具中间结果推送（仅 sequential 模式） |
| | ToolExecutionEnd | 工具调用结束，携带结果和错误标志 |
| **人机交互** | HumanInputRequired | 工具中断等待用户输入 |
| **技能** | SkillStart / SkillEnd | 技能执行生命周期 |

**事件分发链**：

```
agent_loop 产出 AgentEvent
  → Agent._handle_event（更新 AgentState + 通知 listeners）
    → AgentSession._on_agent_event（持久化 + 压缩检查 + 扩展分发）
      → 外部 listeners（SSE 渲染 / CLI 输出 / WebSocket 推送）
```

**设计决策**：
- **为什么用事件驱动而非直接调用？** 事件驱动使得 Loop 不需要知道谁在消费它的输出。同一个事件流可以被持久化器、渲染器、分析器同时消费。
- **为什么 MessageUpdate 包含三种 delta 类型？** 文本、思考过程、工具调用是 LLM 输出的三种本质不同的内容，拆开可以让前端独立渲染。

### 3.4 状态管理

**AgentState** 是 Agent 的完整状态快照：

```
AgentState
├── system_prompt: str          — 系统提示词
├── model: Model                — 当前使用的模型
├── thinking_level: enum        — 思考深度等级
├── tools: [ToolDefinition]     — 可用工具定义列表
├── messages: [AgentMessage]    — 完整对话历史
├── is_streaming: bool          — 是否正在流式输出
├── streaming_message           — 当前正在生成的消息
├── pending_tool_calls: set     — 正在执行的工具调用
└── error_message: str?         — 最近错误信息
```

**消息队列** — 两个独立的待处理队列：

- **Steering Queue**：每个 TurnEnd 后消费，用于运行时注入中断/引导消息
- **Follow-up Queue**：steering 为空时消费，用于整次 prompt 结束后自动排入下一条消息

每个队列支持两种 drain 模式：`one-at-a-time`（每次取一条）和 `all`（每次取全部）。

---

## 4. 扩展机制

### 4.1 Tool Protocol

工具是 Agent 与外部世界交互的手段。Protocol 定义如下：

```
Tool（协议）
├── definition: ToolDefinition
│   ├── name: str
│   ├── description: str
│   ├── parameters: JSON Schema
│   ├── prompt_snippet: str?          — 注入 system prompt 的工具简介
│   ├── prompt_guidelines: [str]      — 注入 system prompt 的使用指南
│   ├── renderer: ToolRenderer?       — 自定义前端渲染逻辑
│   └── timeout_seconds: int?
│
└── execute(tool_call_id, params, ctx: ToolContext) → ToolResult
    ├── content: [TextContent | ImageContent]  — 返回给 LLM 的内容
    ├── details: Any?                          — 不送 LLM，供 UI/扩展使用
    └── display: dict?                         — 渲染层 hint
```

**ToolContext**（执行上下文）：
- `signal`: 取消信号（用于超时或用户中断）
- `on_update`: 中间结果推送回调（长耗时工具定期报告进度）
- `metadata`: 透传字典（session_id、HITL gate 等）
- `mutation_queue`: 文件写互斥队列

**ToolRegistry**（注册表）：
- 支持动态注册/注销/列举
- `to_definitions()` 输出轻量定义列表给 AgentState，运行时按需解析到具体实例
- 允许同名替换、按场景启用不同工具集

**FileMutationQueue**（文件互斥）：
- 每条文件路径一把异步锁
- 防止并行工具调用对同一文件的写冲突
- 提供 `read_locked / write_locked / edit_locked` 便利方法

### 4.2 Extension Protocol

扩展是框架的"插件系统"，在事件边界介入 Agent 行为：

```
Extension（协议）
├── name: str
├── on_event(ctx, evt)                    — 接收所有 AgentEvent
├── on_before_agent_start(ctx, prompt, system_prompt)
│   └── 可返回: { message, system_prompt } 注入内容
├── on_before_tool_call(ctx, tool_call)
│   └── 可返回:
│       ├── { block: true, reason }        — 阻止工具执行
│       ├── { mutated_args }               — 修改工具参数
│       └── { inject_metadata }            — 注入执行元数据
└── on_after_tool_call(ctx, tool_call, result)
    └── 可返回: { result: { content, details } }  — 修改工具结果
```

**ExtensionRunner**（扩展运行器）：
- 按注册顺序分发事件
- **错误隔离**：单个扩展抛异常不影响其他扩展和主流程
- `before_tool_call` 的多个返回值合并策略：metadata 合并、mutated_args 合并、block 短路（任一阻止则阻止）
- `after_tool_call` 形成链式变异：前一个扩展的结果传给后一个

**transform_context 特殊钩子**：
- 在 LLM 调用前转换消息列表（用于 RAG/Memory 注入）
- 多个 Extension 的 transform_context 按注册顺序链式包裹
- **后注册的更靠近模型**（最内层包裹）

### 4.3 Hook 链总结

| Hook 位置 | 注入方式 | 功能 |
|----------|---------|------|
| before_agent_start | Agent 构造 / Extension | 修改 system_prompt 或注入初始消息 |
| before_tool_call | Agent 构造 / Extension | 阻止工具、修改参数、注入 metadata |
| after_tool_call | Agent 构造 / Extension | 修改 ToolResult 的内容/详情/渲染 |
| transform_context | Agent 构造 / Extension | LLM 调用前转换消息列表 |

**设计决策**：Hook 链是框架唯一的扩展入口。不允许在 Loop 内部硬编码任何扩展逻辑。新增扩展功能必须复用 Extension 接口，禁止另立钩子 API。

### 4.4 双桥接模式：Retriever 与 Memory

框架有意将"检索"和"记忆"分开设计：

| 子系统 | 协议 | 桥接方式 |
|--------|------|---------|
| **Retriever** | 无状态 query → chunks | RetrieverTool（智能体 RAG，模型按需调用）或 AutoRetrievalExtension（经典 RAG，每 turn 自动注入） |
| **MemoryStore** | session 范围 remember/recall/forget | MemoryExtension + transform_context（持久化用户消息，召回为系统注释） |

**为什么分开？** 合并会迫使不同类型的后端（如 mem0 的事实提取 vs Pinecone 的向量搜索）采用别扭的统一 API。分开后每种后端可以选择最自然的桥接方式。

---

## 5. Provider 抽象

### 5.1 ModelProvider Protocol

```
ModelProvider（协议）
├── name: str
├── list_models() → [Model]
└── stream(model, messages, tools, system_prompt, thinking_level, ..., auth)
    → AsyncIterator[StreamEvent]

Model
├── provider: str           — 提供商标识
├── id: str                 — 模型 ID
├── context_window: int     — 上下文窗口大小
├── max_output_tokens: int  — 最大输出 token
├── supports_reasoning      — 是否支持推理模式
└── cost: ModelCost         — 单价（统计用）
```

**StreamEvent 联合类型**（Provider 中立的事件流）：

| 事件 | 含义 |
|------|------|
| text_delta | 文本增量 |
| thinking_delta | 思考过程增量 |
| tool_call_start | 工具调用开始（id + name） |
| tool_call_delta | 工具调用参数增量 |
| tool_call_end | 工具调用参数完成 |
| message_end | 消息结束 + token 用量统计 |
| error | 错误（含可重试/溢出标记） |

**设计决策**：
- **为什么不用 OpenAI SDK？** 直连 HTTP SSE 接口，避免 SDK 版本锁定。同一个 OpenAI 适配器可以服务所有 OpenAI 兼容端点（vLLM、Together、Minimax 等），只需替换 `base_url`
- **为什么 StreamEvent 是联合类型？** 不同厂商的 SSE 格式差异巨大，统一为中间事件流后，Loop 层不需要知道任何厂商细节

### 5.2 凭证解析三层

```
AuthSource
├── static(api_key, extra_headers?)     — 硬编码，适合开发
├── env(env_var, extra_headers?)        — 环境变量，适合部署
└── dynamic(callback)                   — 异步回调，适合 OAuth 刷新
```

**设计决策**：凭证解析从 Provider 内部提升到 Agent 层，作为构造必填参数。这避免了"凭证从哪里来"这个关注点散落在多个 Provider 实现中。

### 5.3 多 Provider 注册表

```
ModelRegistry
├── register_provider(provider, auth_source)   — 注册 Provider + 凭证源
├── find(provider_name, model_id) → Model?     — 查找模型
├── list_available() → [Model]                 — 列举所有可用模型
└── get_auth(model) → ProviderAuth             — 解析凭证
```

同一个框架实例可以同时注册多个 Provider（OpenAI + Anthropic + 自部署），运行时按模型选择切换。

### 5.4 思考等级（ThinkingLevel）

`off | minimal | low | medium | high | xhigh`

- 不支持 reasoning 的模型自动不下发 reasoning 字段（静默降级）
- 每个 Provider 自行映射：OpenAI → `reasoning_effort` 字符串，Anthropic → `thinking.budget_tokens` 数值表
- 用户面对的是统一的六级语义，不需要了解各厂商的具体参数

---

## 6. 会话与持久化

### 6.1 AgentSession 组合层

Agent 是纯运行时，AgentSession 是**组合层**，将多个子系统整合：

```
AgentSession
├── agent: Agent
├── store: SessionStore
├── compactor: Compactor?
├── extensions: [Extension]
└── session_id: str

生命周期：
├── start()      — 从 Store 加载历史 → 订阅事件 → 装配 ExtensionRunner
├── prompt()     — 代理到 Agent.prompt()
├── continue_()  — 代理到 Agent.continue_()
├── compact()    — 手动触发上下文压缩
├── abort()      — 代理到 Agent.abort()
└── dispose()    — 清理资源
```

**事件驱动的持久化**：
- 监听 `MessageEnd` → 写入 `MessageEntry`
- 监听 `ToolExecutionEnd` → 写入工具结果
- 监听 `AgentEnd` → 检查压缩阈值 → 必要时触发压缩并写入 `CompactionEntry`

**设计决策**：显式 `start()` 而非构造函数中自动启动。避免构造副作用与异步 IO 隐式发生。

### 6.2 SessionStore Protocol

```
SessionStore（协议）
├── create_session(session_id, header)
├── append_entry(session_id, entry: SessionEntry)
├── load_session(session_id) → SessionSnapshot
├── list_sessions(owner?, limit?) → [SessionMeta]
├── delete_session(session_id) → bool
└── close()

SessionEntry（判别联合）
├── MessageEntry             — 消息记录
├── CompactionEntry          — 压缩摘要（summary + first_kept_entry_id + tokens_before）
├── ModelChangeEntry         — 模型切换记录
├── ThinkingLevelChangeEntry — 思考等级变更记录
└── CustomEntry              — 扩展自定义记录
```

**内置实现**：
- `InMemoryStore`：测试/短期会话
- `JsonlStore`：每会话一个 `.jsonl` 文件（第一行 header，后续行为 entries）—— Scene 默认
- `SqliteStore`：单文件 SQLite（stdlib）；`SESSION_STORE=sqlite`，路径 `SESSION_SQLITE_PATH` 或 `{dir}/sessions.db`
- 工厂：`create_session_store()`

### 6.3 上下文压缩

```
Compactor（协议）
├── should_compact(messages, context_window) → bool
└── compact(messages, reason, instructions?, signal?) → CompactionResult
```

**双触发策略**：

| 触发方式 | 触发条件 | 行为 |
|---------|---------|------|
| **阈值预防** | AgentEnd 后 token 估算达到 context_window 的 80% | 自动压缩，不自动 continue |
| **溢出恢复** | Provider 返回上下文溢出错误 | 压缩后自动重试当前 turn |
| **手动触发** | 用户显式调用 compact() | 支持自定义压缩指令 |

**压缩算法**：保留最近 N 条消息（默认 4），对其余消息调用 LLM 生成摘要。摘要函数由消费者注入，可对接任意 LLM。

---

## 7. 资源与 Prompt 构建

### 7.1 ResourceLoader

统一的资源发现和加载器，支持五类资源：

| 资源类型 | 文件格式 | 用途 |
|---------|---------|------|
| Skills | `SKILL.md`（YAML frontmatter + Markdown body） | 注入 system prompt 的技能指令 |
| PromptTemplates | `*.md`（YAML frontmatter） | 可复用的 prompt 模板 |
| Themes | `*.json` | UI 主题配置 |
| ContextFiles | `AGENTS.md` / `CLAUDE.md` | 项目级上下文（从 cwd 向上查找到 .git 边界） |
| ExtensionSpecs | `*.py` | 扩展发现 |

**搜索路径优先级**：
```
显式路径 > 项目 .pi/ 目录 > 用户 ~/.pi/agent/ 目录 > 环境变量 AGENT_CORE_{TYPE}_PATH
```

**名称冲突处理**：先注册的获胜，冲突记录到 `ResourceDiagnostics`（warning/error/collision 收集器）。

### 7.2 SystemPromptBuilder

将 system prompt 拆为 7 个有序 section，按运行时输入动态拼装：

```
SystemPrompt = 有序拼接(
  1. Base         — 基础人设 prompt
  2. Tools        — 按名排序，附每个工具的 prompt_snippet
  3. Guidelines   — 基于工具集合的 predicate 规则（如"edit 前必须先 read"）
  4. Tool Guidelines — 全局工具输出指南 + 每个工具的 prompt_guidelines
  5. Context Files — 项目上下文文件
  6. Skills       — <available_skills> XML 块（过滤 disable_model_invocation 的技能）
  7. Meta         — 当前日期 + 工作目录
)
```

**设计决策**：system prompt 是动态构建的，不是静态字符串。工具集、技能列表、项目上下文都可能随会话变化，硬编码的 prompt 无法适应这种动态性。

### 7.3 Skill 自进化闭环

四阶段流水线，实现技能指令的自我优化：

```
1. Trace 收集
   SkillTraceCollector（作为 Extension）在 AgentStart/TurnEnd 时自动记录执行轨迹
   → 包含：用户查询、加载的规则、执行结果

2. 离线分析
   OfflineEvolutionAgent 批量分析 traces
   → 并行生成 PatchProposal（成功分析师 + 错误分析师）
   → LLM 驱动分析 + 启发式回退

3. 验证门控
   SkillValidationGate 对提案进行前后对比测试
   → 仅接受 score_delta ≥ 5% 的改进

4. 审计日志
   追加式 JSONL 记录所有 accept/reject 决策
```

---

## 8. 通信协议设计

### 8.1 SSE 事件映射

Scene 层将内部 AgentEvent 映射为前端友好的 SSE JSON：

| AgentEvent | SSE event 名 | SSE data 字段 |
|-----------|-------------|--------------|
| MessageUpdate(TextDelta) | `text_delta` | `{ text }` |
| MessageUpdate(ThinkingDelta) | `thinking_delta` | `{ text }` |
| MessageUpdate(ToolCallDelta) | `tool_call_delta` | `{ id, name, arguments_delta }` |
| ToolExecutionStart | `tool_start` | `{ id, name, args }` |
| ToolExecutionEnd | `tool_end` | `{ id, name, result, is_error }` |
| MessageEnd | `message_end` | `{ message, usage }` |
| HumanInputRequired | `human_input_required` | `{ tool_call_id, prompt, schema }` |
| AgentEnd | `done` | `{ messages }` |

**不透传的事件**：TurnStart/TurnEnd、MessageStart 等内部事件不暴露给前端，避免协议耦合。

### 8.2 Content Block 三阶段生命周期

每个内容块遵循 start → delta → done 的生命周期：

```
Text Block:    message_start → text_delta(×N) → message_end
Thinking Block: message_start → thinking_delta(×N) → message_end
Tool Call Block: tool_start → tool_call_delta(×N) → tool_end
```

**设计决策**：start/done 分离模式使得前端可以精确知道每个 block 的开始和结束，支持流式渲染和骨架屏。

### 8.3 HITL（Human In The Loop）

完整的 HITL 流程由三个组件构成：

```
RequiresHumanInput（异常）
  ↑ 工具内部抛出，携带 prompt + input_schema
  
HumanInputGate（门控）
  ├── require_input(tool_call_id, prompt, schema) → 挂起等待
  └── provide_input(tool_call_id, values) → 解除挂起

Agent.provide_human_input(tool_call_id, values)
  └── 外部入口，代理到 HumanInputGate
```

**流程**：
```
工具 execute() 中 raise RequiresHumanInput
  → Loop 捕获异常（不视为错误）
  → 发出 HumanInputRequired 事件
  → 持有 Future 等待
  → 外部调用 provide_human_input()
  → Future resolve
  → 工具内 require_input() 返回用户输入
  → 工具继续执行
```

**限制**：仅 sequential 工具执行模式支持 HITL。parallel 模式下无法确定哪个工具在等待输入。

---

## 9. 复刻指南

### 9.1 最小可复刻单元

实现一个可用的 Agent 框架，最少需要以下组件：

| 优先级 | 组件 | 核心职责 |
|--------|------|---------|
| P0 | Message 模型 | 定义 UserMessage / AssistantMessage / ToolResultMessage |
| P0 | AgentEvent 模型 | 至少需要 AgentStart/End、TurnStart/End、MessageStart/Update/End、ToolStart/End |
| P0 | Agent Loop | 纯异步生成器实现的 ReAct 循环 |
| P0 | ModelProvider 接口 | 统一流式输出接口 |
| P1 | Tool 接口 + Registry | 工具定义、注册、执行 |
| P1 | Agent 类 | 状态包装 + 事件分发 |
| P2 | SessionStore | 会话持久化 |
| P2 | Compactor | 上下文压缩 |
| P2 | Extension 接口 | 插件扩展点 |

### 9.2 关键设计决策及其替代方案

| 决策 | 本框架选择 | 替代方案 | 选择理由 |
|------|----------|---------|---------|
| Loop 实现 | 纯异步生成器 | 面向对象状态机 | 生成器天然支持流式输出，状态机需要手动管理 yield/await |
| 消息格式 | 判别联合 | 继承体系 | 序列化友好，模式匹配支持好 |
| 扩展机制 | Protocol + ExtensionRunner | 事件总线 / 中间件链 | 类型安全，错误隔离，调试简单 |
| Provider 抽象 | 统一 StreamEvent 流 | 各 Provider 返回原生格式 | Loop 层无需知道 Provider 细节 |
| 持久化时机 | 事件驱动（MessageEnd/AgentEnd） | 定时快照 | 不丢失任何消息，恢复精确 |
| 凭证管理 | AuthSource 三层抽象 | Provider 内部硬编码 | 关注点分离，支持 OAuth 刷新 |

### 9.3 不同语言实现适配建议

**Java/Kotlin**
- 异步生成器 → `Flow<AgentEvent>`（Kotlin Coroutines）或 `Flow.Publisher<AgentEvent>`（Java）
- 判别联合 → `sealed interface` + `record`
- Protocol → `interface`
- 值对象 → `record`（Java 16+）
- 并发控制 → `StructuredTaskScope`（Java 21+）替代 `asyncio.gather`

**Go**
- 异步生成器 → `chan AgentEvent` 或 `iter.Seq[AgentEvent]`（Go 1.23+）
- 判别联合 → `interface` + type switch
- Protocol → `interface`
- 值对象 → `struct`
- 并发 → `goroutine` + `errgroup`

**TypeScript**
- 异步生成器 → `AsyncGenerator<AgentEvent>`（原生支持）
- 判别联合 → `type` + `discriminated union`
- Protocol → `interface`
- 值对象 → 不可变对象（`readonly` 或 `Object.freeze`）

**Rust**
- 异步生成器 → `impl Stream<Item = AgentEvent>`（tokio-stream）
- 判别联合 → `enum`
- Protocol → `trait`
- 值对象 → `struct`（derive Clone）

### 9.4 复刻时应保留的设计约束

1. **Core 层零 IO** — 无论如何适配，核心循环不应直接依赖网络/文件/数据库
2. **事件驱动解耦** — Loop 产出事件，外部消费事件，两者不直接耦合
3. **值对象注入** — 所有可变依赖通过参数注入，Loop 本身不持有状态
4. **Protocol 优先** — 先定义接口，再提供实现，禁止硬编码具体实现
5. **错误隔离** — 扩展/工具的异常不中断主流程
6. **渐进式复杂度** — 最简场景不需要引入全部子系统

### 9.5 复刻时可以省略的部分

- **Skill 自进化**：高级功能，大多数场景不需要
- **Companion 系统**：产品特定功能（宠物/精灵），与框架无关
- **ResourceLoader**：如果资源管理方式不同，可以用更简单的方案替代
- **FileMutationQueue**：如果不涉及文件系统工具，不需要
- **SystemPromptBuilder**：如果 prompt 管理方式不同，可以简化

---

## 附录 A：架构全景图

```
┌──────────────────────────────────────────────────────────────────┐
│                        Scene 层                                   │
│  ┌──────┐  ┌──────────┐  ┌───────────┐  ┌───────┐  ┌────────┐  │
│  │ CLI  │  │ HTTP SSE │  │ WebSocket │  │ 飞书   │  │ 自定义  │  │
│  └──┬───┘  └────┬─────┘  └─────┬─────┘  └───┬───┘  └───┬────┘  │
│     └───────────┴──────────────┴─────────────┴──────────┘       │
│                              │                                    │
├──────────────────────────────┼────────────────────────────────────┤
│                        Session 层                                 │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  AgentSession                                           │     │
│  │  ┌─────────┐  ┌───────┐  ┌───────────┐  ┌──────────┐  │     │
│  │  │  Agent  │  │ Store │  │ Compactor │  │Extension │  │     │
│  │  │         │  │       │  │           │  │ Runner   │  │     │
│  │  └────┬────┘  └───────┘  └───────────┘  └────┬─────┘  │     │
│  │       │                                       │         │     │
│  │  ┌────▼───────────────────────────────────────▼──────┐  │     │
│  │  │  Agent Loop（纯异步生成器）                        │  │     │
│  │  │  ┌──────────┐  ┌───────────┐  ┌───────────────┐  │  │     │
│  │  │  │ Provider │  │ Tool      │  │ Transform     │  │  │     │
│  │  │  │ Stream   │  │ Execution │  │ Context       │  │  │     │
│  │  │  └──────────┘  └───────────┘  └───────────────┘  │  │     │
│  │  └──────────────────────────────────────────────────┘  │     │
│  └─────────────────────────────────────────────────────────┘     │
│                              │                                    │
├──────────────────────────────┼────────────────────────────────────┤
│                        基础设施层                                  │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐ │
│  │Providers │ │  Tools   │ │ Prompts│ │Resources │ │ Memory  │ │
│  │OpenAI    │ │Local/Bash│ │Builder │ │Loader    │ │Retriever│ │
│  │Anthropic │ │HTTP/MCP  │ │Guide   │ │Skills    │ │Knowledge│ │
│  │自定义    │ │自定义    │ │Snippets│ │Context   │ │自定义   │ │
│  └──────────┘ └──────────┘ └────────┘ └──────────┘ └─────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

## 附录 B：核心数据流

```
用户输入
  │
  ▼
Agent.prompt(text)
  │
  ├── 构造 UserMessage → 追加到 messages
  ├── 创建 AgentContext（messages 引用 + system_prompt + model + ...）
  ├── 创建 AgentLoopConfig（provider + tool_registry + hooks + ...）
  │
  ▼
agent_loop(new_messages, context, config, signal)
  │
  ├── yield AgentStart
  │
  ├── 【Reason】provider.stream() → StreamEvent 流
  │   ├── StreamTextDelta    → yield MessageUpdate(TextDelta)
  │   ├── StreamThinkingDelta → yield MessageUpdate(ThinkingDelta)
  │   ├── StreamToolCallStart/Delta/End → 累积 ToolCallContent
  │   └── StreamMessageEnd  → 构造完整 AssistantMessage → yield MessageEnd
  │
  ├── 【Act】execute_tools(tool_calls, registry, mode, hooks)
  │   ├── yield ToolExecutionStart
  │   ├── tool.execute(params, ctx) → ToolResult
  │   ├── yield ToolExecutionEnd
  │   └── 追加 ToolResultMessage → messages
  │
  ├── yield TurnEnd
  │
  ├── 循环判断 → 有 tool_results → 继续 / 无 → 终止
  │
  └── yield AgentEnd
  
事件流被多层消费：
  ├── Agent 内部 → 更新 AgentState
  ├── AgentSession → 持久化到 Store + 压缩检查
  ├── ExtensionRunner → 分发给所有 Extension
  └── 外部 Listener → SSE/CLI/WebSocket 渲染
```

## 附录 C：术语表

| 术语 | 含义 |
|------|------|
| Agent Loop | 核心 ReAct 循环，纯异步生成器 |
| AgentEvent | 事件判别联合，系统的神经信号 |
| AgentState | Agent 的完整状态快照 |
| AgentSession | 组合层，整合 Agent + Store + Compactor + Extensions |
| Compactor | 上下文压缩协议 |
| Content Block | 消息内容块（Text/Image/ToolCall） |
| Extension | 插件协议，在事件边界介入 Agent 行为 |
| HITL | Human In The Loop，人机交互中断机制 |
| Hook | 工具边界和上下文转换的拦截点 |
| ModelProvider | LLM 提供商协议，统一流式输出接口 |
| PendingMessageQueue | 待处理消息队列（steering / follow-up） |
| Protocol | 接口协议定义（Python typing.Protocol） |
| SessionStore | 会话持久化协议 |
| StreamEvent | Provider 层中立事件流 |
| ThinkingLevel | 思考深度等级（off → xhigh） |
| Tool | 工具协议，Agent 与外部世界交互的手段 |
| ToolRegistry | 工具注册表，管理工具生命周期 |
| transform_context | LLM 调用前的消息列表转换钩子 |
