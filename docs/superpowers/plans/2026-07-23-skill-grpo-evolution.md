# Skill GRPO 理念进化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `skill_evolution` 上落地组内相对打分与路径蒸馏（Skill 层，不训权重），形成「轨迹 → \(r\)/\(A_i\) → 提案 → \(\Delta\bar{r}\) 门控写回」闭环。

**Architecture:** 扩展 `SkillEvolutionTrace` 为带 `steps` 的路径轨迹；新增 `reward` / `grouping` / `relative_score`；扩展 Distiller 与 ValidationGate；主动采样（P3）与案例召回（P4）另开阶段。

**Tech Stack:** Python 3.11+, pytest-asyncio, 现有 Extension / AgentEvent

**Spec:** `docs/superpowers/specs/2026-07-23-skill-grpo-evolution-design.md`

**范围：** 本计划覆盖 **P0–P2**（最小闭环）。P3/P4 见 spec §10，完成 P2 后再开独立计划。

**状态（2026-07-23）：** P0–P2 已实现，`pytest tests/skill_evolution/` 88 passed。

---

## 文件结构

### 新建

| 文件 | 职责 |
|------|------|
| `agent_core/skill_evolution/reward.py` | HybridReward：\(r_h\) / \(r_j\) / \(r_u\) 可插拔 |
| `agent_core/skill_evolution/grouping.py` | `task_key` 归一化 + 离线成组 |
| `agent_core/skill_evolution/relative_score.py` | 组内 \(A_i\) |
| `agent_core/skill_evolution/distiller.py` | 高/低优势 → 规则/案例提案 |
| `tests/skill_evolution/test_*.py` | 对应单测与 `test_grpo_pipeline.py` |

### 修改

| 文件 | 修改 |
|------|------|
| `types.py` / `collector.py` / `store.py` | 路径字段与事件采集 |
| `validation.py` / `agent.py` / `__init__.py` | 门控、蒸馏接线、导出 |

---

### Tasks P0–P2

- [x] Task 1: PathStep + Trace 扩展字段
- [x] Task 2: Store 序列化新字段
- [x] Task 3: Collector 累积 ToolExecution → steps
- [x] Task 4: HybridReward
- [x] Task 5: grouping + relative_score
- [x] Task 6: Distiller
- [x] Task 7: ValidationGate \(\Delta\bar{r}\) + 护栏
- [x] Task 8: OfflineEvolutionAgent 接线 + 导出

## P3/P4（本计划不做）

- [ ] P3：Scene 触发 GroupRollout（G 次采样）
- [ ] P4：提示词 top-k 案例注入
