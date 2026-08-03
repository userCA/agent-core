# Skill 自进化：现状缺口与完善路线图

> **日期**：2026-08-03  
> **目的**：基于本地实测与代码核对，记录「库已齐、闭环未通」的真实状态，并给出可执行的后续开发优先级。  
> **相关文档**：[`skill-self-evolution.md`](./skill-self-evolution.md)（能力说明）、[`superpowers/specs/2026-07-23-skill-grpo-evolution-design.md`](./superpowers/specs/2026-07-23-skill-grpo-evolution-design.md)（GRPO 设计）、[`agent-framework-optimization-plan-phase2.md`](./agent-framework-optimization-plan-phase2.md) §3（已知工程债）

---

## 0. 一句话结论

**数据在收，但信号脏；分析链路未接 LLM；验证可被 force 绕过；无人自动触发；审计从未写过。**  
因此「自我进化」目前只完成了观测侧的半截（Trace 落盘），**没有产生过一次真实的 skill 规则更新**。

---

## 1. 当前实现了什么（库能力）

`agent_core/skill_evolution/` 覆盖完整流水线（单元测试 `tests/skill_evolution/` 已绿）：

| 阶段 | 模块 | 功能 |
|------|------|------|
| Trace 收集 | `collector.py` | Extension 挂事件流，记 query / outcome / tool steps |
| 存储 | `store.py` | InMemory / JsonL |
| 离线分析 | `agent.py` | 批读 trace → LLM 或 heuristic → `PatchProposal`；含 GRPO 路径蒸馏入口 |
| 验证 | `validation.py` | before/after 对比；`evaluate_acceptance_gates`（Δr̄ 等） |
| Path Case | `cases.py` + `case_recall.py` | 正负例落盘 + top-k 注入 context |
| GRPO | `grouping` / `relative_score` / `distiller` / `group_rollout` / `reward` | 组内相对评分与主动 G 采样 |
| 审计 | `audit.py` | accept/reject append-only 日志 |

Scene 侧：

- `ENABLE_SKILL_EVOLUTION=1`（默认开）→ `SkillTraceCollector` 已挂到 http_sse / h5 `ChatAssistant`
- 手动 API：`/skills/evolution/{summary,analyze,feedback,proposals,audit}` + 前端 `EvolutionPanel`
- `ENABLE_GROUP_ROLLOUT` / `ENABLE_SKILL_CASE_RECALL` **默认关**

---

## 2. 本地实测（2026-08-03）

路径：`~/.agent-core/skill-evolution-traces.jsonl`

| 指标 | 值 | 含义 |
|------|-----|------|
| Trace 条数 | **440** | Collector 确实在写盘 |
| 技能分布 | `image-generation` 220 + `code-review` 220 | **每个 session 双写**（见 §3.1） |
| Session 数 | 37，且全部同时含上述两 skill | 归因污染，非真实「两技能都被用」 |
| `execution_outcome` | success 402 / failure 38 | 粗粒度成功判定 |
| `loaded_rules` 非空 | **0 / 440** | `on_skill_loaded` 从未被 Scene 调用 |
| `user_feedback` 非空 | **0 / 440** | feedback API 有，产品路径未喂数 |
| `new_rules_discovered` 非空 | **0 / 440** | heuristic 成功分析入口为空 |
| `user_query` 形态 | **440/440** 为 `str(TextContent)` | 形如 `[TextContent(type='text', text='…')]` |
| `steps` 非空 | 256 / 440 | 工具链有一部分可用 |
| `reward` / `group_id` | 全空 | 在线未算奖、未开 GroupRollout |
| `task_key` ≥3 的组 | 17 组（但 key 被 TextContent 前缀污染） | GRPO 分组「能凑数」，信号差 |
| `skill-evolution-audit.jsonl` | **不存在** | 从未 accept/reject 写审计 |
| `cases/{positive,negative}.jsonl` | **不存在** | 无 path case 落盘 |

**对照用户结论**：Trace 收集 ✅；其余闭环 ❌ —— 实测一致，且 **Trace 质量本身不足以支撑有意义的进化**。

---

## 3. 断点详解（比「LLM 没接」更深一层）

