# Agent 核心框架设计哲学

> 本文档抽象自 `agent-core` 参考实现，面向在其他语言/环境中复刻一个通用 Agent 运行时。
> 重点描述**设计理念与架构契约**，而非具体代码。

---

## 一、第一性原则

### 1. 库 ≠ 服务

框架只交付**抽象与运行时库**，不绑定任何服务形态。FastAPI、CLI、WebSocket、Notebook 等宿主由消费者自行实现。框架通过 `Protocol`（接口）注入存储、LLM、工具来源，宿主决定具体实现。

> 复刻要点：核心库不应 import 任何 Web 框架或数据库驱动。

### 2. 异步优先

所有公共 API 是协程（coroutine）或异步生成器（async generator）。核心循环产出事件流，消费者订阅事件。同步监听器也被支持——框架内部统一处理。

### 3. 分层单向依赖

```
core  ←  session  ←  extensions  ←  resources / prompts
  ↑
providers / tools（通过 Protocol 注入 core）
```

- `core` 层**零 IO 依赖**（仅 stdlib + 数据模型库）。
- 每一层只依赖下层，绝不反向。
- `scene/`（示例宿主）在框架之外，不属于库本体。

### 4. 接口在框架内，实现在适配器

存储、LLM 提供商、工具来源——先定义 `Protocol`（接口契约），再附内置实现。消费者可替换任意一层。

### 5. 显式优于隐式

- 状态用数据模型（Pydantic/等价物）表达，赋值时校验。
- 事件用**判别联合**（discriminated union，带 `type` 字段的联合类型）分发，消费者按 `type` 模式匹配。
- 所有可变依赖收敛为值对象参数传入循环，循环本身不持有可变状态。

### 6. YAGNI

只做必要功能。沙箱、会话分支、运营能力全部留作扩展点，不内置。

---

## 二、核心循环：Agent Loop

Agent 的本质是一个**多轮异步生成器**，每轮执行：

```
用户消息 → [上下文转换] → 流式 LLM → 累积 AssistantMessage
                                    ↓ 有工具调用？
                              执行工具 → 结果写回消息列表
                                    ↓
                         无工具调用且无待处理消息 → 结束
```

### 2.1 循环的终止条件

- LLM 不再产生工具调用（正常结束）
- 达到 `max_turns` 上限
- 外部 `abort` 信号触发
- LLM 返回不可重试的错误

### 2.2 重试与溢出处理

- **可重试错误**：指数退避重试，首次流式（保证响应性），重试时缓冲输出。
- **上下文溢出**：触发压缩回调，压缩后重新构建消息再重试。

### 2.3 消息注入（Steering & Follow-up）

两个队列，生命周期不同：
- **Steering**（转向）：运行中注入（如用户中断），当前轮结束后 drain，参与下一轮。
- **Follow-up**（跟进）：本次运行结束前 drain；若有内容则追加一轮（支持 agent 自主追问后的连续任务）。

两种 drain 模式：`one-at-a-time`（默认）、`all`。

---

## 三、事件模型

事件是框架与外部世界的唯一通信契约。所有事件携带 `type` 字段，构成判别联合：

| 层级 | 事件 | 含义 |
|---|---|---|
| 全局 | `agent_start` / `agent_end` | 一次 `prompt()` 的起终点 |
| 轮次 | `turn_start` / `turn_end` | 单轮（一次 LLM + 工具执行）边界 |
| 消息 | `message_start` / `message_update` / `message_end` | 消息生命周期；`update` 携带流式 delta |
| 工具 | `tool_execution_start/update/end` | 工具调用生命周期 |
| HITL | `human_input_required` | 需要人工介入 |
| Skill | `skill_start` / `skill_end` | Skill 生命周期 |

流式 delta 分三类：`text_delta`（正文）、`thinking_delta`（推理链）、`tool_call_delta`（工具调用参数）。

> 复刻要点：事件模型是 SSE / WebSocket / 前端渲染的唯一数据源，设计时优先保证事件的完整性与顺序性。

---

## 四、消息与内容模型

### 4.1 内容块（Content Block）

消息由内容块列表组成，按 `type` 判别：

- `text`：文本
- `image`：图片（base64 + mime_type）
- `tool_call`：工具调用（id + name + arguments）
- `tool_result`：工具返回结果

### 4.2 消息角色

- `user`：用户消息（text + image）
- `assistant`：助手消息（text + tool_call），携带 usage、stop_reason
- `tool_result`：工具执行结果
- `custom`：自定义消息（扩展用）

