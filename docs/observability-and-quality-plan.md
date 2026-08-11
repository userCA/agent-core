# Agent 可观测性与质量把控计划

> 状态：**轨 A 已完成**（2026-07-29 实施）；**轨 B 阶段 1 已实施**（2026-08-11，OTLP 采数）；**阶段 2 待定**（Score/Dataset/反馈）  
> 目的：指导后续优化——解决「调试看不清」与「线上 prompt/质量没法评」双痛点，并约束 AI 加速开发下的质量闸门。  
> 相关：`agent_core/observability.py`、`docs/design.md` §9 观察性、`docs/agent-framework-optimization-plan-phase2.md` §5、`docs/reference/agent_protocol.md` §9  
> **轨 B 实施规格**：`docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md`（两阶段：OTLP 采数 → Score/Dataset）  
> **轨 B 阶段 1 实施计划**：`docs/superpowers/plans/2026-08-11-langfuse-otlp-phase1.md`

---

## 1. 背景与问题

当前 AI 辅助开发速度快，但存在两类并存的质量风险：

| 痛点 | 表现 | 后果 |
|------|------|------|
| **调试看不清** | 一次失败聊天难以定位第几 turn、哪个 tool/LLM；因果链靠猜 | 无法自主调试，过度依赖 AI「帮你查」 |
| **线上质量没法评** | 差回复无法归档打分；prompt 改动缺少对照实验 | 质量靠感觉，回归不可验证 |

同时存在过程风险：

- 测试为通过率定制（改断言迎合实现、mock 掉整条关键路径）
- 大 diff 合并时人无法理解项目，心智模型落后于代码

**结论**：速度可以交给 AI，合并与验收标准必须由人把控；观测与评测要共用同一条数据血脉，不能做成两套互不相干的埋点。

---

## 2. 总策略：一条因果链，两个出口

```
AgentEvent（已有）
    ↓ 统一补齐身份与度量字段
run_id / session_id / turn / llm / tool / usage / system_prompt_hash
    ↓
出口 A：本地调试（结构化日志 + OTEL console/Jaeger）
出口 B：线上评测（Langfuse 等，挂在 scene 层，可选）
```

### 2.1 架构边界（硬约束）

| 层级 | 职责 | 禁止 |
|------|------|------|
| `agent_core` | 产出标准化事件 / OTEL span；保持观测可选（无 SDK 也不应崩溃） | 绑定 Langfuse 或其他 SaaS SDK 为硬依赖 |
| `scene/`（如 `http_sse`） | 组装 exporter、可选接入 Langfuse、暴露反馈 API | 把厂商语义泄漏回 core API |
| 人 | 定义成功标准、跑真实路径验收、审查 diff | 只看 CI 绿就合并 |

设计依据：`docs/design.md` 已规划 OpenTelemetry；协议文档明确反对 Tracing 与单一厂商框架绑死。Langfuse 支持 OTEL 接入时，应走 **先标准 span，后选 UI**。

### 2.2 与「现在是否该上 Langfuse」的结论

- **短期**：不把 Langfuse 绑进 `agent_core`。先接好事件身份字段 + OTEL（尤其 `trace_llm_call` 零调用方缺口）。
- **中期**：在 scene 可选集成 Langfuse，解决打分、数据集、prompt 版本对比。
- **判断标准**：本地不打开任何云面板，也能在 5 分钟内讲清一次失败 run 的因果链；云面板只负责质量闭环，不替代调试能力。

---

## 3. 轨 A — 调试看清（优先）

**目标**：一次真实聊天后，能在终端回答「卡在哪一轮、哪个 tool、哪次 LLM」。

### 3.1 现状缺口

- `agent_core/observability.py` 已有 `observe()` / `trace_llm_call()`，但：
  - `observe()` 主要覆盖 tool hook
  - `trace_llm_call()` **无调用方**（见 Phase2 §5.1）
  - 缺稳定的 run 级 span 与统一 `run_id` 贯穿日志