### 3.1 Trace 归因错误（P0 数据债）

`SkillTraceCollector._extract_skill_names` 从 **整份 system_prompt** 解析全部 `<skill name="...">`，TurnEnd 时对每个 skill **各写一条**相同 query/steps 的 trace。

后果：

- 旅行规划、查工具参数等与 `image-generation` / `code-review` 无关的对话也被记在这两 skill 下
- `run_evolution_cycle(skill_name=...)` 读到的是噪声样本，LLM 再好也会过拟合错域

**目标行为**：只记录本 turn **实际激活/相关** 的 skill（路由命中、显式 load、或工具归属），而不是 prompt 里列出的全集。

### 3.2 Trace 字段空洞

| 字段 | 根因 | 对下游的影响 |
|------|------|----------------|
| `loaded_rules=[]` | Scene 从不调 `on_skill_loaded` | failure heuristic「改最后一条 rule」走不通；LLM 看不到规则 ID |
| `user_query` 含 `TextContent` 字面量 | `_extract_user_query` 用 `str(msg.content)` | task_key / 分组 / 证据文本全部脏 |
| `user_feedback` 恒空 | UI 未把满意度接到 `/skills/evolution/feedback` | 成功侧 heuristic 全灭 |
| outcome 过粗 | 仅看 message.error / tool_results.is_error | steps 里已有 tool error 仍可标 success；任务失败难进入失败分析池 |

### 3.3 OfflineEvolutionAgent「空转」

```text
create_offline_evolution_agent("jsonl")  # 工厂不接受 model_provider
  → OfflineEvolutionAgent(store)         # model_provider=None
  → _call_llm() → return None
  → 仅 heuristic：依赖 new_rules_discovered / user_feedback / loaded_rules / 特定 error 文案
```

在 440 条实测数据上，上述 heuristic 输入几乎全空 → **proposals ≈ 0**（或偶发低质量）。

GRPO 路径蒸馏（`_generate_path_proposals`）**不依赖 LLM**，理论上可出 proposal；但受 §3.1 归因污染 + 脏 task_key + 无 reward 标注限制，产出不可信，且 Scene analyze 后仍依赖人工点 accept。

### 3.4 ValidationGate 名存实亡

- `agent_runner` 未注入 → 关键词重叠打分（中文 `\w+` 几乎无效）
- Scene `accept` 使用 `apply_proposal(..., force=True)` → **验证失败也能写盘**
- 无 shadow/canary、无回滚策略（仅有 backup 文件能力）

### 3.5 无自动触发

- 只有手动 `POST /skills/evolution/analyze`（EvolutionPanel 按钮）
- 无 cron / 后台任务 / 「trace 达阈值自动跑」
- GroupRollout / CaseRecall 默认关，且未与连续失败钩子接进 ChatAssistant 主路径

### 3.6 工程债（已有文档，仍有效）

摘自 phase2 §3，开发时一并处理：

- `_analyzed_trace_ids` 仅内存，重启重复分析
- LLM call 预算计算边界 bug
- Proposal JSON 解析脆弱、失败静默
- Store 缺 mark_analyzed / prune / 按 outcome 查询的高效索引

---

## 4. 目标闭环（验收定义）

一条 skill（例如真实高频 skill，而非被误归因的名）满足：

```text
真实使用 → 正确归因的 Trace（含干净 query、steps、规则/技能、可区分 outcome）
       → 离线分析（LLM + 可选 GRPO）产出可 diff 的 Proposal
       → 验证门（真实或可解释的 shadow 评分）通过或人工复核
       → 原子写回 SKILL.md（或 add_case）
       → audit.jsonl 有记录
       →（可选）CaseRecall 在后续 turn 注入正负例
```

**最小可宣称「起作用」的验收**：

1. 连续 7 天采集的 trace：`loaded_rules` 或「实际 skill」字段非空率 > 80%；query 无 `TextContent` 字面量  
2. 对某一 skill `analyze` 在接入 provider 后能稳定产出 ≥1 条 confidence≥0.6 的 proposal（可用固定 fixture trace 回归）  
3. accept 路径：**默认不 force**；未过 gate 不得改文件；audit 必写  
4. 至少一次端到端：fixture → analyze → accept → skill 文件变更 + audit 行存在（CI 可跑）

