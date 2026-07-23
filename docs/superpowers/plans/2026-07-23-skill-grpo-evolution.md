# Skill GRPO 理念进化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `skill_evolution` 上落地组内相对打分与路径蒸馏（Skill 层，不训权重），形成「轨迹 → \(r\)/\(A_i\) → 提案 → \(\Delta\bar{r}\) 门控写回」闭环。

**Architecture:** 扩展 `SkillEvolutionTrace` 为带 `steps` 的路径轨迹；新增 `reward` / `grouping` / `relative_score`；扩展 Distiller 与 ValidationGate；主动采样（P3）与案例召回（P4）另开阶段。

**Tech Stack:** Python 3.11+, pytest-asyncio, 现有 Extension / AgentEvent

**Spec:** `docs/superpowers/specs/2026-07-23-skill-grpo-evolution-design.md`

**范围：** 本计划覆盖 **P0–P2**（最小闭环）。P3/P4 见 spec §10，完成 P2 后再开独立计划。

**状态（2026-07-23）：** P0–P4 已实现，`pytest tests/skill_evolution/` 96 passed。

---

## 文件结构

### 新建（含 P3/P4）

| 文件 | 职责 |
|------|------|
| `reward.py` / `grouping.py` / `relative_score.py` / `distiller.py` | P0–P2 打分与蒸馏 |
| `group_rollout.py` | P3 主动 G 采样 |
| `cases.py` / `case_recall.py` | P4 案例存储与注入 |

---

### Tasks

- [x] Task 1–8: P0–P2
- [x] P3：GroupRollout + Scene 开关（默认关）
- [x] P4：cases jsonl + top-k recall 扩展（默认关）
