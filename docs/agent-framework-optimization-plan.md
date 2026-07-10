# Agent 框架 Thin Core / Thick Harness 优化方案

## 现状诊断

### pi-mono-harness 三层架构（参考标准）

| 层级 | 文件 | 行数 | 职责 |
|------|------|------|------|
| **Core Loop** | `agent-loop.ts` | 743 | 纯函数式无状态循环，只通过 `emit` 发射事件 |
| **Core Agent** | `agent.ts` | 558 | 有状态封装，管理 transcript/队列/生命周期 |
| **Harness** | `agent-harness.ts` | 1065 | Session 持久化 + Compaction + Skills + Hook 系统 + Stream 管理 |

### 当前 agent_core 问题

| 问题 | 当前状态 | 目标状态 | 关键文件 |
|------|----------|----------|----------|
| **Core 过载** | `AgentLoopConfig` 有 21 个字段，含 `mutation_queue`/`human_input_gate`/`compact_callback` 等 harness 关注点 | Core 只保留 ~12 个字段 | `core/context.py` |
| **无 Harness 层** | `AgentSession` 混合了 Agent + Store + Compactor + Extensions 的 ad-hoc 组合 | 引入 `AgentHarness` 作为统一编排层 | `session/session.py` |
| **Hook 类型不安全** | 所有 hook 签名使用 `Any`，返回 `dict[str, Any]` | Typed hook 系统，每种 hook 有明确输入/输出 | `core/agent.py` L92-102, L358-445 |
| **无 `prepareNextTurn`** | Turn 间不能动态切换 model/context | 支持 turn 间上下文重建 | `core/loop.py` |
| **Compaction 原始** | 仅"保留最近 N 条"，94 行实现 | Token-aware + cut-point 分析 + 文件操作追踪 | `compaction/compactor.py` |
| **Session 扁平** | 5 种 entry 类型，无树结构，无缓存 | 树结构 + 分支导航 + 内存缓存 | `session/store.py` |
| **大量 `Any` 类型** | hook/event/tool 签名均为 `Any` | Protocol/TypedDict 明确类型 | 多处 |

---

## Task 1: Core 瘦身 — 拆分 `AgentLoopConfig`

**目标**: 将 `AgentLoopConfig` 中不属于 core 的关注点移出

**文件**: `agent_core/core/context.py`

**变更**:
- 从 `AgentLoopConfig` 中提取 harness 级字段为 `HarnessLoopExtensions`（可选 dataclass）:
  - `mutation_queue` → 移到 Harness
  - `human_input_gate` → 移到 Harness（通过 hook 注入）
  - `compact_callback` → 移到 Harness
  - `tool_result_max_chars` → 移到 Harness
- 新增 core 级回调:
  - `prepare_next_turn: Callable[[], Awaitable[PrepareNextTurnResult]] | None`
  - `should_stop_after_turn: Callable[[], Awaitable[bool]] | None`
- `AgentLoopConfig` 保留约 12 个 core 字段: `model`, `stream_fn`, `convert_to_llm`, `auth_resolver`, `transform_context`, `thinking_level`, `tool_execution`, `tool_registry`, `before_tool_call`, `after_tool_call`, `tool_timeout`, `max_turns`, `max_retries` 等

**依赖**: 无  
**风险**: 低 — 新增 dataclass 不影响现有代码

---

## Task 2: Core 瘦身 — Agent 类解耦

**目标**: 从 `Agent` 类中移除对 `ModelProvider`/`AuthSource`/`FileMutationQueue`/`HumanInputGate` 的直接依赖

**文件**: `agent_core/core/agent.py`

**变更**:
- `Agent.__init__` 不再直接接受 `provider` 和 `auth_source`，改为接受 `stream_fn` 和 `auth_resolver`
- 移除 `self._human_input_gate = HumanInputGate()` — 移到 Harness 层
- 移除 `FileMutationQueue()` 创建 — 移到 Harness 层
- 将 `_create_loop_config()` 中 harness 级配置移除
- 保留 `Agent` 作为"有状态循环封装器"（对应 pi-mono `agent.ts`），只管理 transcript/队列/生命周期/事件分发
- `setup_mcp_tools()` 移到 Harness

