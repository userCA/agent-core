# Agent 框架优化分析 — Phase 2（新增模块与跨切面关注点）

> **本文档为 `docs/agent-framework-optimization-plan.md` 的补充**。原计划（Phase 1）聚焦于 Thin Core / Thick Harness 架构重构。
>
> **状态说明（2026-07-17）：** Phase 1 的 Harness 演进（P0/P1/P2）已在 `.qoder/specs/Agent完备Harness演进_task-31c.md` 中落地完成，包括 pending flush、setter 语义、provider hooks、职责收敛等。下文「Phase 1 均未实施」的描述**已过时**，请以 task-31c 修订版与代码为准。
>
> 自原计划撰写（2026-06）以来，代码库新增了 `memory/`、`companion/` 等模块。本文档其余部分仍分析：**新增模块的质量问题**、**跨切面关注点**、以及 Phase 1 未覆盖的 Gap。

---

## 现状总览

```
agent_core/
├── core/            # 纯运行时（Phase 1 覆盖）
├── providers/       # LLM 适配（Phase 1 部分覆盖）
├── session/         # 会话持久化（Phase 1 覆盖）
├── compaction/      # 上下文压缩（Phase 1 覆盖）
├── extensions/      # 扩展/Hook（Phase 1 覆盖）
├── prompts/         # 系统提示构建（Phase 1 部分覆盖）
├── resources/       # 资源加载（Phase 1 部分覆盖）
├── tools/           # 工具抽象 + 内置工具（Phase 1 部分覆盖，新增 sandbox/aigc/widgets）
│
├── memory/          # 记忆系统（新增，本文档覆盖）★★★
│   ├── base.py
│   ├── extension.py
│   └── adapters/    # inmemory / mem0 / openviking
│
├── companion/       # 宠物伴侣系统（新增，本文档覆盖）★★
│   ├── state_machine.py / bones.py / observer.py
│   ├── guide.py / memory.py / naming.py / species.py
│   ├── daily_rhythm.py / topic_extractor.py / templates.py
│   └── types.py
│
├── skill_evolution/ # 技能自进化（新增，本文档覆盖）★★★
│   ├── types.py / agent.py / store.py
│   ├── collector.py / validation.py / audit.py
│
├── knowledge/       # 本地知识库（新增，本文档覆盖）★★
│   └── local_kb.py
│
├── retrieval/       # 检索抽象（新增，本文档覆盖）★
│   ├── base.py / extension.py / tool.py
│
└── observability.py # OpenTelemetry 观测（新增，本文档覆盖）★★
```

---

## 一、Memory 系统优化

### 1.1 MemoryStore Protocol 不完整

**现状** (`memory/base.py`, 22行)：

```python
@runtime_checkable
class MemoryStore(Protocol):
    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None: ...
    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]: ...
    async def forget(self, *, session_id: str) -> None: ...
```

**问题**：
- 缺少 `update(record_id, ...)` — 无法修正已存储记忆
- 缺少 `list(session_id)` — 无法枚举/审查记忆
- `InMemoryMemoryStore` 和 `Mem0MemoryStore` 的 `forget` 实现不完整（`OpenVikingMemoryStore.forget` 未实现）
- `MemoryRecord` 无 `id` 字段，无法精确定位单条记忆

**建议**：
```python
class MemoryStore(Protocol):
    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> str:  # 返回 record_id
    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]: ...
    async def update(self, *, record_id: str, text: str | None = None, metadata: dict[str, Any] | None = None) -> None: ...
    async def forget(self, *, session_id: str, record_id: str | None = None) -> None:  # 支持单条删除
    async def list(self, *, session_id: str, limit: int = 100) -> list[MemoryRecord]: ...
```

**优先级**: P1 | **工作量**: 小 | **风险**: 低（Protocol 扩展，向后兼容）

---

### 1.2 MemoryExtension 仅处理用户消息

**现状** (`memory/extension.py` L29-36)：

```python
if isinstance(evt, MessageEnd):
    msg = evt.message
    if getattr(msg, "role", None) != "user":
        return  # ← 仅存储用户消息
```

**问题**：
- 助手的关键推理、工具执行结论、技能应用结果均未被记忆
- 记忆召回仅在 `transform_context` 中注入为 system 消息，但注入位置固定为 latest user message 之后，可能与工具调用上下文脱节

**建议**：
- 配置化选择存储哪些 role（`remember_roles: list[str] = ["user", "assistant"]`）
- 对 AssistantMessage，提取文本内容 + 工具调用摘要作为记忆
- 记忆召回注入位置改为在 turn 开始时插入到 LLM messages 的 system 之后、对话历史之前

**优先级**: P1 | **工作量**: 小 | **风险**: 中（改变记忆内容可能影响召回质量）

---

### 1.3 记忆写入无去重/质量控制

**现状** (`memory/extension.py` L37-48)：

```python
self._pending.append("\n".join(text_parts))
if len(self._pending) > _MAX_PENDING:
    self._pending.pop(0)
# TurnEnd 时全量写入，无去重
for text in self._pending:
    await self._store.remember(session_id=session_id, text=text)
```

**问题**：
- 用户连续发送相似消息 → 重复记忆
- 短消息（如"好的"、"谢谢"）也被存储，污染记忆库
- 无最小长度过滤

**建议**：
- 新增 `min_text_length: int = 10` 过滤短消息
- 新增简单的去重：与最近 N 条记忆的 token overlap > 80% 则跳过
- 新增 `max_pending_per_turn: int = 5` 限制每轮写入量

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

