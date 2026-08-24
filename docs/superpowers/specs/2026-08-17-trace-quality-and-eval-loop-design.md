# Trace 可信与产品评测闭环

> 日期：2026-08-17  
> 状态：待实施（指导后续开发的权威方案）  
> 范围：skill 激活事件总线、evolution collector 归因、脏 jsonl 隔离、聊天 👍/👎、Langfuse Score  
> **禁止**：引入 `agentevals` / LangChain / LangSmith；把 `langfuse` SDK 写入 `agent_core`；在脏 trace 上开自动 apply / 默认 scheduler  
> 关联：  
> - [`docs/skill-evolution-gap-and-roadmap.md`](../../skill-evolution-gap-and-roadmap.md)  
> - [`docs/observability-and-quality-plan.md`](../../observability-and-quality-plan.md)  
> - [`docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md`](./2026-08-11-langfuse-scene-integration-design.md)  
> - [`docs/superpowers/specs/2026-08-12-skill-progressive-disclosure-design.md`](./2026-08-12-skill-progressive-disclosure-design.md)  
> 实施计划：[`docs/superpowers/plans/2026-08-17-trace-quality-and-eval-loop.md`](../plans/2026-08-17-trace-quality-and-eval-loop.md)

---

## 0. 一句话目标

**先让「本 turn 激活了哪个 skill」成为与 tool 同等的事件真相，再让用户对一次 `run_id` 的打分同时落到本地 trace 与 Langfuse。**  
在此之前，禁止把现有 jsonl 当评测集，禁止打开自动写回 skill。

---

## 1. 现状（2026-08-17 实测，不是 8 月初文档的复述）

### 1.1 盘上的 evolution trace 仍是脏样本

路径：`~/.agent-core/skill-evolution-traces.jsonl`  
最后写入：**2026-07-31**（早于 8 月 3 日 collector 修复）。共 **440 条**，与缺口文档同一批：

| 字段 | 值 | 含义 |
|------|-----|------|
| skill 分布 | image-generation 220 + code-review 220 | 每个 session **双写** |
| `user_query` | 440/440 含 `[TextContent(` | 分组 / 证据文本不可用 |
| `loaded_rules` | 全空 | 规则级进化无锚点 |
| `user_feedback` / `reward` / `group_id` | 全空 | 无人工信号 |
| 内容 | 北京两日游、拍短剧也记到上述两 skill | 归因污染 |

`skill-evolution-audit.jsonl` 仅 2 条 **reject**（含测试），**没有一次真实 accept 改 SKILL.md**。  
`analyzed.json` 仍指向上述脏 id。新 collector 修好后 **jsonl 没有新行**。

### 1.2 代码已修、生产仍漏采（根因）

8 月 3 日 collector 改为保守归因：只写本 turn 激活的 skill；query 抽纯文本；steps 失败标 failure；默认关闭 tool→skill 反推。

8 月 12 日渐进式暴露：激活真相改为 `load_skill` / `/skill:` / 可选 `path_read`，并 `harness.record_skill_activation()`。

**断点：** `SkillStart` / `SkillEnd` 只发给 ChatAssistant 的 SSE `_handlers`，**不经过** `AgentHarness._handle_event` → `ExtensionRunner`。  
`SkillTraceCollector` 是 harness **extension**，听不到这次激活。

默认 `AGENT_SKILL_PROGRESSIVE=1` 且 prompt 里有多个 `available_skills` 时，TurnEnd 走「宁缺毋滥」→ **整 turn 不写 trace**。  
这解释了：修复后盘上没有新的干净数据。

单测绿是因为测试里手动 `collector.on_event(SkillStart)`；`tests/scene/test_skill_runtime_path_read.py` 只断言 `_handlers`，不断言 collector。