**依赖**: Task 1  
**风险**: 中 — 需要同时更新 `AgentSession` 的 Agent 创建方式

---

## Task 3: Hook 类型安全化

**目标**: 用明确的 Protocol/dataclass 替代 `Any` 类型的 hook 签名

**文件**: 
- `agent_core/core/hook_types.py`（新建）
- `agent_core/core/agent.py`（修改）

**变更**:

新建 `hook_types.py`:
```python
@dataclass
class BeforeToolCallResult:
    block: bool = False
    reason: str | None = None
    inject_metadata: dict[str, Any] | None = None
    mutated_args: dict[str, Any] | None = None

@dataclass
class AfterToolCallResult:
    content: list | None = None
    details: Any | None = None
    is_error: bool | None = None
    terminate: bool | None = None

@dataclass
class BeforeAgentStartResult:
    system_prompt: str | None = None
    messages: list[AgentMessage] | None = None

@dataclass  
class TransformContextResult:
    messages: list[Any] | None = None
```

修改 `agent.py`:
- 将 hook 链中的 `dict[str, Any]` 替换为上述 dataclass
- `_chain_before_hooks()` → 返回 `BeforeToolCallResult`
- `_chain_after_hooks()` → 返回 `AfterToolCallResult`
- `_chain_before_agent_start_hooks()` → 返回 `BeforeAgentStartResult`

**依赖**: 无  
**风险**: 低 — 内部实现变更

---

## Task 4: 提取 Hook Chain 为独立模块

**目标**: 将 `Agent` 类中 ~90 行的 hook chaining 逻辑提取为可独立测试的 `HookChain` 类

**文件**:
- `agent_core/core/hook_chain.py`（新建）
- `agent_core/core/agent.py`（修改）

**变更**:
- 新建 `HookChain` 类，封装 `_chain_before_hooks`、`_chain_after_hooks`、`_chain_transform_hooks`、`_chain_before_agent_start_hooks` 逻辑
- `Agent` 类内部使用 `HookChain` 实例替代手写 chaining 函数
- `HookChain` 支持 `register(hook_type, handler)` 和 `unregister(hook_type, handler)` 统一接口

**依赖**: Task 3  
**风险**: 低 — 纯内部重构

---

## Task 5: Loop 增强 — `prepareNextTurn` 和 `shouldStopAfterTurn`

**目标**: 支持 turn 间上下文重建和动态停止

**文件**: `agent_core/core/loop.py`

**变更**:
- 在 `TurnEnd` yield 之后、下一个 `while True` 迭代之前:
  1. 检查 `config.should_stop_after_turn`，如果返回 `True` 则 `break`
  2. 调用 `config.prepare_next_turn`，获取新的 `AgentContext`/`model`/`thinking_level`
  3. 用返回的新 context 替换当前 `context.messages`、`context.system_prompt`、`context.tools`
- 对应 pi-mono `agent-loop.ts` L226-253 的模式

**依赖**: Task 1  
**风险**: 中 — 修改 loop 核心路径，但新回调为可选（None 时行为不变）

---

## Task 6: 构建 `AgentHarness` 编排层

**目标**: 创建 Harness 层作为 Agent + Session + Compaction + Skills + Hooks 的统一编排入口

**文件**:
- `agent_core/harness/__init__.py`（新建）
- `agent_core/harness/agent_harness.py`（新建，核心 ~600 行）

**设计**: 参照 pi-mono `agent-harness.ts` 的 Python 等效实现