### 1.4 记忆适配器一致性

**现状**：三个适配器（inmemory / mem0 / openviking）实现质量参差不齐：
- `InMemoryMemoryStore` 使用 `asyncio.Lock`，正确
- `Mem0MemoryStore` 和 `OpenVikingMemoryStore` 的异步边界不清晰（同步 HTTP 调用是否在 asyncio 中阻塞？）
- 全局单例模式不一致

**建议**：
- 统一适配器基类或 mixin，提供 `_ensure_async` 装饰器
- 为每个适配器编写 `test_memory_*_store.py` 一致性测试（Protocol 合规 + 基本 CRUD）
- 使用 `asyncio.to_thread` 包装所有同步 IO

**优先级**: P2 | **工作量**: 中 | **风险**: 低

---

## 二、Companion 伴侣系统优化

### 2.1 全局模型单例 + 线程锁

**现状** (`companion/bones.py` 未使用全局，但 `knowledge/local_kb.py` 有类似问题)：

实际上 companion 的 `roll_companion` 是无状态的，但 `EmotionFSM._apply_modifiers` 中使用了 `import random` 在方法内部（L218, L230），这是不规范的。

**问题**：
- `import random` 在方法内部而非模块顶部
- `random.random()` 不是线程安全的（虽然 CPython GIL 保护，但逻辑上应使用 `random.Random(seed)` 实例）
- EmotionFSM 的 breed modifier 概率判断使情绪转换非确定性，难以测试和复现

**建议**：
- 将 `random` 移至模块顶部导入
- 为 EmotionFSM 注入 RNG 实例（默认 `random.Random()`），测试时可注入确定性 RNG
- 移除方法内 import

**优先级**: P3 | **工作量**: 小 | **风险**: 低

---

### 2.2 Companion 与 Core 框架耦合度

**现状**：`CompanionExtension`（`extensions/companion.py`, 234行）直接依赖 `agent_core.core.events` 中的具体事件类型（`TurnStart`, `ToolExecutionStart`, `ToolExecutionEnd`, `TurnEnd`, `AgentEnd`），并硬编码事件→情绪的映射。

**问题**：
- Companion 是业务特性，但被实现为 extension，与 memory/retrieval 等基础设施混放
- 事件→情绪的映射逻辑分散在 `on_event` 中，难以配置和测试
- `_decay_task` 使用 `asyncio.ensure_future` 而非 `asyncio.create_task`，且无取消保护

**建议**：
- 将 Companion 移至 `agent_core/features/companion/` 或保持 extension 但明确标注为"示例扩展"
- 将事件→情绪映射提取为配置表（类似 `TRANSITIONS` 但更声明式）
- `_start_decay_loop` 中捕获 `asyncio.CancelledError`，避免任务取消时打印异常堆栈

**优先级**: P3 | **工作量**: 小 | **风险**: 低

---

### 2.3 CompanionMemory / Observer / Guide 集成

**现状**：`companion/memory.py`、`observer.py`、`guide.py` 各自独立，通过 `CompanionMemory` 串联，但：
- `SilentObserver` 的 `last_active_at` 是模块级全局变量（`observer.py`）
- `GuideNPC.decide_bubble` 依赖 LLM 调用，无降级策略
- 记忆驱动的气泡生成与 `MemoryExtension` 无集成（两个独立的记忆系统）

**问题**：
- 全局 `last_active_at` 在多用户场景下会互相覆盖
- Guide LLM 调用失败时静默返回 None，用户无反馈

**建议**：
- `last_active_at` 改为实例属性（per-uid）
- Guide 气泡生成增加本地模板降级（LLM 不可用时使用预定义模板）
- 考虑将 `CompanionMemory` 与 `MemoryExtension` 共享同一个 `MemoryStore` 实例（当前已传入，但语义不同）

**优先级**: P2 | **工作量**: 中 | **风险**: 中（多用户场景 bug）

---

## 三、Skill Evolution 技能自进化优化

### 3.1 Validation Gate 使用关键词重叠启发式

**现状** (`skill_evolution/validation.py` L350-378)：

```python
# Heuristic fallback: keyword overlap scoring
query_words = set(re.findall(r'\w+', query_lower))
skill_words = set(re.findall(r'\w+', skill_lower))
overlap = len(query_words & skill_words) / len(query_words) if query_words else 0
base_score = min(overlap * 2, 1.0)
```

**问题**：
- 关键词重叠对中文支持极差（`\w+` 不匹配中文字符）
- 即使对英文，关键词重叠也无法衡量"规则是否真正指导了正确行为"
- `agent_runner` 参数几乎总是 None（需要外部注入一个 agent 执行器），导致始终走启发式路径
- 验证阈值 `test_threshold = 0.05` 对启发式评分无意义

**建议**：
- 中文分词：引入 `jieba` 或使用字符级 n-gram 重叠
- 提供 `DummyAgentRunner` 作为默认值，文档明确说明生产环境需注入真实 runner
- 启发式评分增加语义相似度（使用 `knowledge/local_kb.py` 的 embedding 模型计算 cosine similarity）
- 将 `test_threshold` 改为可配置且对启发式/真实执行区分

**优先级**: P1 | **工作量**: 中 | **风险**: 中（改变验证逻辑可能影响进化质量）

---

### 3.2 OfflineEvolutionAgent 状态管理

**现状** (`skill_evolution/agent.py` L126-127)：

```python
self._analyzed_trace_ids: set[str] = set()  # 实例级
self._llm_call_count = 0
```