- `AgentEvent` 事件模型已较完整（`turn_start/end`、`message_*`、`tool_execution_*` 等），缺的是**可关联的身份字段与落盘**

### 3.2 任务清单

| ID | 任务 | 建议落点 | 验证 |
|----|------|----------|------|
| **A1** | 在 LLM stream 调用处接入 `trace_llm_call`；补 run/turn 级 span | `agent_core/core/loop.py` 的 `_stream_assistant`；agent loop 入口/出口 | 一次 `prompt` 可见 llm + tool 父子 span |
| **A2** | 结构化日志：关键事件带 `session_id` / `run_id` / `turn`；LLM 记录 model、latency、usage | `logging_config` + loop / harness / scene 订阅处 | `grep run_id=xxx` 能串起整条链 |
| **A3** | scene「调试回放」：一次 run 的事件摘要落本地 JSON（可不含完整 token 流） | `scene/http_sse/` | 复现 bug 时打开一份文件即可讲故事 |
| **A4** | 本地 OTEL → Console 或 Jaeger（可选依赖） | scene 启动配置 | 不依赖云产品也能看 span |

### 3.3 成功标准（轨 A）

任意一次失败聊天，**不打开 Langfuse**，能在约 5 分钟内指出：失败发生在第几 turn、哪个 tool 或哪次 LLM，并指出对应日志/回放文件。

---

## 4. 轨 B — 线上 prompt / 质量可评

**目标**：坏 case 可归档、可打分、可对比不同 prompt。

### 4.1 任务清单

| ID | 任务 | 建议落点 | 验证 |
|----|------|----------|------|
| **B1** | scene 可选集成 Langfuse：一次 user turn = 一条 Trace；子 span = LLM / Tool；与本地共用 `run_id` | `scene/http_sse/`（环境变量开关） | UI 中能看到与本地日志同 `run_id` 的树 |
| **B2** | 上报：最终回复摘要、tool 名/成败、usage、**system_prompt hash + 版本标签**（默认不全量 dump 隐私内容） | scene 组装层 | 可按 prompt 版本筛选 |
| **B3** | 反馈 API / 前端：👍/👎 或短原因 → Score | HTTP API + H5/桌面轻量入口 | 坏 case 可检索 |
| **B4** | 从 Score 定期抽样坏 case → 固定评测集；改 prompt 后回放对比 | 流程 + 可选脚本 | 质量改进有对照，不是感觉 |

### 4.2 成功标准（轨 B）

任意一次线上差评，能在评测 UI 中找到同 `run_id`，并归入坏 case 集；改 prompt 后至少能跑一轮有对照的对比。

### 4.3 隐私与成本注意

- 默认记录 hash / 元数据 / 截断摘要；全量 prompt/响应需显式开关
- Langfuse 与 OTEL exporter 均可关闭，本地开发默认走轨 A 即可

---

## 5. 实施顺序（禁止并行大干）

```
阶段 1（优先）：A1 + A2
  → 本地已经「看得清」

阶段 2：A3 + B1（最小 Langfuse）
  → 同一 run_id 两端对齐

阶段 3（按需）：B2 → B3 → B4
  → 打分、数据集、prompt 实验闭环
```

### 刻意不做

- 不把 Langfuse 写进 `agent_core` 硬依赖
- 不先上完整评测平台再补埋点
- 不为了面板或通过率去改测试迎合实现
- 不在无 `run_id` 统一语义前同时接多家观测 SaaS

---

## 6. 质量闸门（AI 加速开发下的人控）

与观测并行，合并前执行：

### 6.1 三闸门

| 闸门 | 问题 | 不通过则 |
|------|------|----------|
| **意图** | 成功标准是什么？（1–3 条可观察行为） | 不让动手 |
| **边界** | 改哪些文件？有没有顺手「优化」？ | 打回 |
| **验收** | 能否用 1 条真实路径亲手验证？ | 不合并 |

### 6.2 Diff 审查三问

1. 每行变更是否对应用户需求？
2. 有没有为了绿测放宽/改写断言？
3. 有没有自己调试不了的黑盒？