```python
class AgentHarness:
    """Thick harness layer: orchestrates Agent + Session + Compaction + Skills + Hooks."""
    
    def __init__(self, options: AgentHarnessOptions): ...
    
    # Lifecycle
    async def prompt(self, text: str, **opts) -> AssistantMessage: ...
    async def continue_(self) -> AssistantMessage: ...
    async def compact(self, instructions: str | None = None) -> CompactionResult: ...
    async def abort(self) -> AbortResult: ...
    async def wait_for_idle(self) -> None: ...
    
    # Runtime mutation
    async def set_model(self, model: Model) -> None: ...
    async def set_thinking_level(self, level: str) -> None: ...
    async def set_tools(self, tools: list, active_names: list | None = None) -> None: ...
    async def set_active_tools(self, names: list[str]) -> None: ...
    
    # Hooks
    def on(self, event_type: str, handler: Callable) -> Callable: ...
    def subscribe(self, listener: Callable) -> Callable: ...
    
    # Internal
    async def _create_turn_state(self) -> TurnState: ...
    async def _flush_pending_session_writes(self) -> None: ...
    async def _handle_agent_event(self, event: AgentEvent) -> None: ...
```

**关键模式（从 pi-mono 移植）**:
- **Pending Session Writes**: 运行期间缓冲 session 写入，在 `TurnEnd` 边界 flush（对应 `agent-harness.ts` L484-508）
- **Typed Hook 分发**: `on(event_type, handler)` + `subscribe(listener)` 双层事件系统
- **`prepareNextTurn`**: 在 turn 间 flush session + 重建 context snapshot（对应 L457-466）
- **Phase 状态机**: `idle` → `turn` / `compaction` → `idle`

**依赖**: Task 1, 2, 3, 5  
**风险**: 高 — 新模块，需要与多个现有模块交互

---

## Task 7: AgentSession 迁移为 Harness 薄包装

**目标**: 将 `AgentSession` 逐步迁移为 `AgentHarness` 的向后兼容包装

**文件**: `agent_core/session/session.py`

**变更**:
- `AgentSession.__init__` 内部创建 `AgentHarness` 实例
- `prompt()`、`continue_()`、`compact()`、`abort()` 代理到 `AgentHarness`
- 保留现有公共 API 签名不变
- `_on_overflow_compact` 逻辑移到 `AgentHarness`
- `_maybe_compact` 逻辑移到 `AgentHarness`

**依赖**: Task 6  
**风险**: 中 — 需要保持所有现有调用者（`scene/http_sse/`等）不感知变化

---

## Task 8: Compaction 升级为 Token-Aware

**目标**: 从"保留最近 N 条"升级为 token 感知的智能压缩

**文件**:
- `agent_core/compaction/compactor.py`（重写核心逻辑）
- `agent_core/compaction/strategies.py`（增强 token 估算）
- `agent_core/compaction/cut_points.py`（新建）

**变更**:

新增 `CompactionSettings`:
```python
@dataclass
class CompactionSettings:
    enabled: bool = True
    reserve_tokens: int = 16384      # 预留 token 数
    keep_recent_tokens: int = 20000  # 至少保留的最近 token 数
```

新建 `cut_points.py`:
- `find_cut_point(messages, token_budget)` — 基于 token 预算找到最佳分割点（不切断 turn 中间）
- `find_valid_cut_points(messages)` — 识别有效切割位置（user/assistant/tool_result 消息边界）
- `extract_file_operations(messages)` — 从 tool calls 中提取 read/written/edited 文件列表

增强 `LLMSummaryCompactor`:
- `should_compact()` 使用 provider Usage 数据（如有）或改进的 token 估算
- `compact()` 使用 `find_cut_point()` 替代 `messages[-keep_recent:]`
- 支持迭代式摘要（将上一次 summary 传入新 summary prompt）
- 生成 `CompactionPreparation` 包含文件操作追踪

增强 `strategies.py`:
- `estimate_tokens()` 改用 UTF-8 byte length / 4（更精确）
- `estimate_context_tokens()` 包含 system prompt + tools 定义的 token

**依赖**: 无（可独立进行）  
**风险**: 中 — 修改压缩逻辑，但有 `CompactionSettings.enabled` 开关

---

## Task 9: 输出截断增强 — Dual-Limit UTF-8-Aware

**目标**: 从简单字符截断升级为行数+字节双限制、UTF-8 感知的截断

**文件**: `agent_core/tools/truncate.py`