**问题**：
- `_analyzed_trace_ids` 是实例级状态，进程重启后丢失 → 重复分析相同 traces
- 无持久化的"已分析"标记，Store 中无此信息
- `max_llm_calls` 预算计算有 bug（L251）：`remaining * batch_size` 可能导致远超预算的迭代

```python
# L250-257 — remaining 可能为负数时仍进入循环
remaining = self.max_llm_calls - len(tasks)
for i in range(0, min(len(failure_traces), remaining * batch_size), batch_size):
```

**建议**：
- 在 `SkillEvolutionStore` 中添加 `mark_analyzed(trace_id)` 方法，持久化已分析标记
- 修复预算计算：`remaining = max(0, self.max_llm_calls - len(tasks) - self._llm_call_count)`
- 添加 `reset_analyzed()` 方法支持手动重置

**优先级**: P1 | **工作量**: 小 | **风险**: 低

---

### 3.3 Proposal 解析脆弱

**现状** (`skill_evolution/agent.py` L382-421, L303-344)：
- `_parse_proposal_json` 和 `_parse_batch_proposals` 逻辑重复
- JSON 解析失败时静默返回 None，无诊断信息
- LLM 输出的 JSON 可能包含 markdown 代码块、额外文本，解析成功率不稳定

**建议**：
- 合并两个解析函数为统一的 `_parse_proposals(raw, source_traces, skill_name, is_batch)`
- 引入 `json_repair` 库（容忍不完整 JSON）或使用 `llm.parse_json` 模式（在 prompt 中要求纯 JSON）
- 解析失败时记录 raw output 到 audit log（`audit.py`）供后续分析

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

### 3.4 SkillEvolutionStore 接口不完整

**现状** (`skill_evolution/store.py`, 294行)：
- 有 `get_traces`、`append_trace`、`get_trace_count`
- 缺少 `update_trace`、`delete_trace`、`get_traces_by_outcome`（按结果筛选）
- JSONL 实现无内存缓存，每次查询全量扫描

**建议**：
- 添加 `get_traces_by_outcome(skill_name, outcome, limit)` 方法
- JSONL store 添加 `_index_by_skill` 内存缓存（加载时构建）
- 添加 `prune(old_than_seconds)` 方法清理旧 traces

**优先级**: P2 | **工作量**: 中 | **风险**: 低

---

### 3.5 Collector 与 Live Agent 集成缺失

**现状** (`skill_evolution/collector.py`, 226行)：
- `TraceCollector` 通过监听事件收集 traces
- 但 `execution_outcome` 的判定逻辑不完整 — 仅凭 `ToolExecutionEnd.is_error` 无法判断任务级成功/失败
- 无 `user_feedback` 收集通道（需要外部调用 `collector.record_feedback(trace_id, feedback)`）

**建议**：
- 引入任务级成功判定：结合 `AgentEnd` 的 stop_reason + 工具错误率 + 用户显式反馈
- 在 `ChatAssistant` 中暴露 `record_feedback(session_id, feedback)` API
- 添加 `outcome` 判定的可配置策略

**优先级**: P1 | **工作量**: 中 | **风险**: 中

---

## 四、Knowledge / Retrieval 优化

### 4.1 LocalKnowledgeBase.add 同步阻塞

**现状** (`knowledge/local_kb.py` L147-169)：

```python
def add(self, name: str, content: str) -> str:
    """Chunk and embed (synchronous, blocks)."""
    ...
    model = _get_model()  # 同步
    for i, chunk in enumerate(chunks):
        vec = model.encode(chunk, normalize_embeddings=True)  # 同步，阻塞事件循环
```

**问题**：
- `add()` 是同步方法，在 async 宿主中调用会阻塞事件循环
- 虽有 `add_async()` 方法，但命名不一致（其他方法均为同步）
- `_get_model()` 使用全局单例 + 线程锁，首次加载 SentenceTransformer 可能耗时 10-30s

**建议**：
- 将 `add()` 标记为 deprecated，统一使用 `add_async()`
- 模型加载改为懒加载 + `asyncio.to_thread`
- 添加模型预热 API：`await kb.warmup()` 在应用启动时预加载模型

**优先级**: P1 | **工作量**: 小 | **风险**: 低

---

### 4.2 retrieve 全量扫描

**现状** (`knowledge/local_kb.py` L270-301)：

```python
async def retrieve(self, query: Query) -> list[RetrievedChunk]:
    q_vec = model.encode(query.text, normalize_embeddings=True)
    results = []
    for doc_dir in self._dir.iterdir():  # 全量扫描
        for npy_path in sorted(doc_dir.glob("chunk_*.npy")):  # 全量扫描
            doc_vec = np.load(str(npy_path))  # 每个 chunk 一次 IO
            score = float(np.dot(q_vec, doc_vec))
```

**问题**：
- 每次查询加载所有 chunk 的 embedding 向量到内存
- 无向量索引（ brute-force cosine similarity）
- 文档量大时（>1000 chunks）查询延迟不可接受

**建议**：
- 短期：添加内存 embedding 缓存（启动时加载所有向量到 numpy 矩阵，查询时矩阵乘法）
- 中期：集成 `faiss` 或 `numpy` 矩阵批量计算
- 长期：支持可插拔向量后端（faiss / chroma / qdrant）

```python
# 短期优化：启动时预加载 embedding 矩阵
def _build_index(self):
    vectors = []
    for npy_path in self._dir.glob("**/chunk_*.npy"):
        vectors.append(np.load(npy_path))
    self._index = np.vstack(vectors) if vectors else None
```