---

## 5. 分阶段完善方案

原则：**先修信号，再接大脑，再守门，最后自动化与探索。**  
禁止在脏数据上开自动写回。

### P0 — Trace 可信（必须先做）

| ID | 事项 | 改动面 | 验收 |
|----|------|--------|------|
| P0.1 | 修正 user_query 提取：从 content parts 取 text，禁止 `str(list)` | `collector._extract_user_query` | 新 trace 无 `[TextContent` 前缀；补单测 |
| P0.2 | Skill 归因：只记录本 turn 相关 skill（方案见下） | collector + Scene 路由/skill 激活钩子 | 同 session 不再「双 skill 镜像」；归因与路由日志可对账 |
| P0.3 | 接线 `on_skill_loaded` 或写入 `active_skill` / `rule_ids` | ChatAssistant / ResourceLoader | `loaded_rules` 或等价字段非空率上升 |
| P0.4 | Outcome 策略：steps 错误率、任务级信号、可选 human_signal | collector + feedback | failure 池与真实工具失败对齐；文档化策略 |
| P0.5 | Feedback 产品路径：聊天满意度 → `trace_id` → `/skills/evolution/feedback` | 前端 + API 契约 | 抽检有 feedback 附属 trace |

**P0.2 归因方案（推荐顺序）**：

1. **短期**：若系统有 skill 路由结果，只写被选中的 skill；无路由则写「本 turn 工具所属 skill」或跳过（宁缺毋滥）  
2. **中期**：prompt 中区分 `available_skills` vs `activated_skills`，collector 只解析后者  
3. **禁止**：继续对 system_prompt 全量 skill 标签扇出写 trace

### P1 — 分析真正跑通

| ID | 事项 | 改动面 | 验收 |
|----|------|--------|------|
| P1.1 | `create_offline_evolution_agent(..., model_provider=)` 工厂透传 | `agent.py` | 单测：注入 FakeProvider 能出 proposal |
| P1.2 | Scene `analyze` 复用与 chat 相同的 provider/auth 装配 | `http_sse/server.py`、`h5/server.py` | 本地手动 analyze 对有失败 trace 的 skill 返回非空 proposals |
| P1.3 | 无 provider 时 API 明确返回 `analyzer=heuristic` + 诊断（为何 0 proposal） | analyze response | 前端可见「未接 LLM」而非静默空列表 |
| P1.4 | 持久化已分析 trace id / cursor | store | 重启不重复烧 token |
| P1.5 | 失败 heuristic 增强（不依赖 LLM 时的保底）：基于 steps 错误模式（tool not found、参数错误）生成「补工具说明/前置检查」类提案 | `agent.py` | 在关闭 LLM 时，对现有 failure+steps 样本仍能出 proposal |

### P2 — 验证门可信

| ID | 事项 | 改动面 | 验收 |
|----|------|--------|------|
| P2.1 | accept **去掉默认 force=True**；未过 gate → 403/422 + audit reject | server accept | 单测锁定 |
| P2.2 | 注入轻量 `agent_runner`（同一 provider，固定 test suite 或从高价值 trace 生成） | validation + scene | 至少 1 个 skill 有真实 before/after 分数 |
| P2.3 | 中文友好的 heuristic 兜底（字符 n-gram / jieba，二选一，避免假安全感） | `validation.py` | 中文 query 重叠分非恒 0 |
| P2.4 | 与 GRPO `evaluate_acceptance_gates` 对齐：路径类提案走 Δr̄ 门控 | distiller 提案 apply 路径 | 文档与代码一致 |

### P3 — 触发与运维

| ID | 事项 | 改动面 | 验收 |
|----|------|--------|------|
| P3.1 | 可选后台周期任务：`ENABLE_EVOLUTION_SCHEDULER=1`，按 skill 阈值/失败率触发 analyze | scene 或独立 CLI `python -m ...` | 文档说明频率与成本上限 |
| P3.2 | 成本护栏：`max_llm_calls`、按 skill 日预算、只分析 failure 优先 | agent + config | 日志可观测 |
| P3.3 | 人机默认：自动 analyze + **仅提案**；自动 apply 需显式 `ENABLE_EVOLUTION_AUTO_APPLY=0` 默认关 | 配置 | 误进化风险可控 |