**变更**:
- 新增 `TruncationResult` dataclass: `content`, `truncated`, `truncated_by`, `total_lines`, `total_bytes`
- 新增 `DEFAULT_MAX_LINES = 2000`, `DEFAULT_MAX_BYTES = 50 * 1024`
- 实现 `truncate_head()` — 保留头部（文件读取场景）
- 实现 `truncate_tail()` — 保留尾部（shell 输出场景）
- UTF-8 byte length 感知: `utf8_byte_length(s)` 
- 保留旧 `truncate_tail(text, max_chars)` 签名作为向后兼容包装

**依赖**: 无  
**风险**: 低 — 新增函数，旧函数保持不变

---

## Task 10: Tool Pipeline 标准化

**目标**: 将 tool 执行正式化为 prepare/execute/finalize 三阶段

**文件**:
- `agent_core/core/tool_runner.py`
- `agent_core/tools/base.py`

**变更**:
- `ToolDefinition` 添加 `execution_mode: Literal["sequential", "parallel"] | None = None`
- 将 `_run_single_tool` 拆分为:
  1. `prepare_tool_call()` — 验证参数，运行 before hook，返回 `PreparedToolCall | BlockResult`
  2. `execute_prepared()` — 执行工具，捕获错误
  3. `finalize_executed()` — 运行 after hook，允许结果覆盖
- 在 batch 级别: 如果任何 tool 有 `execution_mode="sequential"`，整个 batch 强制串行
- 支持 `ToolResult.terminate` 标志提前终止 batch

**依赖**: Task 3  
**风险**: 低-中 — tool_runner 内部重构

---

## Task 11: Session Store 增强

**目标**: 添加内存缓存和树结构支持

**文件**:
- `agent_core/session/store.py`（扩展 entry 类型 + Protocol）
- `agent_core/session/jsonl_store.py`（添加缓存）

**变更**:

`store.py` 新增:
- `BranchSummaryEntry` — 分支摘要
- `LabelEntry` — 标签
- `ActiveToolsChangeEntry` — 工具变更
- `CustomMessageEntry` — 自定义消息
- `SessionInfoEntry` — session 信息
- 所有 entry 添加 `parent_id` 字段
- `SessionStore` Protocol 添加: `get_entry()`, `get_path_to_root()`, `get_leaf_id()`, `set_leaf_id()`

`jsonl_store.py` 新增:
- `_by_id: dict[str, SessionEntry]` — O(1) 查找缓存
- `_labels: dict[str, str]` — 标签缓存
- `load_session()` 时构建缓存
- `append_entry()` 时增量更新缓存

**依赖**: 无  
**风险**: 中 — Protocol 变更需要所有实现者适配

---

## Task 12: 迁移上层调用者

**目标**: 将 `scene/` 和 `demo/` 从直接使用 Agent/AgentSession 迁移到 AgentHarness

**文件**: `scene/http_sse/server.py`, `scene/http_sse/manager.py`, `demo/` 相关文件

**变更**:
- `ChatAssistant.create()` 从组装 Agent + AgentSession 改为创建 AgentHarness
- 将 provider/auth/compaction/session 的组装统一收口到 scene 层
- 利用 AgentHarness 的 typed hook 替代直接操作 agent 内部状态

**依赖**: Task 7  
**风险**: 高 — 影响所有在线场景，需要充分测试

---

## 依赖关系总览

```
Task 1 (Config拆分) ──→ Task 2 (Agent解耦)
                      ──→ Task 5 (Loop增强)

Task 3 (Hook类型)  ──→ Task 4 (HookChain提取)
                    ──→ Task 10 (Tool Pipeline)

Task 1+2+3+5 ──→ Task 6 (AgentHarness构建) ──→ Task 7 (Session迁移) ──→ Task 12 (上层迁移)

Task 8 (Compaction) ── 独立
Task 9 (Truncation) ── 独立  
Task 11 (Session Store) ── 独立
```

**推荐实施顺序**: Task 9 → Task 8 → Task 3 → Task 1 → Task 5 → Task 4 → Task 10 → Task 11 → Task 2 → Task 6 → Task 7 → Task 12

