# Skill 层 GRPO 理念进化设计

> **日期**：2026-07-23  
> **状态**：设计已确认，待实现计划  
> **范围**：在现有 `agent_core/skill_evolution/` 上叠加组内相对打分与路径蒸馏；**不**训练模型权重  
> **关联**：[`docs/skill-self-evolution.md`](../../skill-self-evolution.md)、[`docs/agent-framework-design-philosophy.md`](../../agent-framework-design-philosophy.md)

---

## 0. 摘要

用 GRPO（Group Relative Policy Optimization）的核心思想——**同一目标采多条路径、组内相对比较**——驱动 Skill 越用越好。

| 真 GRPO（训模型） | 本方案（进化 Skill） |
|-------------------|----------------------|
| 同 prompt 采 G 条轨迹 | 同 `task_key` / 主动 `group_id` 采 G 条 |
| \(A_i\) 进入 policy gradient | \(A_i\) 进入 Distiller，筛选正负例 |
| 更新参数 θ | 更新版本化制品 \(S_v\)（`SKILL.md` 规则 + `cases/`） |
| eval reward / loss | 固定评测集上 \(\Delta\bar{r}\ge\delta\) + 无关键回归 |

**产品选择（已确认）**：

1. **优化对象**：Skill 层（非模型权重）
2. **奖励**：启发式 + LLM Judge + 人工反馈（可缺省、可 renormalize）
3. **轨迹来源**：日常离线相似聚合 + 高价值/失败时主动多采样
4. **写回形态**：路径偏好规则（`SKILL.md`）+ 正负例案例库（非独立 Path Policy 运行时）
5. **变好证据**：版本化 \(S_v\) + 固定集 \(\Delta\bar{r}\) 门控

---

## 1. 问题与目标

### 1.1 问题

到达同一终点往往有多条工具/推理路径。当前 skill 进化：

- 轨迹偏粗（多为 query → outcome，缺逐步工具链）
- 成功/失败二值为主，**缺少同组相对比较**
- 难以回答：「这条路径是否比同目标下的其他路径更好？」
- 写回缺少与模型训练对等的**可验证优化变量与指标**

### 1.2 目标

1. 采集可比较的路径轨迹（含步骤）
2. 对同目标轨迹做组内相对打分 \(A_i\)
3. 将高/低优势路径蒸馏为规则 + 案例
4. 仅当固定评测集证明 \(S_{v+1}\) 优于 \(S_v\) 时写回
5. 遵守「库 ≠ 服务」：库提供能力，scene/宿主调度采样与离线 job

### 1.3 非目标

- 模型权重上的 GRPO / PPO / RLHF
- 依赖 token logprob
- 独立 Path Policy 执行引擎
- 将完整对话原文写入系统提示

---

## 2. 整体架构

```
在线（Scene / Extension）
  AgentEvent 流 → TrajectoryCollector（细粒度 PathTrace）
       │
       ├─ 日常：1 条轨迹入库
       └─ 触发：高价值 skill / 连续失败 → GroupRollout（G 次采样）
       ↓
轨迹库（扩展现有 skill_evolution store）
  PathTrace + RewardRecord + optional HumanFeedback
       ↓
离线 Pipeline（升级 OfflineEvolutionAgent）
  1. TaskGroupBuilder    — 相似目标聚成 group（G≥G_min）
  2. HybridReward        — 启发式 + LLM Judge + 人工
  3. GroupRelativeScorer — A_i = r_i − mean(r_group)（可选 σ 归一）
  4. Distiller           — 高 A → 路径规则 + 正例；低 A → 反模式 + 负例
  5. ValidationGate      — S_v vs S_{v+1}，Δr̄ ≥ δ 且无关键回归
       ↓
写回
  SKILL.md（Path Preferences）+ cases/（positive / negative）
  + version bump + audit log
```

**边界**：

- `core/loop.py` 语义不变；不引入训练环
- 在线 G 采样、定时离线 job 由 scene 或宿主调度
- 库内模块以 Protocol + 默认实现形式提供，可替换 Judge / 存储