### 4.3 AgentState

运行时状态，包含：`system_prompt`、`model`、`thinking_level`、`tools`（轻量定义列表）、`messages`。由循环直接 mutate（append）。

---

## 五、工具协议（Tool Protocol）

工具是框架扩展能力的核心入口。

### 5.1 契约

```
ToolDefinition（轻量，送 LLM）：
  name, description, parameters(JSON Schema),
  prompt_snippet（可选，送入系统提示词）,
  prompt_guidelines（可选，生成使用指南）

Tool（执行体，Protocol）：
  definition: ToolDefinition
  execute(tool_call_id, params, ctx: ToolContext) → ToolResult

ToolResult：
  content（送 LLM 的内容块列表）,
  details（不送 LLM，供 UI/扩展）,
  display（渲染层 hint）
```

### 5.2 ToolContext

执行上下文，包含：`signal`（取消信号）、`on_update`（长耗时工具的进度回调）、`metadata`（session_id、human_input_gate 等）、`mutation_queue`（文件互斥锁）。

### 5.3 执行模式

- **parallel**（默认）：同一 turn 内多个工具调用并发执行（`asyncio.gather`）。
- **sequential**：逐个执行，中间 emit `ToolExecutionUpdate` 事件（适合需要观察中间结果的场景）。

### 5.4 文件互斥

`FileMutationQueue`：按文件路径维护 `Lock`，避免并行工具调用对同一文件的写冲突。

### 5.5 工具拦截钩子

- `before_tool_call`：可返回 `{block: True, reason}` 阻断调用。
- `after_tool_call`：可改写结果的 `content / details / display`。

---

## 六、人机对话（HITL）

工具执行过程中可暂停并等待人工输入：

1. 工具抛出 `RequiresHumanInput(prompt, input_schema)` 异常。
2. 框架捕获后 emit `HumanInputRequired` 事件，挂起该工具调用。
3. 外部调用 `provide_human_input(tool_call_id, values)` 解决 Future。
4. 工具内 `require_input()` 返回，继续执行。

> 复刻要点：HITL 不是错误——框架需将 `RequiresHumanInput` 与普通异常区分处理。

---

## 七、LLM 提供商抽象

### 7.1 Protocol

```
ModelProvider：
  name: str
  list_models() → list[Model]
  stream(model, messages, tools, *, system_prompt, thinking_level, ...)
    → AsyncIterator[StreamEvent]
```

`StreamEvent` 是提供商中立的判别联合：`text_delta`、`thinking_delta`、`tool_call_start/delta/end`、`message_end`、`error`。

### 7.2 凭证解析（AuthSource）

三种来源：`static`（直接传入）、`env`（环境变量）、`dynamic`（回调，适合 OAuth 刷新）。在循环中**即时解析**，不缓存。

### 7.3 思考等级（ThinkingLevel）

`off | minimal | low | medium | high | xhigh`。不支持 reasoning 的模型自动不下发 reasoning 字段；支持的模型按提供商映射（OpenAI → reasoning_effort；Anthropic → thinking.budget_tokens）。

### 7.4 消息转换

框架维护统一的消息模型，通过 `convert_to_llm` 回调转换为提供商原生格式。工具结果默认截断到 4000 字符，防止巨型 payload 撑爆上下文。

---

## 八、会话持久化（Session）

### 8.1 分层

- `Agent`：纯运行时，无持久化概念。
- `AgentSession`：组合层，持有 `Agent` + `SessionStore` + `Compactor` + `Extensions`。

### 8.2 SessionStore Protocol

```
create_session(session_id, header)
append_entry(session_id, entry)
load_session(session_id) → SessionSnapshot
list_sessions(owner?, limit?)
close()
```

### 8.3 SessionEntry 判别联合

- `MessageEntry`：消息持久化
- `CompactionEntry`：压缩记录（摘要 + 保留边界）
- `ModelChangeEntry` / `ThinkingLevelChangeEntry`：元数据变更
- `CustomEntry`：扩展自定义

> 复刻要点：Entry 是判别联合而非单一表结构——每种 entry 携带不同的字段集合。

### 8.4 生命周期

`AgentSession.start()` 显式创建 session header、订阅 agent 事件、装配扩展。避免构造副作用与异步 IO 隐式发生。

---

## 九、上下文压缩（Compaction）

当消息列表接近模型的上下文窗口时，触发压缩：

