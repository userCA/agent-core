# Skill 自进化系统

本文档描述 agent-core 中的 **Skill 自进化系统**，该系统基于 Trace2Skill 和 EvoSkill 研究论文实现，能够自动从执行轨迹中学习并优化 skill 规则。

> **落地状态与后续开发**：库能力已齐，但 Scene 闭环未通（Trace 有脏数据、analyze 未接 LLM、验证可被 force 绕过、无自动触发）。详见 [`skill-evolution-gap-and-roadmap.md`](./skill-evolution-gap-and-roadmap.md)。

## 核心原理

### 问题背景

传统 skill 维护是**人工驱动**的：
1. Bug 发生 → 人工发现 → 人工分析 → 人工写规则
2. 存在滞后性、主观性、不可规模化问题

### 解决方案

采用 **"离线轨迹聚合 + 在线验证门控"** 的双层架构：

```
┌─────────────────────────────────────────────────┐
│           Skill Self-Evolution Pipeline          │
├─────────────────────────────────────────────────┤
│                                                  │
│  1. Trace Collection (collector.py)             │
│     ├─→ 捕获 skill 使用情况                      │
│     └─→ 存储到持久化日志                         │
│                                                  │
│  2. Offline Analysis (agent.py)                 │
│     ├─→ 读取批量 traces                          │
│     ├─→ 并行提案生成                             │
│     │    ├─ Success Analysts (提取成功模式)      │
│     │    └─ Error Analysts (诊断失败根因)        │
│     └─→ 层次化合并（去重、解决冲突）              │
│                                                  │
│  3. Validation Gate (validation.py)             │
│     ├─→ 在测试集上对比新旧版本                   │
│     └─→ 只接受有提升的变更                       │
│                                                  │
│  4. Skill Update                                │
│     └─→ 原子化应用接受的变更                     │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 关键设计原则

1. **批量处理**：避免对单个案例过拟合
2. **冲突检测**：识别并标记矛盾的提案
3. **保守更新**：只接受可测量的改进
4. **验证门控**：防止"盲目进化"导致退化

## 快速开始

### 1. 设置轨迹收集器

在你的 agent/session 初始化时添加 trace collector：

```python
from agent_core.skill_evolution import create_skill_trace_collector

# 创建 collector（默认使用 JSONL 持久化存储）
collector = create_skill_trace_collector(
    store_type="jsonl",  # "memory" for testing, "jsonl" for production
    storage_path="~/.agent-core/skill-evolution-traces.jsonl",
    enabled=True,
)

# 注册到 session
session.add_extension(collector)
```

Collector 会自动捕获：
- Skill 加载事件（哪些规则被激活）
- 执行结果（成功/失败）
- 用户反馈（如果提供）

### 2. 运行离线进化分析

定期（如每天）运行进化周期：

```python
from agent_core.skill_evolution import create_offline_evolution_agent

# 创建进化代理
agent = create_offline_evolution_agent(
    store_type="jsonl",
    batch_size=100,  # 每次分析的 trace 数量
)

# 运行进化周期
result = await agent.run_evolution_cycle(
    skill_name="dev-process-backend",
    min_traces=50,  # 最少需要多少 traces 才分析
    max_proposals=5,  # 最多生成多少个提案
)

print(f"Analyzed {result['traces_analyzed']} traces")
print(f"Generated {result['proposals_generated']} proposals")
print(f"Accepted {len(result['final_proposals'])} proposals")
```

### 3. 验证并应用提案

```python
from agent_core.skill_evolution import create_validation_gate

# 创建验证门控
gate = create_validation_gate(
    skill_dir=".claude/skills",
    test_threshold=0.05,  # 至少提升 5% 才接受
)

# 注册测试用例
from agent_core.skill_evolution.types import TestCase

test_cases = [
    TestCase(
        test_id="tc1",
        description="Type safety check",
        input_query="getattr config field",
        expected_behavior="Should flag getattr usage",
        success_criteria="no_error",
    ),
]
gate.register_test_cases("dev-process-backend", test_cases)

# 验证每个提案
for proposal_data in result["final_proposals"]:
    from agent_core.skill_evolution.types import PatchProposal
    proposal = PatchProposal(**proposal_data)
    
    validation_result = await gate.validate(proposal, test_cases)
    
    if validation_result.passed:
        print(f"✓ Proposal {proposal.proposal_id} passed validation")
        await gate.apply_proposal(proposal, backup=True)
    else:
        print(f"✗ Proposal {proposal.proposal_id} rejected (delta={validation_result.score_delta})")
```

## 组件详解

### 1. Trace Collector (`collector.py`)

**职责**：自动捕获 skill 执行轨迹

**关键方法**：
- `on_before_agent_start()`: 新查询开始时重置状态
- `on_skill_loaded()`: 记录加载的 skill 和规则
- `on_turn_end()`: 保存最终轨迹

**数据结构**：
```python
@dataclass
class SkillEvolutionTrace:
    trace_id: str
    timestamp: float
    session_id: str | None
    user_query: str
    skill_name: str
    loaded_rules: list[str]
    execution_outcome: ExecutionOutcome  # SUCCESS/PARTIAL/FAILURE/REGRESSION
    execution_details: dict
    user_feedback: str | None
    regression_info: dict | None