---

## 3. 优化变量与“变好”的精确定义

训模型有 θ；Skill 进化必须有对等物，否则无法证明改进。

### 3.1 优化变量 \(S_v\)

\[
S_v = \{\text{SKILL.md 规则段},\ \text{cases/ 正负例},\ \text{version}\}
\]

- 可序列化、可 diff、可回滚
- 每次进化：\(S_v \rightarrow S_{v+1}\)
- 审计记录 `base_version`、`new_version`、支撑 `group_id`、门控指标

### 3.2 官方目标函数

对每个 skill 维护固定评测集 \(T_{\text{skill}}\)。在**同一模型、工具集、解码参数**下：

\[
\bar{r}(S) = \frac{1}{|T|}\sum_{t \in T} r(t, S)
\]

**唯一自动放行条件（须全部满足）**：

1. \(\Delta\bar{r} = \bar{r}(S_{v+1}) - \bar{r}(S_v) \ge \delta\)（默认 \(\delta = 0.05\)，对齐现有 `test_threshold`）
2. 无关键用例回归（success → failure 等）
3. 平均步数恶化不超过 \(\varepsilon\)（默认 15%）

辅指标（报告用，不单独放行）：Judge 分、人工偏好一致率、高优势路径复现率、耗时。

### 3.3 为何这是当前最佳起步

| 方案 | 评价 |
|------|------|
| 固定集 \(\Delta\bar{r}\) + 回归护栏（本方案） | 可控、可复现、对接现有 ValidationGate；Skill 层最佳起步 |
| 纯线上 A/B | 噪声大、慢；适合门控通过后的灰度，不替代门控 |
| 仅 Judge / 仅人工 | 贵或不稳，不能当唯一放行条件 |
| 真 GRPO 训模 | 超出本次范围 |

可演进：按 skill 调 \(\delta\)；扩 \(T\)；门控通过后加影子流量。

---

## 4. 数据模型

在现有 `SkillEvolutionTrace` / `PatchProposal` 上扩展（向后兼容：旧字段保留）。

### 4.1 PathTrace（细粒度轨迹）

| 字段 | 说明 |
|------|------|
| `trace_id` | 唯一 ID |
| `group_id` | 可选；主动采样时当场分配；离线聚合后回填 |
| `skill_name` | 关联 skill |
| `task_key` | 归一化目标键（去噪 query / 意图槽 / 模板哈希） |
| `user_query` | 原始查询 |
| `session_id` | 会话 |
| `steps[]` | 见下 |
| `outcome` | 复用 `ExecutionOutcome` |
| `reward` | 标量，可后算 |
| `advantage` | 组内相对优势，可后填 |
| `human_signal` | like / dislike / `preferred_trace_id` 等 |
| `loaded_rules` | 兼容现有字段 |
| `execution_details` | 兼容扩展袋 |

**Step 记录**（摘要级，非全文）：

- `tool_name`、关键参数摘要（截断/脱敏）、`is_error`、耗时、可选短错误信息

### 4.2 RewardRecord

- `trace_id`、`r_h`、`r_j`、`r_u`、`r`、`weights`、`computed_at`
- 缺失分量标记 `null`，打分时 renormalize

### 4.3 PatchProposal 扩展

- 现有：`modify` / `add` / `remove` 规则
- 新增：`add_case` / `retire_case`
- 元数据：`base_version`、`expected_delta_r`、`source_group_ids`、`source_trace_ids`

### 4.4 Skill 版本元数据

建议在 skill 目录：

```
skill-name/
  SKILL.md              # 含 ## Path Preferences 等章节
  cases/
    positive.jsonl      # 或 .md；路径摘要
    negative.jsonl
  evolution/
    VERSION             # 或 frontmatter version
    tests/              # 固定评测用例 T_skill
```

---

## 5. 混合奖励

\[
r = w_h r_h + w_j r_j + w_u r_u
\]

默认起步权重：`w_h=0.4, w_j=0.4, w_u=0.2`。缺某一项时将该权重分摊到其余项并 renormalize。