**优先级**: P1 | **工作量**: 中 | **风险**: 低

---

### 4.3 Retrieval 模块过薄

**现状** (`retrieval/base.py` 25行, `extension.py` 36行, `tool.py` 38行)：
- `Query` / `RetrievedChunk` 类型定义
- `RetrievalExtension` 仅做简单注入
- 无 reranking、query expansion、multi-hop retrieval

**建议**：
- 添加 `Reranker` Protocol + 实现（基于 cross-encoder 或 LLM）
- 添加 `HybridRetriever` 组合 keyword + semantic 检索
- `RetrievalExtension` 支持配置注入位置（system / user message）

**优先级**: P2 | **工作量**: 中 | **风险**: 低

---

## 五、Observability 观测优化

### 5.1 LLM 调用未被追踪

**现状** (`observability.py`)：
- `observe()` context manager 仅追踪 tool calls（通过 hook 注入）
- `trace_llm_call()` 存在但**无任何调用方** — provider 未集成
- 无 agent run 级 span

**问题**：
- LLM 调用是 agent 最关键的耗时/耗资操作，却无自动追踪
- 需要手动在每个 provider 中包装 `trace_llm_call()`

**建议**：
- 在 `ModelProvider.stream()` 的调用处（`loop.py` `_stream_assistant`）自动包装 `trace_llm_call()`
- 或在 `providers/base.py` 的 `stream` Protocol 中添加 tracing wrapper
- 添加 agent run 级 span（在 `agent_loop` 入口/出口）

```python
# loop.py _stream_assistant 中：
with trace_llm_call(provider=config.model.provider, model=config.model.id, session_id=...):
    stream = config.stream_fn(...)
    async for evt in stream:
        ...
```

**优先级**: P1 | **工作量**: 小 | **风险**: 低

---

### 5.2 无 Token 使用量 / 成本追踪

**现状**：
- `Usage` 模型有 `input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_write_tokens`
- 但无任何地方聚合/记录/暴露这些数据
- `ModelCost` 有单价但未使用

**问题**：
- 无法知道一次会话花了多少钱
- 无法做成本预警或预算控制
- Anthropic provider 返回的 usage 数据未被转换为 `Usage` 模型（需检查）

**建议**：
- 新增 `UsageTracker` 类，订阅 `MessageEnd` 事件累加 usage
- 新增 `CostEstimator` 根据 `Model.cost` 计算每次调用的成本
- 在 `AgentState` 或 `AgentEnd` 事件中暴露累计 usage/cost
- 添加 `max_cost` 配置，超预算时终止 agent run

**优先级**: P1 | **工作量**: 中 | **风险**: 低

---

### 5.3 无 Metrics / 结构化日志

**现状**：
- 仅有 `logging.warning`/`logging.exception` 散落在各处
- 无结构化日志（所有 log 为字符串）
- 无 metrics（延迟、错误率、吞吐量）

**建议**：
- 引入 `structlog` 或统一使用 `logging` 的结构化模式
- 定义关键 metrics：`agent.turn.duration`、`agent.tool.duration`、`agent.llm.duration`、`agent.tool.error_rate`
- 添加 `MetricsCollector` Protocol，支持 Prometheus / 内存实现

**优先级**: P2 | **工作量**: 中 | **风险**: 低

---

## 六、Providers 优化

### 6.1 Message Converter 仅支持 OpenAI 格式

**现状** (`providers/message_converter.py`)：
- `create_default_converter` 仅生成 OpenAI 格式消息
- Anthropic provider 有自己的 converter，但功能不对称
- `CustomMessage` 仅处理 `compaction_summary` 类型，其他 custom 类型被静默丢弃

**问题**：
- 新增消息类型（如 `BashExecutionMessage`、`BranchSummaryMessage`）无转换路径
- Anthropic 的 `tool_result` 格式与 OpenAI 不同，converter 未统一

**建议**：
- 创建统一的 `MessageConverter` Protocol，每个 provider 实现自己的 converter
- 添加 `convert_custom_message()` 扩展点，允许注册 custom 类型转换
- 统一处理 `ToolResultMessage`（OpenAI 用 `role=tool`，Anthropic 用 `tool_result` content block）

**优先级**: P1 | **工作量**: 中 | **风险**: 中（改变消息格式可能影响 provider 兼容性）

---

### 6.2 无 Model Fallback / 熔断

**现状**：
- `ModelRegistry.get_provider()` 在 provider 未注册时抛出 `UnknownProviderError`
- 无自动 fallback（如 primary model 失败时切换到 backup）
- 无 rate limit 处理（429 错误直接抛出）

**建议**：
- 添加 `ModelGroup` 概念：一组可互换的 models，按优先级尝试
- 添加 `CircuitBreaker`：连续 N 次失败后暂时禁用 provider
- 在 `agent_loop` 的 retry 逻辑中支持切换 model

**优先级**: P2 | **工作量**: 中 | **风险**: 中

---

### 6.3 Auth 传递不透明

**现状** (`providers/auth.py`, 51行)：
- `ProviderAuth(api_key="")` 常被传入空 key，依赖 provider 的 `AuthSource` 解析
- `OfflineEvolutionAgent._call_llm()` 传入 `ProviderAuth(api_key="")` 注释为 "resolved by provider's auth source" — 但如果 provider 的 auth source 未配置则静默失败

**建议**：
- `ProviderAuth` 添加 `is_empty` 属性，调用前校验
- 文档明确说明 auth 解析责任归属