**可并行**: Task 8/9/11 可与 Task 1-5 并行开发

---

## 风险缓解策略

| 风险 | 级别 | 缓解 |
|------|------|------|
| 破坏性 API 变更 | 高 | `Agent` 原有 API 保留为 deprecated 兼容层；`AgentSession` 变为 `AgentHarness` 的 thin wrapper |
| Hook 过度设计 | 中 | 先只引入 4 种核心 hook（`tool_call`, `tool_result`, `context`, `before_agent_start`），其余按需添加 |
| Session 树不兼容 | 中 | `JsonlStore` 向后兼容读取旧格式，新 entry 类型通过 `type` 字段区分 |
| 循环依赖 | 中 | `HumanInputGate` 改为 hook 模式注入，`tool_runner` 只依赖 core hook 接口 |
| 性能回归 | 低 | Hook 为 None 时零开销；事件类使用 `__slots__` |
| 回归测试 | 高 | 每个 Task 完成后运行现有测试；Task 6/7 完成后做集成测试 |

---

## 被否决的替代方案

| 方案 | 原因 |
|------|------|
| **引入 `Result[T, E]` 泛型** (Plan C Step 3) | Python 不原生支持 `Result` 模式，用 `try/except` + typed exceptions 更符合 Python 惯例 |
| **一步到位重写 `Agent` 类** | 风险太高，破坏所有调用者；采用增量迁移策略 |
| **先迁移 scene/ 再改 core** | 依赖方向错误，应该先改底层 core 再迁移上层 |
| **引入 Proxy Stream** (Plan A Step 18) | 当前无明确需求，推迟到需要时再加 |
| **Shell Output Spill-to-File** (Plan B Step 2) | 当前 shell 输出通过 `subprocess` 直接捕获，spillover 模式复杂度高，优先级低 |

---

## Critical Files

1. **`agent_core/core/context.py`** (65行) — `AgentLoopConfig` 是 core/harness 的边界契约，拆分它是最关键的架构杠杆点
2. **`agent_core/core/agent.py`** (486行) — Agent 类瘦身核心目标，需移除 provider/auth/mutation_queue/human_input_gate 直接依赖
3. **`agent_core/core/loop.py`** (286行) — agent loop 主循环，需添加 `prepareNextTurn`/`shouldStopAfterTurn` 支持
4. **`agent_core/session/session.py`** (292行) — 当前 ad-hoc 编排层，需迁移为 AgentHarness 薄包装
5. **`pi-mono-harness/harness/agent-harness.ts`** (1065行) — 参考蓝图，Python AgentHarness 的设计标准

---

## 附录: Harness 子模块详细对比（待确认）

以下是 pi-mono-harness 中各子模块与 agent_core 的逐项对比，用于确认 Skill/Tool/Messages/SystemPrompt/ExecutionEnv 等 harness 模块的优化范围。

### A. Skill 系统

| 维度 | pi-mono `harness/skills.ts` (376行) | agent_core `skills/__init__.py` (250行) | 差距 |
|------|------|------|------|
| **Skill 数据模型** | `{ name, description, content, filePath, disableModelInvocation }` — 包含完整 `content` 字段 | `Skill(name, description, file_path, base_dir, disable_model_invocation)` — **缺少 `content` 字段** | 当前 Skill 不存储文件内容，调用时需重新读取 |
| **目录遍历** | 递归遍历 + SKILL.md 优先 + `.gitignore`/`.ignore`/`.fdignore` 排除 | 递归遍历 + SKILL.md 优先 + 简单跳过 `.` 和 `node_modules` | **缺少 ignore file 支持** |
| **Source-tagged Skills** | `loadSourcedSkills()` 支持多源 skills 合并 + source 追踪 | `load_skills()` 用 dict 去重，碰撞时 warning | 功能基本等价 |
| **Frontmatter 解析** | 使用 `yaml` 库完整解析 YAML | 手写简单 key:value 解析器 | **不支持多行 description、数组等复杂 YAML** |
| **Skill 内容加载** | `loadSkillFromFile()` 读取文件 → 解析 frontmatter → 提取 body 作为 `content` | `load_skill_from_file()` 只提取 frontmatter，不存储 body | **无法格式化 skill invocation** |
| **Skill Invocation 格式化** | `formatSkillInvocation(skill, additionalInstructions)` → XML 格式 | **不存在** | **完全缺失**，无法通过 harness 触发 skill |
| **Sourced Skills** | `loadSourcedSkills<TSource>()` 泛型 + 可自定义映射 | 无 | 缺失 |
| **Diagnostics** | `SkillDiagnostic { type, code, message, path }` — typed code | `dict[str, Any]` — 无类型约束 | 类型安全性差 |