```

### 2. Memory Store (`store.py`)

**支持的存储后端**：
- `InMemorySkillEvolutionStore`: 测试用
- `JsonlSkillEvolutionStore`: 生产环境（JSONL 格式）
- 可扩展：MongoDB 等

**JSONL 格式示例**：
```json
{"trace_id": "uuid-123", "timestamp": 1717200000.0, "skill_name": "dev-process-backend", "loaded_rules": ["rule_14"], "execution_outcome": "failure", ...}
```

### 3. Offline Evolution Agent (`agent.py`)

**工作流程**：

1. **轨迹分离**：
   - 成功轨迹 → Success Analyst
   - 失败轨迹 → Error Analyst

2. **并行提案**：
   ```python
   # Success Analyst: 提取可复用模式
   async def _analyze_success_trace(trace):
       if trace.user_feedback and "helpful" in trace.user_feedback:
           return PatchProposal(
               operation="modify",
               target_rule_id=trace.loaded_rules[0],
               rationale="User confirmed these rules are helpful",
               confidence=0.6,
           )
   
   # Error Analyst: 诊断根因
   async def _analyze_failure_trace(trace):
       if "rule not found" in trace.execution_details.get("error", ""):
           return PatchProposal(
               operation="add",
               rationale="Error indicates missing rule",
               confidence=0.8,
           )
   ```

3. **层次化合并**：
   - 按 skill_name + target_rule_id 分组
   - 检测冲突（同一目标的不同操作）
   - 优先高置信度提案
   - 丢弃低置信度离群值

### 4. Validation Gate (`validation.py`)

**验证流程**：

1. 加载当前 skill 内容
2. 应用提案生成新版本
3. 在测试集上运行两个版本
4. 计算性能差异
5. 只有通过阈值（默认 +5%）才接受

**测试用例定义**：
```python
TestCase(
    test_id="unique-id",
    description="What this validates",
    input_query="Query to feed to agent",
    expected_behavior="Description of expected outcome",
    success_criteria="no_error" | callable,  # How to check pass/fail
    tags=["category1", "category2"],
)
```

## 最佳实践

### 1. 最小 traces 数量

建议设置 `min_traces >= 20` 以避免过拟合：
- < 10 traces: 容易受个别案例影响
- 20-50 traces: 平衡灵敏度和稳定性
- > 100 traces: 更保守，适合生产环境

### 2. 测试用例质量

验证效果取决于测试用例质量：
- **覆盖常见场景**：确保测试集代表真实使用模式
- **包含边界情况**：测试极端输入
- **定期更新**：随着 skill 演进更新测试用例

### 3. 阈值选择

`test_threshold` 控制接受标准：
- `0.05` (5%): 默认，平衡敏感性和噪声
- `0.10` (10%): 更保守，只接受显著改进
- `0.02` (2%): 更激进，捕捉微小改进

### 4. 备份策略

始终启用备份：
```python
await gate.apply_proposal(proposal, backup=True)
```

备份文件位于：`.claude/skills/<skill-name>/SKILL.md.bak`

### 5. 监控和审计

定期检查进化结果：
```bash
# 查看最近的 traces
tail -n 50 ~/.agent-core/skill-evolution-traces.jsonl

# 统计各 outcome 分布
jq -r '.execution_outcome' ~/.agent-core/skill-evolution-traces.jsonl | sort | uniq -c
```

## 故障排除

### 问题：没有生成任何提案

**可能原因**：
1. Traces 数量不足 → 降低 `min_traces`
2. 所有 traces 都是成功的 → 检查是否有真实的失败案例
3. 置信度阈值太高 → 调整 `_merge_proposals` 中的 `0.6` 阈值

**调试方法**：
```python
# 检查 traces 分布
traces = await store.get_traces(skill_name="dev-process-backend")
from collections import Counter
outcomes = Counter(t.execution_outcome.value for t in traces)
print(outcomes)  # {'success': 80, 'failure': 20}
```

### 问题：验证总是失败

**可能原因**：
1. 测试用例与 skill 不匹配 → 更新测试用例
2. 阈值设置太高 → 降低 `test_threshold`
3. 启发式评分不准确 → 实现自定义 `_execute_test_case`

**调试方法**：
```python
# 查看详细验证结果
result = await gate.validate(proposal, test_cases)
print(f"Score delta: {result.score_delta}")
print(f"Test results: {result.test_results}")
print(f"Failed cases: {result.failed_cases}")
```

### 问题：冲突提案过多

**可能原因**：
1. Traces 来自不同使用场景 → 按场景分离分析
2. 规则本身有歧义 → 人工审查并澄清规则

**解决方法**：
```python
# 查看冲突详情
for conflict in merged.conflicts:
    prop1, prop2, reason = conflict
    print(f"Conflict: {prop1.proposal_id} vs {prop2.proposal_id}")
    print(f"Reason: {reason}")