```
load_skill / /skill: / path_read
        ↓
SkillRuntime._emit_skill_start
        ├─ harness.record_skill_activation   ✅ OTEL run 属性能读到
        └─ _handlers (SSE)                   ✅ 前端偶发可见（H5 有 SkillStart 映射）
        ✗ ExtensionRunner / collector        ❌ 漏
        ✗ 注入块只扫 system_prompt           ❌ load_skill 全文在 tool result 里
```

### 1.3 产品评测闭环停在「看得见」

| 环节 | 状态 |
|------|------|
| 轨 A 本地调试（run/turn/llm/tool span + 日志） | ✅ |
| 轨 B 阶段 1 Langfuse OTLP 采数 | ✅ |
| 轨 B 阶段 2 Score / Dataset / 聊天打分 | ❌ 规格写了未做 |
| SSE 把 `run_id` 交给聊天气泡 | ❌ `AgentStart` 未进 `http_sse/events.py`；`message.end` 无 `run_id` |
| 聊天 👍/👎 | ❌ MessageBubble 只有复制 |
| `POST /skills/evolution/feedback` | 有 API，要 `trace_id`；前端不调；写的是 **skill_name 为空的孤儿行**，原 trace 的 `user_feedback` 仍空 |
| 固定评测集 + prompt 对照回放 | ❌ |

两条数据血脉目前断开：Langfuse 有 `run_id` 属性，evolution jsonl **没有 `run_id` 字段**。

---

## 2. 目标与非目标

### 2.1 目标（分两阶段，阶段 2 依赖阶段 1）

**阶段 1 — Trace 可信**

1. `load_skill` / `/skill:` / `path_read` 激活后，collector 在同一 turn 写出 **恰好对应 skill** 的 trace（不多写、不少写）。  
2. 新 trace：`user_query` 为纯文本、`loaded_rules` 非空（有规则则 `rule_N`，否则 `skill:<name>`）、带 `run_id`、`steps` 含本 turn 工具。  
3. 未激活任何 skill 的闲聊 **不写** evolution trace。  
4. 旧脏 jsonl **隔离**，analyze 默认不读；新文件从空开始。

**阶段 2 — 最小产品打分**

5. 助手气泡可 👍/👎，请求带 `run_id`（会话级 `session_id` 已有）。  
6. 同一 `run_id` 的 evolution traces 被附上 `human_signal` / `user_feedback`（禁止孤儿行当主记录）。  
7. 配置了 Langfuse 时，同一票打到 Langfuse Score，可用 `run_id` 在面板与本地对上。  
8. 未配 Langfuse 时本地反馈仍成功（评测出口可关，打分入口不可瘫）。

### 2.2 非目标（本方案明确不做）

- 引入 `agentevals`、`openevals`、LangChain、LangSmith（匹配模式若以后要做，自写 50 行 matcher）。  
- `langfuse` Python 包进入 `agent_core`；阶段 2 Score 用 **httpx + 现有 LANGFUSE_* 环境变量**。  
- Langfuse Dataset、坏 case 抽样回放、prompt 实验（B4）——等打分有真实票再开下一份 spec。  
- 打开 `ENABLE_EVOLUTION_SCHEDULER` 默认值、`ENABLE_EVOLUTION_AUTO_APPLY`、GroupRollout / CaseRecall 默认开。  
- 用 LLM-as-judge 批量给历史 440 条打分。  
- 重做 EvolutionPanel UI。  
- 把 tool→skill 一对一映射重新变成主归因。

---

## 3. 架构决策（已锁定）

### D1 事件总线：SkillStart/End 必须走 harness emit-sink

新增 `AgentHarness.emit_event(evt)`，内部复用 `_handle_event`（extensions + subscribe 监听者）。

`SkillRuntime._emit_skill_start` / `SkillEnd` **只**走 `emit_event`，**不再**直接扫 `_handlers`。  
http_sse / h5 / cli 已 `harness.subscribe(_on_agent_event)` → 转发 `_handlers`，SSE 不会丢，且不会双发。

`handle_turn_end` 只负责清 `_active_skills` 并发 `SkillEnd`（经 emit_event）。不要再把 SkillEnd 直接丢给 `_handlers`。

