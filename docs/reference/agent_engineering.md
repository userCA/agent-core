# Agent 工程演进：从 Prompt 到 Agent OS

> **用途**：企业级 AI Agent 平台工程实践的系统回顾与优化指引。  
> **主线**：大模型先天约束 → Prompt 工程 → Context 工程 → Harness 工程 → Agent OS 五层架构。  
> **核心隐喻**：大模型是「裸 CPU」；工程化是为其补齐操作系统子系统。  
> **声明**：基于作者个人技术实践与独立思考，仅代表个人观点。

---

## 如何使用本文档

| 场景 | 跳转 |
|------|------|
| Agent 长链路质量下降 | [1.2 注意力稀释](#12-注意力稀释效应) → [三、Context 工程](#三context-工程阶段管好上下文就管好了一半) |
| 跨步骤数据丢失 / ID 幻觉 | [1.3 数据搬运谬误](#13-数据搬运谬误) → [4.1 parameterBindings](#41-设计哲学从防御到赋能) |
| 上下文膨胀 / Token 飙升 | [3.2 四层防线](#32-四层上下文防线按时间顺序逐层拦截) |
| 进程崩溃 / 断点恢复 | [4.2 有状态执行与断点续传](#有状态执行引擎与断点续传) |
| 防御管道过重、想减负 | [4.1 从防御到赋能](#41-设计哲学从防御到赋能) |
| 多 Agent / 组织级治理 | [五、Agent OS](#五宏观架构全景从-agent-到-agent-os) |
| 设计决策 checklist | [六、核心洞察](#六核心洞察与优化 checklist) |

**演进铁律**：每一层的出现都是因为前一层遇到了天花板；好的分层应为下一阶段铺路。

```
Prompt 工程          Context 工程           Harness 工程            Agent OS
(文本引导)    →    (内存管理)      →     (进程/文件/IPC)    →    (完整 OS)
天花板:              天花板:               天花板:                 当前目标
遵从率↓/无容错       跨执行无知识积累       单体无法承载组织任务
```

---

## 一、大模型的先天约束——为什么需要工程化

四个结构性约束不会因模型变大而消失。所有工程努力都在这四面墙内做文章。

### 1.1 上下文窗口是稀缺资源

- 物理上限（如 128K）在 ReAct 下极易打满：每步 ≥3 条消息；5 步技能 × 每步 3 轮 ≈ 45+ 条；工具 JSON 动辄数万字符。
- **不能靠简单截断**，四个原因：
  1. 截断 JSON 是残废数据，无法 parse / 无法提取。
  2. OpenAI 协议要求 `tool` 紧跟对应 `assistant.tool_calls`，破坏配对会 API 报错。
  3. 即使未溢出，20+ 轮后早期关键发现被注意力稀释（「遗忘」）。
  4. 压缩数据不能真丢——审计、回放、追溯需要原文。

**工程结论**：需要完整的**信息生命周期管理**（产生 → 压缩 → 索引 → 按需恢复），而非截断。

### 1.2 注意力稀释效应

**现象**：同一 Skill，3 步质量好 → 8 步明显下降 → 15 步几乎不可用。换更大模型改善有限。

**根因（上下文 dump）**：到第 8 步时约 70% 为工具原始返回（噪音）、20% 历史对话、仅 10% 为当前有用指令/变量。

**关键区分**：

| 概念 | 含义 |
|------|------|
| 物理容量 | 窗口 token 上限（如 128K） |
| 有效容量 | 被噪音稀释后真正可用于推理的信息密度 |

**自我恶化循环**（S1 无制动）：

```
上下文膨胀 → 注意力稀释 → 工具参数错误↑ → 无效重试消息↑ → 上下文进一步膨胀
```

**优化指引**：不要用更大模型掩盖工程问题。32K→128K 只是把衰减从第 5 步推迟到第 8 步。**管理信息质量，而非扩大物理容量。**

### 1.3 数据搬运谬误

多步骤中，模型从步骤 A 工具返回「搬运」数据到步骤 B 参数，典型失败：

- 长数组被「摘要」成 3–5 个代表性元素（精确执行场景 = 数据丢失）
- UUID/`refId` 截断、混淆、压缩后幻觉
- 浪费 token + 错误率上升 → 再喂回注意力稀释循环

**反模式**：自动模式下仍暴露 `input`（required）给 LLM，等于让模型当数据搬运工。

**核心原则（后续设计哲学基石）**：

> 让 LLM 做擅长的事（意图、规划、推理）；让系统做擅长的事（数据搬运、格式转换、精确传递）。

落地形态：`parameterBindings` 声明式绑定——把数据搬运从 LLM 职责中彻底移除。

### 1.4 无状态的先天缺陷

| 层面 | 问题 |
|------|------|
| 单次执行内 | 中间状态全靠上下文；进程崩溃/重启即清零（只有「内存」无「硬盘」） |
| 跨执行 | 无法从历史教训学习；昨天踩坑今天重犯；架构决策不显式记录会在新会话矛盾重演 |

**总论**：原始大模型是高性能 CPU，缺内存管理、文件系统、进程调度。企业级稳定执行需要外围「操作系统」级基础设施——这是 Prompt → Harness 演进的动因。

---

## 二、Prompt 工程阶段——一切从一段文本开始

### 2.1 从角色扮演到结构化注入

演进路径：短 System Prompt → 膨胀数千字 → 持久化项目上下文文档（如 `CLAUDE.md`：500+ 行、结构化章节）。

**价值**：结构化（表格/映射/规则）提高上下文利用；「上下文推断规则」可做轻量 RAG（关键词触发 → 知识入口，无需向量）。

**上限**：全量注入占 15K–20K token，无论是否相关 → 催生后续「渐进式披露」与「按需检索」。

### 2.2 Prompt Hack 的标语困境

在 tool description 中堆 `⚠️` / 格式规则 ≈ 车间安全标语：正确但脆弱。

| 链路长度 | 指令遵从率（经验） |
|----------|-------------------|
| ~3 步 | ~95% |
| 10+ 步 | <70% |

真正安全来自**消除危险条件**（机械互锁），而非警告危险存在。

### 2.3 Attention 引导的局限

技巧（emoji、IMPORTANT、primacy/recency、逐步重复注入）在短对话有效，长链路不可靠。

本质：注意力是有限资源；上下文 10K→100K 时，单个强调标记权重被稀释约 10 倍。用更多 token 对抗 token 太多 = 火上浇油。

**出路**：系统强制执行规则，而非指望模型记住规则。

### 2.4 S1（MVP）三个结构性缺陷

架构概括：**工作流编排 + 单轮对话**（无 Agent / Skill / ReAct）。业务上验证了方向（如活动效率 +50%），但缺陷是架构必然后果，只能重建：

1. **无容错**：纯内存 while；无事件溯源/检查点；失败只能全量重跑；SSE 断开后结果无处推送。
2. **上下文气球爆炸**：工具结果全量入上下文；无制动的「越跑越蠢」循环。
3. **单向管道无反思**：错误在链路中放大，产出「形式完成、逻辑不一致」。

**根因**：把 AI 当一次性脚本执行器，而非有状态、能反思、能管理自身资源的运行时。Prompt 工程到此触顶 → S2 从零重建。

---

## 三、Context 工程阶段——管好上下文就管好了一半

### 3.1 核心判断

上下文管理是 **Agent 工程化的第一命题**，且是**分层防御的系统工程**（无银弹）。

关键输入：

| 来源 | 启发 |
|------|------|
| 原始 ReAct | 隐含「上下文无限」；demo 仅 3–5 步；10+ 步即退化 |
| Claude Code | Compaction（交接文档替换对话）；Progressive Disclosure（难在 Action Space） |
| Codex | 大结果外置 + refId 按需取回 |

目标量级：128K 窗口内稳定 30+ 步、数十次工具调用。

### 3.2 四层上下文防线（按数据膨胀时间顺序拦截）

```
工具返回瞬间 → L1 外置引用 → L2 语义压缩 → 消息累积 → L3 Compaction → 按需 → L4 DataBus
```

#### L1 — ToolResultRefStore（拦截单次大数据）

触发：字符 >8000 / 数组元素 >10 / `alwaysStore`（绑定场景保完整性）。

消息中只留引用对象（`__stored` / `__refId` / `__summary` / `__hint`）；大结果存外部（如 MySQL）。

- 数组 >10 强制外置：消除 LLM「摘要式搬运」导致的数据丢失。
- `preview`（如前 12000 字符）**永不入 LLM prompt**，仅审计/调试/回放（单一表示原则）。

#### L2 — SemanticCompressor（压缩中等数据）

- 单条 >10000 字符 → 另一 LLM（建议 temperature=0.3，超时约 60s）蒸馏至 ≤2000 字符。
- 原始保留（TTL 如 1h），可经 DataBus 取回。
- 降级：LLM 失败 → 结构化截断（前 3000 + JSON 包装 + `__fallbackTruncated`），勿裸截断。

**踩坑**：勿让 LLM 重写 preview——会改字段名/前缀，破坏前缀匹配恢复，导致腐败数据流入下游。preview 用原始 `substring`。**数据管道中：确定性 > 智能性。**

#### L3 — Compaction（压缩累积膨胀）

- 触发：`prompt_tokens / contextWindow >= 85%`；目标压到 ~30%（留缓冲：压缩有延迟，期间消息仍在涨；95% 易无输出空间）。
- 产物：结构化交接文档（非自由叙述），建议字段：
  1. 用户原始请求（防忘初心）
  2. 按阶段分组的执行历史（保留具体值/ID/名称，禁止空泛概括）
  3. 已放弃路径（防重蹈覆辙）
  4. 数据引用索引（所有 `__stored` refId）
- 分割约束：不能从 `tool` 消息起切；向前回溯到配对 `assistant`；最少保留 6 条、最少删除 2 条。

#### L4 — DataBus（压缩后按需取回）

- System prompt 维护全局数据索引；按 `step.input` / `{{variable}}` 做依赖分析预取。
- 小数据（≤4096）全文注入；大数据生成增强摘要（保留结构，≤1000）。
- 超预算降级顺序（越接近当前任务核心越晚牺牲）：  
  `丢 preview → full → summary → 去掉非直接依赖 → 收缩 transcript → 收缩 working memory`
- Inspect 工具链（轻量替代整块 `get_stored_data`）：  
  `artifact_ref → 索引 → outline/search → context → 结论`（每次取最小必要信息）

### 3.3 单一表示原则（宪法条款）

同一上游数据在任一后续 step 的 LLM 上下文中，**只允许一种表示形态**。

禁止同 step 共存：full+summary、summary+preview、full+tool_result preview、full+tool_results+assistant narration 等。

| 数据规模 | 唯一合法形态 |
|----------|--------------|
| <8000 字符 | 完整结构化对象（inline） |
| >8000 字符 | `artifact_ref`（refId + 有界摘要 + 元数据） |

实现建议：PromptBuilder **组装前检查**——同 refId 多形态则拒绝组装并告警（编译时约束，非运行时祈祷）。

### 3.4 三层记忆（横切：跨步骤必须存活的信息）

与四层防线正交：防线负责「减少」，记忆负责「保留」。

| 层 | 职责 | 要点 |
|----|------|------|
| **State** | 跨步 KV | 确定性通道；A 写入 / B 读取；`parameterBindings` 底座；无 LLM 搬运损耗 |
| **Working Memory** | Pinned + Insights | Pinned：目标+计划，紧贴 system prompt，抗目标漂移；Insights：滚动关键发现，尾部逆序，可经 `working_memory` 主动写入 |
| **Transcript** | 最近 N 条消息 | N 随步数自适应收缩 |

动态再分配示例：

```
keepTarget     = round(36 - steps × 0.8)          # 步越多 transcript 越少
insightsTarget = round(steps × 1.2 + complexity × 4)
charsTarget    = round(2000 + steps × 200 + complexity × 1000)
```

类比：不记得上周三每句对话（Transcript 压缩），但记得当天定了方案 B（Insight 保留）。

### 3.5 Prompt 预算预检（事前治理）

调用前估算；超预算按固定顺序降级；仍超限 → `PROMPT_BUDGET_EXCEEDED`（失败优于硬跑劣质推理）。

触发时机：每步迭代前 + 最终输出前。估算系数可粗（如 ~350 token/条），精确数以 API usage 为准。

### 3.6 效果与哲学（Context 阶段）

经验效果：Token ↓60%+；从「8 步衰减、15 步不可用」→「30+ 步稳定」。

| 哲学 | 含义 |
|------|------|
| 分层拦截优于全能方案 | 各层单一职责，覆盖不同粒度膨胀 |
| 确定性优于智能性 | 管道用 substring/声明式；智能留给真正需理解的环节 |
| 事前治理优于事后修复 | 预算预检、单一表示、强制存储阈值 |

Context 管住「信息质量」后，仍需容错、断点、治理 → Harness。

---

## 四、Harness 工程阶段——完整的 Agent 运行时

Context ≈ 内存管理；Harness ≈ 完整 OS（调度、文件系统、IPC、安全、进化）。

### 4.1 设计哲学：从防御到赋能

根本问题：你信任你的模型吗？（类比 McGregor X/Y 理论）

#### 防御范式的代价

典型五层修复管道（约 500 行，可占 ToolExecutor 近半）：

```
restoreTruncatedArgs → injectContextData → parameterBindings
  → autoRestoreFromStoredObjects → normalizeParameters
```

代价：维护成本 > 核心逻辑；「以防万一」的 DB 访问性能税；**进化阻力**——模型变强后管道不会自动变轻。过度警觉掩盖根本设计问题。

#### 赋能范式对照

| 防御 | 赋能 | 隐喻 |
|------|------|------|
| 多层修复管道 | `parameterBindings` 声明式绑定 | 惩罚工人 vs 改生产线（Deming） |
| 猜纯文本含义 | `step_control`（complete/skip/need_info） | 猜想法 vs 建沟通机制 |
| 系统替记笔记 | `working_memory` 模型自主记录 | 替做笔记 vs 给笔记本 |
| 全量暴露工具 | Action Space 动态裁剪 | 考验自制力 vs 优化环境（Nudge） |

**迁移三阶段**（先减犯错机会，再增做对能力）：

1. 可观测性先行（哪些修复层触发最多？哪些工具错误率最高？）
2. 声明式绑定替代命令式修复（优先高频场景）
3. 再引入 `step_control` / `working_memory` 等自主性工具

**结论**：信任是设计能力，不是态度。最好的控制看起来像自由。

### 4.2 Agent 运行时引擎

#### PERO 编排

`Plan → Execute → Reflect → Optimize`

- Plan：Skill `planDefinition` 预定义（步骤、工具、参数映射）
- Execute：每步 ReAct（Thought → Action → Observation）
- Reflect/Optimize：ReAct 内禀，非外挂独立环节

**为何不用 Tree-of-Thought**：工具密集型、外部结果不可预测；分支真实调用成本过高。单路径 ReAct + 每步自然反思更合适。

#### 单步 ReAct 微循环

| LLM 响应 | 行为 |
|----------|------|
| `tool_calls` | 执行工具 → Observation → 继续 |
| `content` | 步骤完成 → 写 State → 下一步 |
| 无有效响应 | 注入错误提示重试 |

硬约束：Prompt 预算预检；stalled watchdog（超时 → `LLM_STALLED`）。输出校验采用迭代式 prompt refinement（注入错误、限次重试），让模型自纠而非系统偷偷修。

#### 有状态执行引擎与断点续传

**原则：执行与推送分离**

- BackgroundExecutor 独立跑；事件写入 DB（`streamEvents`）
- **SSE 事件流 = 执行状态唯一真相源**（前端思维链、断点续传、审计同源）
- SSE 只负责转发；断开不影响执行；重连后 poll 增量
- 缓冲 flush（如每 500ms 或 10 条）；关键节点 checkpoint（LLM/工具完成后）
- 恢复：优先 KV 快照，兜底事件溯源（可到 step 级）

效果示例：15 步任务第 12 步失败——全量重跑 ~6min → 断点恢复 ~30s。

#### 步骤并行化（Fan-out / Fan-in）

- `parallel: ParallelTask[]`；`allSettled` + Semaphore（默认并发如 3）
- 错误隔离：子任务失败标 `__error` 交下游 LLM 判断
- **配置驱动并行**（非 LLM 自主 spawn）——适合结构化业务流程

**规范**：仅「输入完全确定、互不引用」可并行；任何数据依赖必须串行（含隐含依赖，如 executionId）。

#### 可靠性防护体系（改造生产线，非教育模型）

- 最大迭代（全局 + 单步）
- 重复工具调用检测
- 工具调用分 chunk（避并发超时）
- **RecursionGuard**：深度（如 MAX_DEPTH=5）/ 链路（MAX_CHAIN=20）/ 环（同 skillId ≥3）三重硬拦截
- 取消（executionId）
- 敏感字段脱敏
- 单一表示检查

### 4.3 知识体系（跨执行积累）

单次执行内记忆见 §3.4；本节管多次执行、多用户、多场景的持久知识。

#### 四层记忆（稳定性↓ / 时效性↑）

| 层 | 对应问题 | 特点 |
|----|----------|------|
| behavior/ | 怎么做 | 踩坑、决策、规范；最稳；跨项目 |
| knowledge/ | 知道什么 | 业务事实、技术经验；按域版本管理 |
| personal/ | 给谁说 | 偏好、关注点、认知模型 |
| working/ | 正在做什么 | 当前目标/计划；最短暂 |

#### 行为记忆三层与冲突裁决

`Policy`（硬规则，可覆盖用户指令，须人审）> `Strategy`（执行偏好，可自动优化）> `Action Chain`（高频可复用链路）

裁决顺序：

```
平台协议 > Active Policy > 当前用户指令 > Active Strategy > Retrieved Action Chain
```

Policy ≈ 宪法层：合规/安全/口径不可被单次指令覆盖。

#### Prompt Compiler

编译对象是**结构化行为记忆资产**（非裸 Prompt 文本）。Patch 带适用范围、置信度、试用命中率、成功率，可独立创建/验证/生效/过期。

#### 个人记忆三层

1. 交互偏好（怎么用）→ 响应格式  
2. 关注点画像（关心什么，权重+时间衰减）→ 召回权重  
3. 认知模型（怎么思考）→ 解释深度与论证结构  

画像从交互涌现，不预设角色标签（角色 ≠ 关注点）。

### 4.4 进化体系

#### 自进化认知闭环（任务结束后三问）

1. 学到新东西了吗？  
2. 犯过什么错？  
3. 知识体系有过时内容吗？  

路由到 behavior / decisions / knowledge 等；**有监督写入**：不记临时状态、不存代码 diff 原文、不确定不猜写。

#### Self-Feedback Engine 五组件

`Trace Collector → Outcome Evaluator → Root Cause Analyzer → Patch Generator → Safety Gate`

- 结果归一：correct / incorrect / partial / harmful  
- 归因层级：policy / strategy / chain / execution  
- Patch 状态机：`draft → shadow → active → expired`  
- Strategy/Chain 可自动 shadow→active；**Policy 必须人工审核**  
- 低成功率策略自动 expired

#### 三条闭环成熟度

| 闭环 | 状态 | 路径 |
|------|------|------|
| 执行闭环 | 已闭合 | L4 下发 → L2 执行 → L1 落地 → 回流 L5/L3 |
| 学习闭环 | 成型中 | Shadow 轨迹 → 学习引擎 → Patch → L3 |
| 治理闭环 | 推进中 | 训练/评测/认证 → 发布到 L1 |

### 4.5 运行时扩展能力

#### Capability Runtime（Skill-first → Capability-first）

- Agent 持有 `capabilityConfig`；kind 含 skill / builtin_tool / service_tool / workflow_tool / mcp_tool / tool_pack 等
- 统一解析 → 统一 `ToolDefinition` → 统一路由
- 原则：Agent-first；Tool-first Execution；Artifact-first

#### 多 Agent 协调

树形：CEO 级 → 主管级 → 执行 Agent（深度上限如 5）

`SiliconEmployeeRunner`：Plan → Dispatch（sequential/parallel/adaptive）→ Reflect → Synthesize

跨 Agent：`SharedBlackboard`（read/write/subscribe），注入「协作上下文」。

#### 四层嵌套循环（外层一动 = 内层完整生命周期）

| 层 | 循环 | 解决的问题 | 时间尺度 |
|----|------|------------|----------|
| 微循环 | ReAct | 下一步做什么 | 秒 |
| 步骤循环 | PERO | 本步目标是否达成 | 分钟 |
| 任务循环 | Silicon Employee | 拆解/调度/修正 | 分钟–小时 |
| 组织循环 | OODA | 该关注什么、做什么 | 小时–天 |

---

## 五、宏观架构全景——从 Agent 到 Agent OS

### 5.1 Agent OS 五层架构

不再是「更强的 Agent」，而是认知操作系统。

| 层 | 解决的问题 | 关键组件 |
|----|------------|----------|
| **L1 执行集群** | 任务如何落到真实节点 | Control Plane / Bridge / Gateway / Slot 池；Slot **无状态**，状态在 L2 账本 |
| **L2 Agent Runtime** | 可控、可恢复、可审计执行 | 对话引擎 / ReAct / PERO / Execution Ledger / SSE / 断点；对话↔任务模式自适应 |
| **L3 记忆与语义** | 越用越懂人/业务 | 三层记忆 + DataProductStore（语义检索产物） |
| **L4 认知层** | 感知？判断？调度谁？怎么评？ | Sensor / Reasoner / Silicon Employee；**注意力经济**（优先级队列） |
| **L5 进化与治理** | 如何安全变更好？如何反哺？ | 训练→评测→认证→发布→值班→告警→Patch→回流 |

**一等对象**：`execution request` / `workflow context` / `planDefinition` / `execution ledger` / `governance contract`  
——不是 workspace / terminal / tool list。做的是**业务执行范式工程化**，不是通用 Agent 工具云化。

### 5.2 双平台：云端 Agent OS × OpenClaw

**原则**：思考与执行分离；混编互相拖累。

| | Agent OS | OpenClaw |
|--|----------|----------|
| 持有真相 | 认知（知识、规则、标准） | 执行（在岗、任务单、Slot） |
| 职责 | 想清楚 | 做到位 |
| 铁律 | 不改运行中 Slot 状态 | 不改组织知识真相 |

Contract Layer：`TaskOrder` / `StatusReport` / `EvidencePackage` / `SlotAllocation`

价值：认知核与执行环境可独立演化。

治理链路（节选）：

```
Knowledge → Pack → Skill Bundle → Eval → Certification → Release
  → OnDuty → TaskOrder → Execution → Alert/Remediation → Learning → 采纳
```

Agent 发布状态机示例：`candidate → shadow → probation → active → degraded → retrain → offboard`

### 5.3 与 Claude Code 类产品的本质差异

| 维度 | 企业执行系统 | Claude Code 类 |
|------|--------------|----------------|
| 一等对象 | 结构化执行请求、编排、审计计费 | workspace / session / tools / subagents |
| 数据流转 | 显式绑定 / path / materialization | 模型记忆 |
| 知识定位 | 强规则执行面（可拒绝执行） | 参考建议（可被忽略） |
| 容错 | 必须内建于系统 | 人类开发者兜底 |

总结：个人开发者提效 vs 组织将业务流程可靠委托给 AI。

### 5.4 五层认知模型（工具型 → 认知型）

| 层 | 职责 | 关键设计 |
|----|------|----------|
| L1 语义 | 统一数据语言 | MetricRegistry（口径/版本）；上层地基 |
| L2 感知 | 正确触发与降噪 | cron/事件/阈值；阈值判断用代码非 LLM；合并去重 |
| L3 推理 | 统计先行，LLM 解读 | 统计归因 → 叙述 → 置信度标签；可信度骨架由统计保证 |
| L4 决策 | CEO 做选择题 | 2–3 方案决策卡 + ApprovalGateway（严格/阈值/事后追认） |
| L5 元认知 | 知道自己不知道 | 注意力控制 / 置信校准 / 能力盲区→新 Skill |

演进：V1 会做事 → V2 知道对不对 → V3 知道还要学什么。

---

## 六、核心洞察与优化 Checklist

### 6.1 五条反复验证的认知

1. **「LLM 越跑越蠢」是工程问题** —— 先查上下文信噪比，再考虑换模型。  
2. **上下文管理是分层防御** —— L1–L4 各管一段，无银弹。  
3. **Action Space 必须被治理** —— 工具从 5→50 是选择困难↑，不是能力×10；渐进式披露。  
4. **工具设计有半衰期** —— 模型变强后旧防御可能变包袱；可观测性先行才能减负。  
5. **信任不能跳过人工确认** —— 95% 准确率下 5% 写库即可摧毁信任；shadow/probation、分级审批。

### 6.2 演进主线速查

| 阶段 | 围绕 | OS 类比 | 核心贡献 | 天花板 |
|------|------|---------|----------|--------|
| Prompt | 一段文本 | 裸机编程 | 验证方向 | 长链路遵从率↓、无容错 |
| Context | 信息管理 | 内存管理 | 30+ 步不退化、Token↓60%+ | 跨执行无积累、难自改进 |
| Harness | 完整生命周期 | 进程+文件+IPC | 健壮运行时 | 单体难承载组织任务 |
| Agent OS | 认知操作系统 | 完整 OS | 五层+双平台+闭环 | 建设中 |

### 6.3 优化决策 Checklist（实操）

做任何 Agent 优化前，按序自问：

- [ ] **现象是模型能力还是上下文质量？**（先 dump 信噪比）
- [ ] **是否在让 LLM 做数据搬运？** → 声明式绑定 / State
- [ ] **膨胀发生在哪一层？** 单次大结果 / 中等文本 / 累积消息 / 压缩后取回缺失
- [ ] **是否违反单一表示？** 同数据多种形态是否进了同一 step
- [ ] **是否可用确定性逻辑替代 LLM？**（阈值、格式、搬运、校验）
- [ ] **防御层是否仍有触发数据支撑？** 无数据不减负、也不加层
- [ ] **失败能否断点恢复？** 状态是否在事件账本而非进程内存
- [ ] **新工具是否扩大了无治理的 Action Space？**
- [ ] **知识是建议还是可强制执行的规则？** 企业场景需要后者
- [ ] **变更是否走治理门控？** Policy 人审；Strategy 可灰度

### 6.4 设计原则速记

```
分层拦截 > 全能银弹
确定性 > 管道中的智能
事前治理 > 事后修复
赋能（消除错误条件）> 防御（修补错误后果）
系统强制执行 > Prompt 标语警告
信息生命周期管理 > 简单截断
有效容量 > 物理容量
```

---

## 附录：关键术语索引

| 术语 | 要点 |
|------|------|
| 有效容量 | 扣除噪音后的真实推理容量 |
| 数据搬运谬误 | LLM 跨步传参导致截断/幻觉/丢失 |
| 单一表示原则 | 同数据在同 step 仅一种形态 |
| parameterBindings | 声明式跨步数据注入，移除 LLM 搬运 |
| PERO | Plan-Execute-Reflect-Optimize |
| Compaction | 用量触发的结构化对话交接压缩 |
| DataBus | 压缩后依赖分析与按需预取 |
| RecursionGuard | 嵌套 Skill 深度/链路/环硬拦截 |
| Capability Runtime | 统一能力单元，非仅 Skill |
| SharedBlackboard | 同 rootExecution 跨 Agent 共享状态 |
| Contract Layer | 认知平台与执行平台的外交协议 |
| Policy / Strategy / Action Chain | 行为记忆三层及裁决优先级 |