```

## 扩展开发

### 添加新的分析策略

在 `OfflineEvolutionAgent` 中添加新的分析师：

```python
async def _analyze_special_case(self, trace: SkillEvolutionTrace) -> PatchProposal | None:
    """Custom analysis for specific patterns."""
    if "special_pattern" in trace.user_query:
        return PatchProposal(
            proposal_id=str(uuid.uuid4()),
            source_traces=[trace.trace_id],
            skill_name=trace.skill_name,
            operation="add",
            new_content="Special handling rule",
            rationale="Detected special pattern",
            confidence=0.7,
        )
```

### 自定义验证逻辑

继承 `SkillValidationGate` 并重写 `_execute_test_case`：

```python
class CustomValidationGate(SkillValidationGate):
    async def _execute_test_case(
        self,
        test_case: TestCase,
        skill_content: str,
    ) -> float:
        """Custom test execution logic."""
        # Instead of heuristic scoring, actually run the agent
        # and check if expected behavior occurred
        score = await self._run_agent_with_skill(test_case.input_query, skill_content)
        return 1.0 if self._check_expected_behavior(score, test_case.expected_behavior) else 0.0
```

### 集成 LLM 分析

传入 `model_provider` 启用智能分析：

```python
from agent_core.providers import OpenAIProvider

provider = OpenAIProvider(...)
agent = OfflineEvolutionAgent(store, model_provider=provider)
```

LLM 可用于：
- 更准确的根因分析
- 自然语言规则生成
- 冲突语义理解

## GRPO 风格路径相对进化（P0–P4）

在「成功/失败二值」之上，增加同目标多路径的组内相对比较（不训模型权重）：

1. Collector 记录 `PathStep` 工具链，并写入 `task_key`；`GroupRollout` 可打共享 `group_id`
2. `HybridReward` 混合启发式 / Judge / 人工，算标量 \(r\)
3. `build_groups` + `assign_advantages` 得到 \(A_i = r_i - \bar{r}\)
4. `distill_group` 将高/低优势蒸馏为 Path Preference 规则与正负例提案
5. `evaluate_acceptance_gates` 以 \(\Delta\bar{r}\) + 无关键回归 + 步数护栏放行
6. **P3** `GroupRollout`：同 query 采 G 次；Scene 开关 `ENABLE_GROUP_ROLLOUT`（默认关）
7. **P4** `cases/*.jsonl` + `SkillCaseRecallExtension`；开关 `ENABLE_SKILL_CASE_RECALL`（默认关）

设计说明见 [`docs/superpowers/specs/2026-07-23-skill-grpo-evolution-design.md`](superpowers/specs/2026-07-23-skill-grpo-evolution-design.md)。

```python
from agent_core.skill_evolution import (
    HybridReward,
    GroupRollout,
    build_groups,
    score_group,
    distill_group,
    evaluate_acceptance_gates,
    should_trigger_group_rollout,
)

groups = build_groups(traces, min_size=3)
for g in groups:
    await score_group(g)
    proposals = distill_group(g, tau=0.15)

# Active exploration (host supplies runner)
if should_trigger_group_rollout(enabled=True, consecutive_failures=2):
    await GroupRollout(collector=collector, g=3).run(query, runner)
```

Scene 环境变量：

| 变量 | 默认 | 含义 |
|------|------|------|
| `ENABLE_SKILL_EVOLUTION` | on | 轨迹采集 |
| `ENABLE_GROUP_ROLLOUT` | **off** | 主动 G 采样 |
| `GROUP_ROLLOUT_G` | 3 | 采样条数 |
| `ENABLE_SKILL_CASE_RECALL` | **off** | 注入 top-k 路径案例 |

## 参考资料

- **Trace2Skill**: [Distill Trajectory-Local Lessons into Transferable Agent Skills](https://arxiv.org/abs/xxxx.xxxxx)
- **EvoSkill**: [Automated Skill Discovery for Multi-Agent Systems](https://arxiv.org/abs/xxxx.xxxxx)
- **GRPO 映射（本仓库）**: 组内相对优势 → Skill 蒸馏，非权重更新

## API 参考

完整 API 文档参见源代码中的 docstrings：

- [`agent_core/skill_evolution/types.py`](../agent_core/skill_evolution/types.py)
- [`agent_core/skill_evolution/store.py`](../agent_core/skill_evolution/store.py)
- [`agent_core/skill_evolution/collector.py`](../agent_core/skill_evolution/collector.py)
- [`agent_core/skill_evolution/agent.py`](../agent_core/skill_evolution/agent.py)
- [`agent_core/skill_evolution/validation.py`](../agent_core/skill_evolution/validation.py)
- [`agent_core/skill_evolution/reward.py`](../agent_core/skill_evolution/reward.py)
- [`agent_core/skill_evolution/grouping.py`](../agent_core/skill_evolution/grouping.py)
- [`agent_core/skill_evolution/relative_score.py`](../agent_core/skill_evolution/relative_score.py)
- [`agent_core/skill_evolution/distiller.py`](../agent_core/skill_evolution/distiller.py)