**建议**: 
1. Skill dataclass 添加 `content: str` 字段
2. 添加 `format_skill_invocation()` 函数
3. 用 `python-frontmatter` 或 `pyyaml` 替换手写解析器
4. 添加 `.gitignore` 支持（`pathspec` 库）

---

### B. Prompt Template 系统

| 维度 | pi-mono `harness/prompt-templates.ts` (268行) | agent_core | 差距 |
|------|------|------|------|
| **Prompt Template** | `PromptTemplate { name, description, content }` | **不存在** | **完全缺失** |
| **加载** | `loadPromptTemplates()` — 从目录/文件加载 `.md` 模板 | 无 | 缺失 |
| **参数替换** | `substituteArgs(content, args)` — 支持 `$1`, `$@`, `$ARGUMENTS`, `${@:N}` | 无 | 缺失 |
| **命令参数解析** | `parseCommandArgs(argsString)` — shell 风格引号解析 | 无 | 缺失 |
| **Sourced Templates** | `loadSourcedPromptTemplates<TSource>()` | 无 | 缺失 |
| **Harness 集成** | `AgentHarness.promptFromTemplate(name, args)` | 无 | 缺失 |

**建议**: 新建 `agent_core/harness/prompt_templates.py`，实现 PromptTemplate 加载 + 参数替换

---

### C. Messages（自定义消息类型 + LLM 转换）

| 维度 | pi-mono `harness/messages.ts` (165行) | agent_core `core/messages.py` (87行) | 差距 |
|------|------|------|------|
| **UserMessage** | 标准 user message | `UserMessage(role, content, timestamp)` | 等价 |
| **AssistantMessage** | 标准 assistant message | `AssistantMessage(role, content, usage, ...)` | 等价 |
| **ToolResultMessage** | 标准 tool result | `ToolResultMessage(role, tool_call_id, ...)` | 等价 |
| **BashExecutionMessage** | `{ role: "bashExecution", command, output, exitCode, cancelled, truncated, fullOutputPath, excludeFromContext }` | **不存在** | **缺失** |
| **BranchSummaryMessage** | `{ role: "branchSummary", summary, fromId }` | **不存在** | 缺失 |
| **CompactionSummaryMessage** | `{ role: "compactionSummary", summary, tokensBefore }` | 用 `CustomMessage(custom_type="compaction_summary")` | 存在但不够类型化 |
| **CustomMessage** | `{ role: "custom", customType, content, display, details }` | `CustomMessage(role, custom_type, content, display, details)` | 等价 |
| **`convertToLlm()`** | 统一函数处理所有自定义消息类型 → LLM 格式（含 XML wrapper） | 分散在各 provider 的 `message_converter.py` 中 | **缺少统一的转换层** |
| **可扩展消息注册** | TypeScript `declare module` + `CustomAgentMessages` 接口 | 固定 union type | 不支持第三方扩展 |

**建议**:
1. 添加 `BashExecutionMessage` 类型
2. 创建 `agent_core/harness/messages.py` — 统一的 `convert_to_llm()` 函数
3. 为 `CompactionSummaryMessage` 和 `BranchSummaryMessage` 创建独立类型

---

### D. System Prompt 构建