**优先级**: P3 | **工作量**: 小 | **风险**: 低

---

## 七、Core 深读发现的 Gap（Phase 1 未覆盖）

### 7.1 Loop 无 mid-run compaction

**现状** (`loop.py`)：
- Compaction 仅在 overflow error 时触发（retry 路径）
- 长对话中，context 可能在 turn 开始前已超过阈值，但直到 LLM 返回 overflow error 才压缩

**建议**：
- 在每个 turn 开始时检查 context 大小，提前触发 compaction（不等待 overflow）
- 参考 pi-mono 的 `shouldCompactBeforeTurn` 模式

**优先级**: P1 | **工作量**: 小 | **风险**: 中（可能改变对话行为）

---

### 7.2 Tool 错误累积无智能处理

**现状** (`loop.py` L181-182)：

```python
if assistant.stop_reason in ("error", "aborted"):
    break
```

**问题**：
- 工具连续失败时，loop 仅在第 N 次 LLM 返回 error 时停止
- 无"工具失败率过高则提前终止"的逻辑
- 无"连续工具失败 → 告知用户并停止"的友好处理

**建议**：
- 添加 `max_consecutive_tool_errors: int = 5` 配置
- 在 `tool_runner.py` 中追踪连续错误，超过阈值时设置 `assistant.stop_reason = "tool_errors"` 并 break

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

### 7.3 AgentState Pydantic validate_assignment 开销