嵌套可接受：`load_skill.execute` 处于 tool 执行中，此时 `emit_event(SkillStart)` 会重入 `_handle_event`。SkillStart 不改 `_pending_tool_calls`，与 tool 生命周期正交。

### D2 collector 双通道归因（主 + 兜底）

TurnEnd 解析 skill 名，按顺序：

1. 本 turn `SkillStart` 累加的 `_turn_active_skills`  
2. `harness.skill_activations` 中尚未包含的名字（防 emit 失败或测试未 start harness）  
3. system_prompt 里带 `location=` 的注入块（`/skill:` 若仍改 system 时）  
4. `available_skills` **恰好 1 个** 才归因  
5. 否则不写 trace

禁止再解析全部 `<skill name>` 扇出。`AGENT_SKILL_LEGACY_TOOL_MAP` 保持默认 0。

### D3 join key 是 `run_id`

- `AgentStart` 已有 `run_id`。collector 在 `AgentStart` 记下 `_active_run_id`，写入每条 `SkillEvolutionTrace.run_id`。  
- SSE：`message.end`（及如需 `agent.start`）带上 `run_id`，前端落到 `ChatMessage.runId`。  
- Langfuse：已有 `langfuse.trace.metadata.run_id`。Score POST 的 `traceId` **不要**假设等于 `run_id`（OTEL trace id 是另一套）。Score body 用 Langfuse 支持的字段 + metadata `run_id`；若官方 API 只能绑 `traceId`，则用 **sessionId + comment/metadata.run_id**，并在文档写明面板按 session 筛选后再对 metadata。实施时以当时 Langfuse Public API 为准，**禁止**为了对齐而改 OTEL 的真实 trace id。

### D4 反馈是 overlay，不是新主 trace

jsonl 仍 append-only。`record_user_feedback`：

- 追加一行 `execution_details.type=feedback`，含 `original_run_id` / `original_trace_id`  
- `get_traces()` **合并** overlay 到匹配的主 trace（填 `user_feedback`、`human_signal`）  
- 查询结果 **不**把孤儿 feedback 行当成独立 skill 样本  
- InMemory store 允许直接改原对象，单测更简单；jsonl 用合并读径保持 Protocol 一致

聊天入口：`run_id` + `was_helpful` 即可（`trace_id` 可选）。EvolutionPanel 仍可按 `trace_id` 附言。

### D5 脏数据隔离，不删除、不拿来 analyze

启动或 analyze 前：若默认 jsonl 被判定为 legacy（抽样 `user_query` 含 `[TextContent` 或同一 session 双 skill 镜像），则：

1. 重命名为 `skill-evolution-traces.jsonl.legacy-20260731`（已存在则不覆盖，加后缀）  
2. 新路径写空文件  
3. `analyzed.json` 对 legacy id 失效（可一并改名为 `.legacy`）

analyze API 若仍读到 `user_query` 含 `[TextContent`，跳过该条并在响应 `diagnostics` 计数。

### D6 分层

| 层 | 做 | 不做 |
|----|----|------|
| `agent_core` | `emit_event`；collector 归因；trace.`run_id`；store 合并 feedback | Langfuse HTTP、👍 UI |
| `scene/` | SSE 下发 `run_id`；feedback 路由；可选 Score POST | 把厂商字段写进 loop |
| 前端共享 `components/chat/MessageBubble.tsx` | 👍/👎 | 不要只改 `src/h5/` 副本逻辑；Icon 名必须进 `Icon.tsx` 的 `IconName` |
| Vite | 新 API 若不以 `/skills` `/api` 开头必须补 proxy | 不要新开未代理路径 |

---

## 4. 成功标准（可独立验收）

### 阶段 1