| 维度 | pi-mono `harness/system-prompt.ts` (35行) | agent_core `prompts/builder.py` (131行) | 差距 |
|------|------|------|------|
| **职责** | 仅格式化 skills → XML | 完整 prompt 构建（base + tools + guidelines + context + skills + meta） | agent_core 更丰富 |
| **Callable 模式** | `systemPrompt: string | ((context) => string | Promise<string>)` | 仅支持 `str` | **缺少 callable 模式** |
| **Harness 集成** | `createTurnState()` 中根据 callable/string 动态构建 | 静态 `self.state.system_prompt` | 不支持 turn 间动态重建 |
| **Skill 格式化** | `formatSkillsForSystemPrompt()` — XML with `<location>` | `format_skills_for_prompt()` — XML without `<location>` | 基本等价但格式略有不同 |

**建议**:
1. `system_prompt` 支持 callable 模式：`str | Callable[[SystemPromptContext], str | Awaitable[str]]`
2. 在 `prepareNextTurn` 中重新调用 callable 获取最新 system prompt

---

### E. ExecutionEnv 抽象

| 维度 | pi-mono `harness/types.ts` + `env/nodejs.ts` (529行) | agent_core | 差距 |
|------|------|------|------|
| **FileSystem 接口** | 17 个方法: `absolutePath`, `joinPath`, `readTextFile`, `readTextLines`, `readBinaryFile`, `writeFile`, `appendFile`, `fileInfo`, `listDir`, `canonicalPath`, `exists`, `createDir`, `remove`, `createTempDir`, `createTempFile`, `cleanup` + `cwd` | **不存在** | **完全缺失** |
| **Shell 接口** | `exec(command, options)` — 支持 `cwd`, `env`, `timeout`, `abortSignal`, `onStdout`, `onStderr` | 工具直接调用 `subprocess` | **无抽象层** |
| **FileInfo** | `{ name, path, kind, size, mtimeMs }` | 无标准类型 | 缺失 |
| **FileError** | typed error: `aborted`, `not_found`, `permission_denied`, `not_directory`, `is_directory`, `invalid`, `not_supported`, `unknown` | 直接用 Python 异常 | 缺失 |
| **ExecutionError** | typed error: `aborted`, `timeout`, `shell_unavailable`, `spawn_error`, `callback_error`, `unknown` | 直接用 Python 异常 | 缺失 |
| **Result 模式** | `Result<TValue, TError> = { ok: true, value } | { ok: false, error }` | 异常驱动 | 设计差异（Python 用异常更自然） |

**建议**:
1. 创建 `agent_core/harness/env.py` — 定义 `FileSystem` Protocol + `Shell` Protocol
2. 实现 `LocalExecutionEnv` 默认实现（`os` + `subprocess`）
3. Python 用 `try/except` + typed exceptions 替代 `Result<T,E>` 模式

---

### F. Tool 系统

| 维度 | pi-mono `types.ts` + `agent-loop.ts` | agent_core `tools/base.py` + `core/tool_runner.py` | 差距 |
|------|------|------|------|
| **ToolDefinition** | `AgentTool { name, description, parameters, executionMode? }` | `ToolDefinition { name, description, parameters, ... }` | **缺少 `execution_mode` per-tool 覆盖** |
| **Tool 执行模式** | per-tool `executionMode: "sequential" | "parallel"` 覆盖 batch 默认值 | 无 per-tool 覆盖 | 缺失 |
| **Tool Pipeline** | 三阶段: `prepareToolCall` → `executePreparedToolCall` → `finalizeExecutedToolCall` | `_run_single_tool` 单步执行 | **缺少正式 pipeline** |
| **Before Hook 集成** | `beforeToolCall` 返回 `{ block, reason }` — 类型化 | `before_tool_call` 返回 `dict[str, Any]` | 类型不安全 |
| **After Hook 集成** | `afterToolCall` 返回 `{ content, details, isError, terminate }` | `after_tool_call` 返回 `dict[str, Any]` | 类型不安全 |
| **Terminate 支持** | `terminate: true` 提前终止 batch | 不存在 | 缺失 |
| **ToolResult** | `{ content, details, display }` | `ToolResult(content, details, display)` | 等价 |

**建议**: 已在 Task 10 中覆盖

---

### G. Session 存储