### P4 — GRPO / CaseRecall（数据干净后再开）

| ID | 事项 | 改动面 | 验收 |
|----|------|--------|------|
| P4.1 | 对连续失败 skill 可选开 GroupRollout（成本高） | ChatAssistant + `group_rollout` | 写入同 `group_id` 的 G 条 trace |
| P4.2 | distill → `add_case` 落盘；开 `ENABLE_SKILL_CASE_RECALL` 做 A/B | cases + extension | 后续 prompt 含 Path Case 段 |
| P4.3 | 在线填 `reward` / `human_signal`（点赞点踩） | collector + UI | 相对评分不再纯 heuristic |

---

## 6. 建议实施顺序（开发 checklist）

```text
Week A（P0）
  [ ] P0.1 query 提取修复 + 测试
  [ ] P0.2 归因策略落地（先宁缺毋滥）
  [ ] P0.3 / P0.4 规则与 outcome
  [ ] 清空或归档旧脏 jsonl（或脚本打标 deprecated），避免污染新分析

Week B（P1）
  [ ] P1.1–P1.3 provider 接入 + API 诊断
  [ ] 用「归因修复后」的新数据跑一次 analyze，截图/日志归档
  [ ] P1.4 已分析游标持久化

Week C（P2）
  [ ] 去掉 force 默认；补 CI 端到端
  [ ] 最小 agent_runner 或明确「仅人工 diff 接受」产品策略（二选一写进配置）

Week D+（P3/P4）
  [ ] Scheduler（仍默认只提案）
  [ ] 按需开 CaseRecall / GroupRollout
```

---

## 7. 明确不做 / 暂缓

- **不在 P0 完成前**开启自动 apply 或默认 GroupRollout（烧钱 + 写坏 skill）  
- **不把** EvolutionPanel UI 美化当作进化闭环进度  
- **不以**「库内 96 passed」等同于「生产闭环可用」  
- 四层记忆 / 全局 Self-Feedback Engine：见 `agent-engineering-optimization.md` K3，**不阻塞**本路线图

---

## 8. 与既有文档的关系

| 文档 | 关系 |
|------|------|
| `docs/skill-self-evolution.md` | 保留为「怎么用 API」；本文是「为何没用起来 + 怎么修」 |
| `docs/superpowers/plans/2026-07-23-skill-grpo-evolution.md` | GRPO P0–P4 **库实现已完成**；本文 P4 是 **Scene 开启与数据前提** |
| `docs/agent-framework-optimization-plan-phase2.md` §3 | 工程债仍有效；本文把 Scene 接线缺口与实测合并成执行序 |
| `docs/agent-engineering-optimization.md` §4.1 | 其中「Collector 未注册」**已过时**（K1 已接线）；以本文 §1–2 为准 |

---

## 9. 关键代码锚点

| 问题 | 位置 |
|------|------|
| 工厂未传 provider | `agent_core/skill_evolution/agent.py` → `create_offline_evolution_agent` |
| analyze 未注入 provider | `scene/http_sse/server.py` / `scene/h5/server.py` → `analyze_skill_evolution` |
| LLM 空转 | `OfflineEvolutionAgent._call_llm` |
| 全量 skill 扇出 | `SkillTraceCollector._extract_skill_names` + `_handle_turn_end` |
| query 脏 | `SkillTraceCollector._extract_user_query` |
| accept 绕过验证 | `apply_proposal(..., force=True)` |
| CaseRecall / Rollout 开关 | `scene/http_sse/evolution_config.py` |

---

## 10. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-03 | 初版：核对库/Scene/440 条本地 trace，确认仅采集半通；给出 P0–P4 路线图 |
| 2026-08-03 | **P0–P2 首波落地**：collector 归因/query/outcome 修复；Scene 注册 skill→tool；analyze 接 provider；analyzed cursor 持久化；steps 失败 heuristic；accept 默认过验证门（`force` 可选） |