```
Compactor Protocol：
  should_compact(messages, context_window) → bool
  compact(messages, *, reason, instructions, signal) → CompactionResult
```

触发场景：
- `manual`：手动调用
- `threshold`：达到 token 阈值（不自动 continue）
- `overflow`：上下文溢出（需消费者在外层捕获并显式处理）

`LLMSummaryCompactor` 将 token 估算与摘要生成解耦——`summarize_fn` 由消费者提供，可对接任意 LLM。

---

## 十、扩展体系（Extensions）

### 10.1 Extension Protocol

```
Extension：
  name: str
  on_event(ctx, evt)                    # 事件监听
  on_before_tool_call(ctx, call)        # → {block, reason} | None
  on_after_tool_call(ctx, call, result) # → {result} | None
```

`ExtensionRunner` 按注册顺序 dispatch，捕获异常不中断主流程。

### 10.2 加载方式

- 显式 spec（dotted path，`importlib` 扫描带 `name` 属性的类）
- Entry points（`agent_core.extensions` 组，setuptools 插件机制）

### 10.3 Transform Context 钩子

扩展可通过 `transform_context(llm_messages, signal)` 在每轮 LLM 调用前修改消息列表（用于 RAG 注入、记忆召回等）。多个扩展链式包裹，**后注册的更靠近模型**。

---

## 十一、资源体系（Resources）

### 11.1 搜索路径顺序

显式路径 → `<cwd>/.pi/<type>` → `~/.pi/agent/<type>` → 环境变量（冒号分隔）

### 11.2 Skills

- 每个 skill 是一个目录，含 `SKILL.md`（YAML frontmatter：name、description、disable_model_invocation）。
- 名称冲突记录到诊断报告，不静默覆盖。
- Skill 可标记 `disable_model_invocation`（不送入模型上下文，仅作 UI 展示）。

### 11.3 Context Files

从 `cwd` 沿目录树向上，在遇到 `.git` 前查找 `AGENTS.md` / `CLAUDE.md`，越近的越靠前。

### 11.4 系统提示词构建

`SystemPromptBuilder` 将 system prompt 拆为有序 sections，按运行时动态拼装：

```
base → tools（按名排序 + prompt_snippet）→ 通用 guidelines
→ 工具自带 guidelines → 项目 context files → skills（XML 块）→ meta（日期 + CWD）
```

---

## 十二、复刻检查清单

复刻一个最小可用的 Agent 框架，至少需要实现以下抽象：

| 层级 | 必须实现 | 可延后 |
|---|---|---|
| **核心** | Agent Loop（async generator）、事件判别联合、消息/内容模型、AgentState | 思考等级、HITL |
| **工具** | Tool Protocol、ToolRegistry、parallel 执行 | sequential 模式、文件互斥、长耗时工具 |
| **提供商** | ModelProvider Protocol、1 个提供商实现、StreamEvent 联合 | 多提供商、凭证 dynamic 解析 |
| **会话** | SessionStore Protocol、1 个实现（内存/文件） | MongoDB/Redis 适配器 |
| **压缩** | Compactor Protocol、阈值策略 | overflow 自动重试 |
| **扩展** | Extension Protocol、事件 dispatch | entry point 加载 |
| **资源** | Skills 发现与解析、Context Files 查找 | Themes、Prompts 模板 |
| **提示词** | SystemPromptBuilder（sections 拼装） | 动态 guidelines 生成 |

---

## 十三、关键设计决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 库 vs 服务 | 库 | 消费者自行决定宿主形态 |
| 同步 vs 异步 | 全异步 | 流式 LLM + 并发工具调用天然异步 |
| 状态管理 | Pydantic 模型 + 直接 mutate | 校验 + 性能兼顾 |
| 事件分发 | 判别联合（type 字段） | 类型安全、模式匹配友好 |
| 工具执行 | parallel 默认 | 多工具调用无依赖时并发更快 |
| 凭证解析 | 即时解析（非构造时） | 支持动态/OAuth 刷新场景 |
| 消息转换 | 回调注入 | 框架不绑定任何提供商的消息格式 |
| 压缩触发 | 阈值触发，不自动 continue | 避免压缩后无限循环；消费者决定何时继续 |
| 顶层导出 | 仅暴露 `__version__` | 显式子模块导入，避免循环依赖 |
| 扩展钩子 | 仅 on_event + before/after tool | 收敛钩子面，其余通过 on_event 实现 |