### 5.1 \(r_h\) 启发式（轨迹可算）

归一化到约定区间（建议 \([0,1]\) 或 \([-1,1]\)，实现时统一）：

- 任务完成 / `outcome`（强先验：failure 显著压低）
- 工具错误率（−）
- 相对组内的步数、耗时偏高（−）
- 重复无效调用（−）
- HITL 次数（−）

### 5.2 \(r_j\) LLM Judge

- 输入：**路径摘要**（工具序列 + 关键错误 + 最终结果），禁止默认喂全文对话
- 评判维度：目标达成度、路径简洁性、是否遵循 skill
- 权重有上限，防止 Judge 漂移主导放行

### 5.3 \(r_u\) 人工

- like = +1，dislike = −1
- 显式「更优路径」：preferred 抬高；同组其余略降（先锚定相对序，再并入连续分）
- 复用/扩展现有 `POST /skills/evolution/feedback` 一类 API

### 5.4 与 outcome 的关系

`ExecutionOutcome` 保留为 \(r_h\) 强先验；最终组内排序以混合 \(r\) 与 \(A_i\) 为准，避免「碰巧成功但路径很差」成为最优模板。

---

## 6. 分组与组内相对优势

### 6.1 成组模式

| 模式 | 何时 | 如何 |
|------|------|------|
| 主动采样组 | 高价值 skill / 连续失败 | 同 query + 同 skill，当场 `group_id`，跑 G 次（建议 G=3~5） |
| 离线聚合组 | 日常 | 同 `skill_name` + 相似 `task_key`，时间窗内凑齐 \(G_{\min}\)（建议 ≥3）；不足则只记绝对 \(r\)，不产 \(A_i\) 提案 |

`task_key`：轻量归一化（去会话噪声、抽意图槽、模板哈希）；可选 embedding 相似度（宿主注入）。

### 6.2 相对优势

\[
A_i = r_i - \frac{1}{G}\sum_{j=1}^{G} r_j
\]

可选稳定化：\(A_i \leftarrow A_i / (\sigma_g + \varepsilon)\)。

**蒸馏门**：

- \(A_i > +\tau\) → 正例池（路径偏好）
- \(A_i < -\tau\) → 负例池（反模式）
- \(|A_i| \le \tau\) → 忽略（建议 \(\tau \in [0.1, 0.2]\)）

---

## 7. 蒸馏写回

### 7.1 路径偏好规则

写入 `SKILL.md` 固定章节（如 `## Path Preferences`）：

- 形式：「优先…」「避免…」「当…时先…」
- 带 `rule_id`、来源 `group_id`、置信度
- 必须可执行、可被评测集覆盖；禁止空话

### 7.2 正负例案例库

- `cases/positive.*` / `cases/negative.*`
- 存路径摘要（工具序列 + 结果），非全文
- 注入时按与当前 query 的相似度 top-k；受 token 预算约束；可配置关闭
- 设上限与淘汰策略（低优势、过期、与新规则冲突）

### 7.3 Distiller 职责

1. 从高/低 \(A_i\) 轨迹生成规则草案与案例草案
2. 与现有 Success/Error Analyst 层次合并、去重、冲突标记
3. 输出带 `expected_delta_r` 的提案包

---

## 8. 验证门控与度量

### 8.1 门控流程

1. 在 \(T_{\text{skill}}\) 上分别跑 \(S_v\) 与候选 \(S_{v+1}\)
2. 使用**同一套混合奖励**（至少含可复现的 \(r_h\)；Judge 可缓存或关闭以保证确定性）计算 \(\bar{r}\)
3. 检查 §3.2 放行条件
4. 通过 → 原子写回 + version bump + audit；失败 → 拒绝（可选人工审）

升级现有 `SkillValidationGate`：

- `score_delta` 的官方定义改为混合 \(r\) 的 \(\Delta\bar{r}\)
- 增加关键回归与步数护栏
- 保留 `require_human_review` 开关

### 8.2 健康度量