1. 集成测试：多 skill 的 `available_skills` + 一次 `load_skill(image-generation)` + 一个业务 tool → **恰好 1 条** trace，`skill_name=image-generation`，query 无 `TextContent`，`run_id` 非空。  
2. 同条件下不调用 `load_skill`、不用 `/skill:` → **0 条** trace。  
3. `/skill:foo` 与 `path_read` 各至少 1 条测试覆盖。  
4. 本地默认 jsonl 被隔离后，新对话不再追加到 440 条脏文件。  
5. 现有 `tests/skill_evolution/`、`tests/scene/test_skill_runtime_path_read.py`、`tests/tools/test_load_skill.py` 全绿（path_read 改为断言 harness 事件，而不是 Runtime 私有 `_handlers` 直发）。

### 阶段 2

6. 一轮真实对话后，助手气泡可点 👍，网络请求含 `run_id`；对应 jsonl 主 trace 合并后 `human_signal.vote=like`。  
7. `LANGFUSE_ENABLED=1` 且密钥有效时，Langfuse 该 session 下能看到同名 Score；密钥缺失时 HTTP 反馈仍 200，日志 warning。  
8. H5 与桌面共用 MessageBubble；新增 Icon 名在 `IconName` 联合类型内。  
9. 不点赞的对话不产生 feedback overlay。

### 仍不算闭环（避免宣称过度）

- 没有 Dataset、没有改 prompt 对照回放、没有自动进化写回。阶段 2 只做到 **「差评能按 run_id 找到」**。

---

## 5. 风险

| 风险 | 对策 |
|------|------|
| `emit_event` 在 tool 内重入 | SkillStart 不碰 tool pending 集合；单测 load_skill 路径 |
| SkillStart 双发到 SSE | Runtime 去掉 `_handlers` 直发；只保留 harness subscribe 一条路 |
| CLI / 未 start 的 harness 无 `_ext_runner` | `_handle_event` 已允许 runner 为 None；collector 兜底读 `skill_activations` |
| Langfuse Score 对不上 OTEL trace id | 不伪造 trace id；用 session + metadata.run_id；文档写清 |
| 前端没有 `run_id` 导致打分失败 | 先做 SSE `message.end.run_id`，气泡无 runId 则隐藏按钮 |
| 误开 scheduler 分析脏数据 | D5 隔离 + analyze 跳过 TextContent；scheduler 默认保持 0 |
| H5 Icon 名不存在导致按钮不可见 | 先改 `Icon.tsx` 再引用 |

---

## 6. 实施顺序（禁止并行大干）

```
阶段 1（必须先做，可单独合并）
  1. harness.emit_event
  2. SkillRuntime 只走 emit_event
  3. collector：SkillStart + skill_activations + run_id
  4. 脏 jsonl 隔离 + analyze 跳过
  5. 单测 / 手工：load_skill 后 jsonl 出现干净行

── 闸门：阶段 1 成功标准 1–5 全过，才开始阶段 2 ──

阶段 2
  6. SSE 下发 run_id → ChatMessage
  7. feedback overlay 按 run_id 合并
  8. MessageBubble 👍/👎
  9. scene Langfuse Score HTTP（无 SDK）
  10. 更新 FEATURES / observability plan / gap roadmap 状态

明确下一份 spec（本方案结束后才开）
  B4 Dataset + 回放对照
  自写 trajectory matcher（若 Scene 有 golden）
```

---

## 7. 决策记录

| 日期 | 决策 |
|------|------|
| 2026-08-17 | 不引入 agentevals；评测走 Langfuse + 自研 collector |
| 2026-08-17 | SkillStart 必须进 harness 事件总线，collector 不再依赖 SSE 旁路 |
| 2026-08-17 | 旧 440 条 jsonl 隔离不删除；analyze 不得当训练集 |
| 2026-08-17 | 产品打分 join key = `run_id`；feedback 合并到主 trace |
| 2026-08-17 | 阶段 2 仍零 `langfuse` 包；Score 用 httpx |
| 2026-08-17 | 本文件为后续开发验收依据；任务拆解见同日 plan |