| 维度 | pi-mono `harness/types.ts` + `session/` | agent_core `session/store.py` (79行) | 差距 |
|------|------|------|------|
| **Entry 类型数** | **11 种**: MessageEntry, ThinkingLevelChangeEntry, ModelChangeEntry, ActiveToolsChangeEntry, CompactionEntry, BranchSummaryEntry, CustomEntry, CustomMessageEntry, LabelEntry, SessionInfoEntry, LeafEntry | **5 种**: MessageEntry, CompactionEntry, ModelChangeEntry, ThinkingLevelChangeEntry, CustomEntry | **缺少 6 种** |
| **树结构** | 每个 entry 有 `parentId`，支持 `getPathToRoot(leafId)` | 仅 `MessageEntry` 有可选 `parent_id`，未使用 | **无树结构** |
| **Leaf 追踪** | `getLeafId()`, `setLeafId()` | 不存在 | 缺失 |
| **Session Context** | `buildContext()` — 从 session tree 重建完整上下文 | `_restore_messages()` — 仅从 entries 恢复消息 | 过于简陋 |
| **Session Repo** | `SessionRepo` 支持 `create`, `open`, `list`, `delete`, `fork` | 无 repo 抽象 | 缺失 |
| **内存缓存** | `byId: Map`, `labelsById: Map` | 每次 `load_session` 全量读取 | 性能差 |
| **Pending Writes** | `PendingSessionWrite[]` — 运行期间缓冲 | 每条立即写入 | I/O 效率低 |

**建议**: 已在 Task 11 中覆盖

---

### H. 事件/Hook 系统

| 维度 | pi-mono `harness/types.ts` | agent_core `core/events.py` | 差距 |
|------|------|------|------|
| **Agent 事件** | 13 种: `message_start`, `message_update`, `message_end`, `text_delta`, `thinking_delta`, `tool_call_delta`, `tool_execution_start`, `tool_execution_update`, `tool_execution_end`, `turn_start`, `turn_end`, `agent_start`, `agent_end` | 12 种: MessageStart, MessageUpdate, MessageEnd, TextDelta, ThinkingDelta, ToolCallDelta, ToolExecutionStart, ToolExecutionUpdate, ToolExecutionEnd, TurnStart, TurnEnd, AgentStart, AgentEnd | 基本等价 |
| **Harness Own 事件** | **18 种**: queue_update, save_point, abort, settled, before_agent_start, context, before_provider_request, before_provider_payload, after_provider_response, tool_call, tool_result, session_before_compact, session_compact, session_before_tree, session_tree, model_update, thinking_level_update, resources_update, tools_update | **0 种** | **完全缺失** |
| **Hook Result Map** | `AgentHarnessEventResultMap` — 每种 hook 有明确的返回类型 | hook 返回 `dict[str, Any]` | 类型不安全 |
| **双层事件** | `on(type, handler)` + `subscribe(listener)` | 只有 `subscribe(listener)` | 缺少 typed hook 注册 |

**建议**: 已在 Task 3-4 中覆盖

---

### I. 总结: Harness 模块缺失度排序

| 优先级 | 模块 | 缺失度 | 工作量 |
|--------|------|--------|--------|
| **P0** | AgentHarness 编排层 | 完全缺失 | 大（新建 ~600 行） |
| **P0** | Typed Hook 系统 | 完全缺失 | 中 |
| **P0** | `prepareNextTurn` 支持 | 完全缺失 | 小 |
| **P1** | Token-aware Compaction | 严重不足 | 大 |
| **P1** | Session 树结构 | 严重不足 | 大 |
| **P1** | 自定义消息类型（BashExecution 等） | 部分缺失 | 中 |
| **P2** | ExecutionEnv 抽象 | 完全缺失 | 中 |
| **P2** | Skill content + invocation | 部分缺失 | 小 |
| **P2** | Prompt Template 系统 | 完全缺失 | 中 |
| **P2** | Tool Pipeline 标准化 | 部分缺失 | 中 |
| **P3** | 输出截断增强 | 部分缺失 | 小 |
| **P3** | Ignore file 支持 | 缺失 | 小 |