| 指标 | 含义 |
|------|------|
| `acceptance_rate` | 提案过门比例 |
| `delta_r_hist` | 每次过门的 \(\Delta\bar{r}\) |
| `rollback_count` | 上线后回滚次数 |
| `group_coverage` | 能成组打相对分的任务占比 |
| `human_agree` | 人工偏好与 \(A_i\) 符号一致率 |

---

## 9. 与现有模块对接

| 能力 | 落点 | 复用 |
|------|------|------|
| 细粒度步骤 | `collector.py` + `types.py` | Extension / `AgentEvent` |
| 主动 G 采样 | 库：`GroupRollout` Protocol；scene 调度 | `SessionStore.fork_session` |
| 混合奖励 | 新 `reward.py` | feedback API |
| 分组 + \(A_i\) | 新 `grouping.py`、`relative_score.py` | 离线 pipeline |
| 蒸馏 | 扩展 `agent.py` | `PatchProposal` |
| \(S_v\) 门控 | 升级 `validation.py` + `audit.py` | `test_threshold` |
| 案例注入 | `prompts/builder.py` 或 skill 展开路径 | `SystemPromptBuilder` |

**明确不改**：`core/loop.py` 核心语义；不引入 logprob。

现有粗粒度 `SkillEvolutionTrace` 可映射为缺 `steps` 的 PathTrace，旧数据仍可用于 outcome 级分析，但**不参与**相对路径蒸馏，直至补齐步骤或仅作弱信号。

---

## 10. 分阶段落地

| 阶段 | 交付 | 验收标准 |
|------|------|----------|
| **P0** 可测轨迹 | `PathTrace.steps`、outcome、可选 human；持久化 | 单测：假事件重建步骤序列 |
| **P1** \(r\) + \(A_i\) | HybridReward、TaskGroupBuilder、GroupRelativeScorer；离线批跑 | G=3 算出 mean/\(A_i\)；缺人工时权重 renormalize |
| **P2** 蒸馏 + 门控 | Path Preferences + cases；\(\Delta\bar{r}\ge\delta\) + 无回归才写回 | 人造更差规则被拒；更优规则过门且 audit 有版本 |
| **P3** 主动采样 | 失败/高价值触发 G 次 rollout（scene 开关，默认关） | 关闭时行为与今日一致 |
| **P4** 案例召回 | 提示 top-k 正负例 | 预算内可关；回归集不降 |

每阶段独立可测；P0–P2 构成最小闭环（「越用越好」的离线证明）；P3–P4 提升数据效率与在线利用。

---

## 11. 风险与护栏

| 风险 | 缓解 |
|------|------|
| 过拟合单次高分路径 | 必须过固定集 \(T\)；\(G < G_{\min}\) 不产相对提案 |
| Judge 漂移 | \(w_j\) 上限；放行以可复现 \(r_h\) + 任务成功为主 |
| Skill / 案例膨胀 | 案例上限与淘汰；规则冲突走 merge + 审计 |
| 在线采样成本 | 默认关；仅触发式开启 |
| 评测不确定性 | 门控跑可关 Judge；同 seed/温度；记录完整配置 |

---

## 12. 成功标准（设计验收）

设计落地后，系统应能回答并证明：

1. **参数是什么**：某个 skill 的 \(S_v\)（文件 + version）
2. **这次改了什么**：audit diff（规则 / 案例）
3. **为何认为更好**：门控报告中的 \(\Delta\bar{r}\)、失败率、步数
4. **相对比较是否发生**：存在 `group_id` 与非零 \(A_i\) 分布
5. **能否回滚**：拒绝坏提案；已应用版本可回退到 \(S_v\)

---

## 13. 参考

- 仓库内：`agent_core/skill_evolution/`、`docs/skill-self-evolution.md`
- 思想来源：GRPO（组内相对优势）；Trace2Skill / EvoSkill（轨迹聚合 + 验证门控）
- 约束：`docs/agent-framework-design-philosophy.md`（库 ≠ 服务、YAGNI、事件契约）