**现状** (`core/state.py`）：

```python
class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)
```

**问题**：
- `validate_assignment=True` 意味着每次 `self.state.messages.append(msg)` 都触发 Pydantic 验证
- 长对话中 messages 列表可能有数百条，每次 append 都验证整个列表

**建议**：
- 移除 `validate_assignment`，改为在关键边界（`prompt()` 入口、`_finish_run()`）手动验证
- 或使用 `model_validate` 仅在需要时验证

**优先级**: P2 | **工作量**: 小 | **风险**: 低（需确保关键路径验证）

---

### 7.4 ToolRegistry 无 unregister / enable / disable

**现状** (`tools/base.py`)：
- `ToolRegistry` 只有 `register()` 和 `get()`
- 无 `unregister(name)` — 无法动态移除工具
- 无 `enable(name)` / `disable(name)` — 无法临时禁用工具

**问题**：
- Phase 1 Task 10 提到 per-tool `execution_mode`，但未提及 enable/disable
- 动态工具管理（如用户关闭某个工具）无法实现

**建议**：
- 添加 `unregister(name)`, `enable(name)`, `disable(name)`, `is_enabled(name)`
- `list()` 和 `to_definitions()` 仅返回 enabled 工具
- 在 `ToolDefinition` 中添加 `enabled: bool = True`

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

### 7.5 事件系统缺少关键事件类型

**现状** (`core/events.py`)：
- 12 种事件，覆盖基本生命周期
- 缺少：
  - `CostUpdate` — token 使用量/成本更新
  - `ModelChange` — model 切换事件
  - `ToolEnabledChange` — 工具启用/禁用
  - `CompactionStart` / `CompactionEnd` — 压缩生命周期
  - `TurnTimeout` — turn 超时

**建议**：
- 按 Phase 1 Harness 事件系统设计补充
- 至少先添加 `CostUpdate` 和 `CompactionStart/End`

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

### 7.6 Sequential 模式轮询效率低

**现状** (`core/tool_runner.py` L96-106)：

```python
while not tool_task.done():
    try:
        partial = update_queue.get_nowait()
        yield ToolExecutionUpdate(...)
    except asyncio.QueueEmpty:
        await asyncio.sleep(0.5)  # ← 500ms 固定轮询
```

**问题**：
- 固定 500ms 轮询间隔：太快浪费 CPU，太慢响应迟钝
- 应使用 `asyncio.Queue.get()` 带超时，或 `asyncio.wait()` 组合

**建议**：
```python
while not tool_task.done():
    try:
        partial = await asyncio.wait_for(update_queue.get(), timeout=0.5)
        yield ToolExecutionUpdate(...)
    except asyncio.TimeoutError:
        continue
```

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

## 八、跨切面关注点（全新）

### 8.1 成本追踪与预算控制

**现状**：无。

**建议**：
- 新增 `agent_core/cost.py`：
  - `CostTracker`：累加 Usage × ModelCost
  - `BudgetGate`：超预算时抛出 `BudgetExceeded` 异常
  - `CostEstimate`：基于 token 数的预估（不依赖 provider 返回 usage）
- 在 `AgentLoopConfig` 中添加 `max_cost: float | None = None`
- 在 `AgentEnd` 事件中添加 `total_cost: float` 字段

**优先级**: P1 | **工作量**: 中 | **风险**: 低

---

### 8.2 工具限流（Rate Limiting）

**现状**：无。工具调用无频率/并发限制（除 `max_concurrent=8` 的 semaphore）。

**问题**：
- 外部 API 工具（HTTP、AIGC）可能触发上游 rate limit
- 无 per-tool 或 per-session 限流

**建议**：
- 新增 `agent_core/tools/rate_limiter.py`：
  - `TokenBucketRateLimiter`：令牌桶算法
  - `SlidingWindowRateLimiter`：滑动窗口
- `ToolDefinition` 添加 `rate_limit: RateLimitConfig | None`
- 在 `_run_single_tool` 执行前获取令牌

**优先级**: P2 | **工作量**: 中 | **风险**: 低

---

### 8.3 多租户隔离

**现状**：无显式多租户支持。`session_id` 是唯一隔离边界。

**问题**：
- 无 per-tenant 资源配额（最大 session 数、最大并发 agent run 数）
- 无 per-tenant 成本隔离
- `ModelRegistry` 全局共享，无 per-tenant 凭证

**建议**：
- 在 `ExtensionContext` 中添加 `tenant_id: str | None`
- 添加 `TenantQuota` Protocol：`max_sessions`, `max_concurrent_runs`, `max_monthly_cost`
- 在 `AgentSession.start()` 时检查配额

**优先级**: P3 | **工作量**: 大 | **风险**: 中

---

### 8.4 健康检查与就绪探针

**现状**：无。

**建议**：
- 新增 `agent_core/health.py`：
  - `HealthChecker`：检查 provider 连通性、存储可用性、模型列表
  - `ReadinessProbe`：综合判断框架是否就绪
- 在 `ModelRegistry` 中添加 `health_check(provider_name)` 方法
- 暴露为 scene 层的 `/health` HTTP 端点

**优先级**: P2 | **工作量**: 小 | **风险**: 低

---

## 九、测试覆盖 Gap

### 9.1 核心 Loop 测试不足

**现状**：
- `tests/core/test_loop_text.py`、`tests/core/test_loop_tools.py` 覆盖基本场景
- 缺少：retry 逻辑测试、overflow compaction 测试、steering 中断测试、HITL 恢复测试、abort 测试

**建议**：
- 为每个 Phase 1/2 Task 添加对应的测试文件
- 使用 `FakeProvider.queue_script` 模拟各种场景（overflow、retry、tool error）

**优先级**: P1 | **工作量**: 大 | **风险**: 低

---

### 9.2 新增模块无测试

**现状**：
- `memory/`：有 `test_inmemory_store.py`、`test_mem0_store.py`、`test_openviking_store.py`，但无 `test_memory_extension.py` 的完整集成测试
- `companion/`：无测试
- `skill_evolution/`：无测试（`3b2f1cc` 提交提到 "full review, bug fixes" 但未见测试文件）
- `knowledge/`：无测试
- `retrieval/`：无测试
- `observability.py`：无测试

**建议**：
- 为每个新增模块添加基础单元测试
- 优先级：skill_evolution > knowledge > companion > retrieval > observability

**优先级**: P1 | **工作量**: 大 | **风险**: 低

---

## 十、实施优先级总览

### P0 — 高价值、低风险、快速修复

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 1 | MemoryStore Protocol 扩展（update/list/record_id） | `memory/base.py` + adapters | 小 |
| 2 | MemoryExtension 支持助手消息记忆 | `memory/extension.py` | 小 |
| 3 | MemoryExtension 去重 + 最小长度过滤 | `memory/extension.py` | 小 |
| 4 | KnowledgeBase.add 异步化 + 预热 API | `knowledge/local_kb.py` | 小 |
| 5 | KnowledgeBase.retrieve 预加载 embedding 矩阵 | `knowledge/local_kb.py` | 小 |
| 6 | Observability LLM 调用追踪集成 | `observability.py` + `loop.py` | 小 |
| 7 | Skill Evolution 预算计算 bug 修复 | `skill_evolution/agent.py` L250 | 小 |
| 8 | Skill Evolution 已分析 trace 持久化 | `skill_evolution/store.py` | 小 |
| 9 | Loop mid-run compaction 检查 | `core/loop.py` | 小 |
| 10 | ToolRegistry enable/disable/unregister | `tools/base.py` | 小 |

### P1 — 高价值、中等工作量

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 11 | Validation Gate 中文分词 + 语义相似度 | `skill_evolution/validation.py` | 中 |
| 12 | Collector 任务级成功判定 + feedback API | `skill_evolution/collector.py` + scene | 中 |
| 13 | SkillEvolutionStore 接口完善 + 缓存 | `skill_evolution/store.py` | 中 |
| 14 | Token/Cost 追踪（UsageTracker + CostEstimator） | 新增 `cost.py` | 中 |
| 15 | Message Converter 统一 + CustomMessage 扩展 | `providers/message_converter.py` | 中 |
| 16 | Provider Model Fallback + Circuit Breaker | `providers/registry.py` + 新增 | 中 |
| 17 | 健康检查（HealthChecker） | 新增 `health.py` | 小-中 |
| 18 | 核心 Loop 测试补全 | `tests/core/` | 大 |
| 19 | 新增模块测试（skill_evolution, knowledge, companion） | `tests/` | 大 |

### P2 — 中等价值

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 20 | Companion 多用户 last_active_at 修复 | `companion/observer.py` | 小 |
| 21 | Companion decay loop 取消保护 | `extensions/companion.py` | 小 |
| 22 | Skill Evolution Proposal 解析统一 + 诊断 | `skill_evolution/agent.py` | 小 |
| 23 | Retrieval 模块增强（Reranker / HybridRetriever） | `retrieval/` | 中 |
| 24 | 工具限流（RateLimiter） | 新增 `tools/rate_limiter.py` | 中 |
| 25 | 结构化日志 + Metrics | 新增 `metrics.py` | 中 |
| 26 | AgentState validate_assignment 优化 | `core/state.py` | 小 |
| 27 | Sequential 模式轮询优化 | `core/tool_runner.py` | 小 |
| 28 | 事件系统补充（CostUpdate, CompactionStart/End） | `core/events.py` | 小 |
| 29 | 工具错误累积处理 | `core/loop.py` + `tool_runner.py` | 小 |

### P3 — 低优先级 / 长期

| # | 任务 | 文件 | 工作量 |
|---|------|------|--------|
| 30 | Companion 随机数规范化 + 确定性测试 | `companion/state_machine.py` | 小 |
| 31 | Companion 模块定位（移至 features/ 或标注示例） | `companion/` + `extensions/` | 小 |
| 32 | Auth 传递透明化 | `providers/auth.py` | 小 |
| 33 | 多租户隔离（TenantQuota） | 新增 | 大 |

---

## 十一、与 Phase 1 的关系

```
Phase 1（架构重构）          Phase 2（本文档）
─────────────────────────    ─────────────────────────
Task 1-12 均未实施           新增模块优化（memory/companion/
                             skill_evolution/knowledge/retrieval）
                             跨切面（cost/metrics/rate-limit）
                             Core 深读 Gap

推荐综合实施顺序：
Phase 2 P0（快速修复） → Phase 1 Task 3/9（Hook类型 + Truncation，低风险）
→ Phase 2 P1（高价值） → Phase 1 Task 1/5/8（Core瘦身 + Loop增强 + Compaction）
→ Phase 1 Task 6/7/10/11（Harness + Tool Pipeline + Session Store）
→ Phase 1 Task 2/4/12 + Phase 2 P2/P3
```

---

## 十二、Critical New Files（本文档新增关注）

1. **`agent_core/memory/extension.py`** (76行) — 记忆扩展，仅处理用户消息，需支持助手消息 + 去重
2. **`agent_core/skill_evolution/validation.py`** (495行) — 验证门，关键词重叠对中文无效，需语义相似度
3. **`agent_core/skill_evolution/agent.py`** (673行) — 进化代理，预算计算 bug + 无持久化已分析标记
4. **`agent_core/knowledge/local_kb.py`** (301行) — 本地知识库，同步阻塞 + 全量扫描检索
5. **`agent_core/observability.py`** (128行) — 观测，LLM 调用未追踪，无成本指标
6. **`agent_core/companion/observer.py`** — 全局 `last_active_at`，多用户 bug

---

## 风险缓解

| 风险 | 级别 | 缓解 |
|------|------|------|
| Memory Protocol 变更破坏适配器 | 中 | 新增方法提供默认实现（`raise NotImplementedError`），逐步迁移 |
| Validation Gate 改变影响进化质量 | 中 | 保留启发式为 fallback，新增语义相似度为可选增强 |
| Cost 追踪增加延迟 | 低 | 仅累加整数运算，纳秒级开销 |
| KnowledgeBase 预加载占用内存 | 中 | 添加 `lazy_load: bool = True` 配置，按需加载 |
| 测试补全工作量大 | 高 | 优先覆盖核心 loop 和 skill_evolution，其余逐步补齐 |

---

> **本文档生成于 2026-07-14，基于对 `agent_core/` 全量代码（~11000 行核心 + 新增模块）的逐文件审查。**

---

## 附录：Phase 1 实施状态核查（2026-07-14 验证）

对 Phase 1 全部 12 个 Task 的关键符号进行了 grep 验证，结论如下：

| Task | 状态 | 验证依据 |
|------|------|----------|
| Task 1: AgentLoopConfig 拆分 | ❌ 未实施 | `AgentLoopConfig` 仍含 `mutation_queue`/`human_input_gate`/`compact_callback`/`tool_result_max_chars`/`get_steering_messages`/`get_follow_up_messages`；无 `HarnessLoopExtensions`/`prepare_next_turn`/`should_stop_after_turn` |
| Task 2: Agent 类解耦 | ❌ 未实施 | `Agent.__init__` 仍直接接受 `provider: ModelProvider` + `auth_source: AuthSource`；仍在内部创建 `HumanInputGate()` 和 `FileMutationQueue()` |
| Task 3: Hook 类型安全化 | ❌ 未实施 | 无 `hook_types.py`；hook 返回类型仍为 `dict[str, Any]`；无 `BeforeToolCallResult` 等 dataclass |
| Task 4: HookChain 独立模块 | ❌ 未实施 | 无 `hook_chain.py`；hook chaining 逻辑仍在 `agent.py` L358-445 |
| Task 5: Loop prepareNextTurn/shouldStopAfterTurn | ❌ 未实施 | `loop.py` 无相关回调；turn 间无上下文重建逻辑 |
| Task 6: AgentHarness 编排层 | ❌ 未实施 | 无 `harness/` 模块；无 `AgentHarness` 类 |
| Task 7: AgentSession 迁移为 Harness 薄包装 | ❌ 未实施 | `session/session.py` 仍独立实现，无 Harness 委托 |
| Task 8: Compaction Token-Aware | ❌ 未实施 | 仍为 `keep_recent: int = 10` 简单策略；无 `find_cut_point`/`CompactionSettings`/`cut_points.py` |
| Task 9: 输出截断 Dual-Limit | ⚠️ 部分实施 | `truncate_head`/`truncate_tail`/`truncate_line`/`format_size` 已存在（`tools/truncate.py`），但无 `TruncationResult` dataclass、无 `utf8_byte_length`、无 `DEFAULT_MAX_BYTES=50KB`/`DEFAULT_MAX_LINES=2000` 标准常量（read.py 用 32KB/500 行，bash.py 用独立常量） |
| Task 10: Tool Pipeline 标准化 | ❌ 未实施 | 无 `prepare_tool_call`/`execute_prepared`/`finalize_executed`；无 `PreparedToolCall`/`BlockResult`；`ToolDefinition` 无 `execution_mode` |
| Task 11: Session Store 增强 | ❌ 未实施 | 仍为 5 种 entry 类型；无 `BranchSummaryEntry`/`LabelEntry`/`ActiveToolsChangeEntry`/`CustomMessageEntry`/`SessionInfoEntry`；无 `_by_id` 缓存；无 `get_entry`/`get_path_to_root`/`get_leaf_id` |
| Task 12: 迁移上层调用者 | ❌ 未实施 | scene 层仍直接组装 `Agent` + `AgentSession`；无 `AgentHarness` 引用 |

**结论：Phase 1 的 12 个 Task 全部未实施（Task 9 部分实施）。**

---

## 自我审查：哪些优化是不必要的

上一版分析犯了"为了优化而优化"的错误。经核实实际调用情况，重新分类如下：

### 我搞错的（不是问题）

| 原分析项 | 实际情况 | 结论 |
|----------|----------|------|
| KnowledgeBase.add 阻塞事件循环 | scene server 已用 `kb.add_async()`，同步 `add()` 未被 async 路径调用 | **不是问题，删除** |
| Companion `last_active_at` 多用户互相覆盖 | `last_active_at` 是 `SilentObserver` 实例属性，每个 CompanionExtension 独立实例 | **不是问题，我搞错了，删除** |
| MemoryStore 缺 `update`/`list` | grep 确认两处均未在任何调用方使用，当前 `remember/recall/forget` 三方法够用 | **不是问题，删除** |

### 过度设计（无明确需求，删除）

| 原分析项 | 为什么是过度设计 |
|----------|-----------------|
| Memory 去重 + 最小长度过滤 | 没有证据表明记忆库被污染；YAGNI |
| Skill Evolution 已分析 trace 持久化 | 进化是批处理离线任务，进程重启重跑即可，无需持久化标记 |
| Collector 任务级成功判定 + feedback API | `TraceCollector` 类未被 scene 集成（feishu/server.py 的 `collector` 是局部函数，非此类）；无需求 |
| SkillEvolutionStore 接口不完整（缺 prune/update） | 当前方法够用，缺的方法可以等需要时再加 |
| ToolRegistry enable/disable/unregister | 无动态工具管理的实际需求 |
| Retrieval Reranker / HybridRetriever | 无检索质量问题的反馈；brute-force cosine 够用 |
| 成本追踪与预算控制（CostTracker/BudgetGate） | 无成本预警需求；`budget` 引用均为 Anthropic thinking budget tokens，非费用预算 |
| 结构化日志 + Metrics | 无运营监控需求；当前 `logging.warning/exception` 够用 |
| Provider Model Fallback / 熔断 | 无多模型冗余部署场景 |
| 健康检查 HealthChecker | 可用简单端点替代，无需独立模块 |
| 事件系统补充（CostUpdate 等） | 无订阅这些事件的需求 |
| AgentState validate_assignment 优化 |  premature optimization；Pydantic 验证开销在消息量级下可忽略 |
| Sequential 模式轮询优化（`asyncio.wait_for`） | 当前 500ms sleep 工作正常；改动收益极小 |
| 工具限流 RateLimiter | 无上游 rate limit 问题的反馈 |
| 多租户隔离 TenantQuota | 无多租户部署场景 |

### 真正的问题（保留）

| # | 问题 | 为什么是真正的问题 |
|---|------|-------------------|
| 1 | ~~MemoryExtension 仅存用户消息~~ | **已撤销**：MemoryExtension 是用户画像/RAG 系统，与 session store 职责不同，不存在冗余 |
| 2 | **Skill Evolution 预算计算 bug**（`agent.py:250`） | 实际 bug：`remaining * batch_size` 可远超 `max_llm_calls` |
| 3 | **Validation Gate 中文分词** | 实际 bug：`\w+` 不匹配中文，验证评分对中文 skill 始终为 0 |
| 4 | **Observability 未追踪 LLM 调用** | 功能缺口：`trace_llm_call()` 已实现但零调用方；LLM 是核心耗时/耗资操作却无追踪 |
| 5 | **Loop 无 mid-run compaction** | 效率问题：仅在 overflow error 时压缩，不提前；浪费 token |
| 6 | **KnowledgeBase.retrieve 全量扫描** | 性能隐患：每次查询加载所有 chunk embedding；文档量大时延迟不可接受（但当前文档量可能不大，优先级可降低） |
| 7 | **MemoryExtension 存原始消息而非用户画像** | MemoryExtension 定位是用户画像/RAG，但当前实现存的是原始用户消息文本（"帮我写个函数..."），未提取用户偏好/习惯/背景等画像事实。应改为 LLM 提取用户画像后存储 |

### 修正后的优先级

```
真正需要做的（6项）：
  P0: #2 Skill Evolution 预算 bug 修复（5分钟）
  P0: #3 Validation Gate 中文分词（引入 jieba 或字符 n-gram）
  P1: #4 Observability LLM 调用追踪集成
  P1: #5 Loop mid-run compaction
  P1: #7 MemoryExtension 改为提取用户画像而非存原始消息
  P2: #6 KnowledgeBase.retrieve 预加载索引（视文档量而定）

其余 27 项全部删除，不实施。
```

**教训**：
1. 分析时应先 grep 确认实际调用方和需求量，再判断是否是问题。"可能有用"不是优化的理由。
2. 理解一个模块的定位（做什么）比看它"缺什么"更重要。MemoryExtension 是用户画像系统，不是对话消息的副本存储。