### 6.3 测试贴近真实链路

**假测试特征**：只断言内部私有状态；mock 掉整条关键路径；先实现后写「刚好能过」的断言；故意 skip/放宽。

**真链路原则**：

1. 先写用户故事级行为（事件序列 / HTTP 契约），再实现
2. 修 bug：先红后绿；故意弄坏实现时测试必须变红
3. `FakeProvider` 可脚本化 LLM（不可控侧），但工具执行、队列、持久化尽量走真逻辑
4. 至少一条主路径必须人手过（H5 发消息 / 中断 / 切会话），不能只靠 CI

仓库既有规则（必须遵守）：测试失败追溯实现，不得伪造或修改用例迎合代码。

### 6.4 日常节奏

```
需求 → 人写清成功标准
     → AI 小范围实现
     → 人跑真实路径 + Diff 三问
     → 行为级测试（先红后绿）
     → 能口述数据流再合并
     → 收尾：development-log / mistake-log / 必要时沉淀 skill
```

---

## 7. 最小数据模型（跨 A/B 共用）

一次 Run 至少应能关联：

| 字段 | 含义 |
|------|------|
| `session_id` | 会话 |
| `run_id` | 一次用户 turn / prompt 的端到端执行 |
| `turn_index` | agent loop 内轮次 |
| `span` 类型 | `run` / `turn` / `llm_call` / `tool_call` |
| `model` / `provider` | LLM 身份 |
| `usage` | input/output（及 cache，若有）tokens |
| `tool.name` / `tool.call_id` / `is_error` | 工具因果 |
| `system_prompt_hash` / `prompt_version` | 评测对照（轨 B） |
| `latency_ms` | 各 span 耗时 |

事件流（实时 UI）、Trace（事后因果）、State/回放文件（调试）三者应能通过 `run_id` 互跳。

---

## 8. 验收总表

| # | 标准 | 对应 |
|---|------|------|
| 1 | 失败聊天 5 分钟内定位 turn/tool/LLM，且不依赖云面板 | 轨 A |
| 2 | 差评可找到同 `run_id` 并进入坏 case 集；prompt 改动可对照回放 | 轨 B |
| 3 | 集成测试断言用户可观察行为；禁止为通过率改测试 | §6.3 |
| 4 | 合并前能口述：入口 → loop → provider → tool → store → SSE | §6 |

---

## 9. 参考索引

| 资源 | 说明 |
|------|------|
| `agent_core/observability.py` | 现有 OTEL `observe` / `trace_llm_call`（部分未接线） |
| `agent_core/core/events.py` | AgentEvent 区分联合类型 |
| `agent_core/core/loop.py` | `_stream_assistant` — A1 首选接入点 |
| `scene/http_sse/` | SSE scene；B1–B3 与 A3 落点 |
| `docs/design.md` | 观察性路线：OTEL + structured logs |
| `docs/agent-framework-optimization-plan-phase2.md` §5 | Observability 缺口（LLM 未追踪、usage 未聚合） |
| `docs/reference/agent_protocol.md` §9 | Trace/Event/State 三类观测与评测关系 |
| `docs/mistake-log.md` | 踩坑沉淀 |
| `CLAUDE.md` 编码规范 | 测试质量、目标驱动、精准变更 |

---

## 10. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-29 | 初版：双痛点双轨计划、架构边界、质量闸门、实施顺序与验收标准 |
| 2026-07-29 | 轨 A 实施完成：A1 LLM trace 接入 + A2 结构化日志 + A3 调试回放 + A4 OTEL exporter |
| 2026-08-11 | 轨 B 设计确认：scene 可选 Langfuse；两阶段 OTLP→Score；规格见 `docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md` |
| 2026-08-11 | 轨 B 阶段 1 实施完成：OTLP/HTTP exporter、`configure_langfuse_otel_from_env`、Harness `observe()`、scene lifespan 优先 Langfuse；阶段 2 待定 |
