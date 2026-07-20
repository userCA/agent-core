# Plan-Execute 设计规格

> 日期：2026-07-20  
> 状态：已落地  
> 范围：库级显式 Plan/Todo + Scene（http_sse / h5）进度展示；与 `multi_agent` 正交可组合。

## 1. 目标

把 Plan / Todo / Step / Progress 提升为显式、可持久化、可 SSE 展示的状态。执行仍走现有 ReAct `run_agent_loop`，**不改** `loop.py`。

## 2. 选定方案

**Harness-in-Tool**：`manage_plan` 工具 + 会话内 `PlanStore` + `CustomEntry(plan_snapshot)` 落盘。

非目标：DAG 引擎、TaskDecomposer、强制 Planner/Executor 双 Agent、独立全局 Plan 表、改写 core。

## 3. 包布局

```
agent_core/planning/
├── types.py
├── store.py
├── plan_tool.py
├── context.py
├── factory.py          # install_planning
└── __init__.py
```

依赖：`planning → tools.base + session`；不依赖 `multi_agent`。

## 4. 落盘与用户隔离

- Plan 是 **Session 附属状态**；隔离 = `SessionHeader.owner`
- 每次变更 append `CustomEntry(custom_type="plan_snapshot")`
- 快照冗余 `owner` / `session_id`；鉴权仍靠 Scene owner 校验
- 云端换 SessionStore 后端即可，首版不建独立 plans 表

## 5. Scene

- http_sse：`event: plan`（从 `details.plan`）
- h5：`actionType: plan.update`（先于 content `phase` 分支）
- 前端 `PlanCard`；`manage_plan` 不走普通工具卡

## 6. 与 multi_agent

可同时注册 `manage_plan` + `delegate_task`；调度权仍在 LLM，PlanStore 不自动调 Runner。
