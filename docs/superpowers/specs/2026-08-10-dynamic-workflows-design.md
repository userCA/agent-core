# Dynamic Workflows 设计规格（库级）

> 日期：2026-08-10  
> 状态：已落地  
> 范围：`agent_core` 库内一等 Workflow 能力；Scene 仅保留可选接入点，**不作为本规格验收门槛**。  
> 背景：`docs/Dynamic-Workflows.md`（Claude Dynamic Workflows 机制整理）  
> 关联：`docs/superpowers/specs/2026-07-20-multi-agent-harness-design.md`、`docs/superpowers/specs/2026-07-20-plan-execute-design.md`

---

## 1. 目标

把 Claude Dynamic Workflows 的**核心价值**落到 `agent-core`：

1. **Context Offloading** — 编排计划与中间结果住在脚本运行时 / checkpoint，不堆进主编排器对话上下文  
2. **大规模可控 Fan-out** — `pipeline(items, …)` 级批量并行，复用现有 `SubAgentRunner` 信号量  
3. **可验证编排模式** — 对抗验证、扇出综合、锦标赛等作为库级原语或配方  
4. **Workflow 一等资产** — 可发现、可版本化、可复用的 Python 工作流文件  
5. **Checkpoint / Resume** — 长任务可中断并从 phase 边界恢复  

**非目标（本规格明确不做）：**

- 复刻 Claude Code 的 JavaScript 运行时 / `/workflows` CLI / ultracode  
- 改写 `agent_core/core/loop.py` 或引入 DAG 调度引擎  
- 进程级 / worktree 级隔离（仍用现有 in-process sub-harness）  
- Scene 完整进度 UI（可另开规格；库需暴露进度事件载荷）  
- 默认开启高并发（默认保守并发，与现有 `max_concurrent_agents` 对齐）

---

## 2. 问题陈述

现状（已有）：

| 能力 | 位置 | 局限 |
|------|------|------|
| `delegate_task` single/parallel/chain | `multi_agent/` | 计划在 LLM 上下文；一次 tool call 列 tasks，非脚本工厂 |
| Plan-Execute | `planning/` | 进度可视化，**不**自动驱动 Runner |
| Artifacts / Working Memory | `artifacts/` / `working_memory/` | 结果卸载，非编排脚本 |
| Compaction | `compaction/` | 摘要后仍会丢约束 |

相对 Dynamic Workflows：**计划持有者仍是 LLM**，不是代码。长任务下偷懒、自我偏好、目标漂移仍会放大。

---

## 3. 架构决策

### 3.1 选定方案：Harness-in-Tool + Python Workflow Runtime

```
Orchestrator AgentHarness
  └── run_workflow tool
        └── WorkflowRunner
              ├── 加载静态资产 / 内联脚本
              ├── WorkflowRuntime（受限 Python 命名空间）
              │     phase / log / agent / pipeline / args / checkpoint hooks
              ├── 调用 SubAgentRunner（复用 multi_agent）
              ├── WorkflowStore（CustomEntry checkpoint）
              └── 进度 → ToolResult.details.workflow
```

与 multi_agent / planning 一致：**不改 core loop**；能力以 Tool + 会话附属状态注入。

### 3.2 语言选择：Python DSL，不是 JS

| 选项 | 结论 |
|------|------|
| JS（对齐 Claude） | 拒绝：引入第二运行时，与库栈不一致 |
| YAML-only 声明式 | 拒绝：表达循环/对抗/锦标赛笨拙 |
| **受限 Python 脚本** | 选定：`async` 友好，可直接 `await agent()` / `await pipeline()` |

安全：默认 **AST 白名单沙箱**（禁止 import / open / getattr 危险形态等）；宿主可注入只读 helpers。

### 3.3 与现有模块边界

| 模块 | 关系 |
|------|------|
| `multi_agent.SubAgentRunner` | Workflow 的**唯一** agent 执行内核（首版） |
| `multi_agent.AgentProfileRegistry` | `agent(profile=…)` 解析人设/模型/工具 |
| `planning.PlanStore` | **正交**；Workflow 自有 phase 树，不自动写 Plan（可选桥接 extension 后置） |
| `artifacts` | 子 agent 大输出可外置；workflow 终稿可写 artifact ref |
| `extensions` | 配额、abort、审计钩子；不承载编排逻辑 |

**依赖方向：**

```
workflows → multi_agent → session/core/tools
workflows → session (CustomEntry)
workflows ↛ planning（可选后续桥接）
planning ↛ workflows
```

### 3.4 动态 vs 静态

采用 **静态资产优先，动态生成可选二期**：

1. **P0–P2**：`.pi/workflows/*.py` 静态配方 + `run_workflow(name=…)`  
2. **P3**：模式 helpers（adversarial / tournament / …）  
3. **P4（可选）**：`generate_workflow` 或主模型写出脚本 → 校验 → 落盘/试跑  

库能力「完备」的验收线定在 **P0–P3**；P4 为增强。

---

## 4. 包布局

```
agent_core/workflows/
├── __init__.py              # 公共导出
├── types.py                 # WorkflowMeta, RunState, PhaseRecord, Checkpoint, Options
├── errors.py                # WorkflowError, SandboxError, CheckpointError
├── sandbox.py               # AST 校验 + 受限 exec 命名空间
├── runtime.py               # WorkflowContext: phase/log/agent/pipeline/args
├── runner.py                # WorkflowRunner: load → run → checkpoint → progress
├── store.py                 # WorkflowStore + CustomEntry(workflow_checkpoint)
├── loader.py                # 发现 .pi/workflows / 包内 recipes
├── patterns.py              # 六大模式 helpers（库函数，非 LLM）
├── tool.py                  # RunWorkflowTool
├── factory.py               # install_workflows / create_workflow_handle
└── recipes/                 # 内置示例配方（可选）
    ├── fanout_synthesize.py
    └── adversarial_review.py
```

测试：

```
tests/workflows/
├── test_sandbox.py
├── test_runtime_primitives.py
├── test_runner_checkpoint.py
├── test_loader.py
├── test_patterns.py
├── test_tool_factory.py
└── fixtures/
    └── sample_workflow.py
```

---

## 5. 公共 API（契约）

### 5.1 脚本侧（Workflow 作者可见）

```python
# meta 必须由脚本导出
meta = {
    "name": "fanout-synthesize",
    "description": "...",
    "phases": ["classify", "fanout", "synthesize"],
}

# 运行时注入（不可由脚本覆盖）
# args: dict          — run_workflow 传入
# ctx: WorkflowContext

await ctx.phase("fanout")
ctx.log("starting batch")
item = await ctx.agent(
    "分析此文件…",
    profile="researcher",   # 可选，默认 default profile
    label="file-a",
    schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
)
results = await ctx.pipeline(
    items,
    map_fn,                 # async (item, index) -> Any
    concurrency=None,       # None → 用 runner 全局信号量
)
```

约束：

- 脚本顶层可为 sync 定义 + 一个 `async def main(ctx, args): ...` **或** 模块级 awaitable 入口 `async def run(ctx): ...`（二选一，loader 约定见实施计划）  
- **约定入口**：`async def run(ctx: WorkflowContext) -> Any`  
- 返回值序列化为 JSON-friendly；不可 JSON 的类型写入 artifact 并返回 ref  

### 5.2 宿主侧

```python
from agent_core.workflows import (
    WorkflowOptions,
    install_workflows,
    WorkflowHandle,
)

handle = install_workflows(
    harness_or_tools=...,
    options=WorkflowOptions(
        runner=sub_agent_runner,          # 必填：复用 multi_agent runner
        registry=profile_registry,        # 必填
        search_paths=["./.pi/workflows"],
        max_agent_invocations=100,        # 单次 run 上限（防失控）
        enable_dynamic_exec=False,        # 内联脚本开关，默认关
    ),
    session_store=store,
    session_id=...,
    owner=...,
)
# 注册 run_workflow 工具；返回 WorkflowHandle(abort, list_workflows, get_run)
```

### 5.3 工具 `run_workflow`

参数：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 资产名（与 meta.name 或文件名匹配） |
| `args` | object | 传给脚本的 args |
| `resume_run_id` | string? | 从 checkpoint 恢复 |
| `inline_source` | string? | 仅当 `enable_dynamic_exec` 时允许 |

进度：`ToolResult.details.workflow` 形状：

```json
{
  "type": "workflow",
  "run_id": "...",
  "name": "fanout-synthesize",
  "status": "running|completed|failed|aborted|paused",
  "phase": "fanout",
  "phases": ["classify", "fanout", "synthesize"],
  "log": ["starting batch"],
  "progress": {"completed_agents": 3, "total_agents": 10},
  "error_message": null
}
```

终稿：`content` 为简短摘要；完整结构化结果放 `details.workflow.result`（过大则 artifact ref）。

### 5.4 Checkpoint

- `CustomEntry(custom_type="workflow_checkpoint", data=WorkflowCheckpoint)`  
- 粒度：**phase 边界**自动保存；`pipeline` 内按 batch 可选保存（默认 phase 级）  
- Resume：重跑时跳过已 `completed` 的 phase；未完成 phase 重做（首版不做细粒度 item 级 resume，文档标明）

```python
class WorkflowCheckpoint(BaseModel):
    run_id: str
    workflow_name: str
    status: Literal["running", "completed", "failed", "aborted", "paused"]
    current_phase: str | None
    completed_phases: list[str]
    phase_outputs: dict[str, Any]   # JSON-serializable
    args: dict[str, Any]
    agent_invocation_count: int
    updated_at: float
    owner: str = ""
    session_id: str = ""
```

---

## 6. 沙箱规则（首版）

**禁止：**

- 任何 `import` / `__import__` / `from … import`  
- 访问 `__builtins__` 中危险名：`open`, `eval`, `exec`, `compile`, `getattr`（对任意对象）, `globals`, `locals`, `breakpoint`  
- 属性访问名以 `__` 开头（除显式允许的 dunder 无）  

**允许：**

- 字面量、控制流、推导式、`async`/`await`、函数定义  
- 注入名：`ctx`, `args`, `meta`（只读拷贝）, 以及 `patterns` 模块导出的纯函数  
- 标准安全子集：`len`, `range`, `enumerate`, `zip`, `min`, `max`, `sum`, `sorted`, `list`, `dict`, `set`, `str`, `int`, `float`, `bool`, `isinstance`, `type`（只读）、`json`（注入只读 dumps/loads）

校验失败 → `SandboxError`，工具返回 failed，不执行。

---

## 7. 编排模式（patterns.py）

作为 **Python helpers**（在沙箱内可调用），不是独立服务：

| 模式 | 函数 | 行为摘要 |
|------|------|----------|
| Fan-out & Synthesize | `fanout_synthesize(ctx, items, map_prompt_fn, synthesize_prompt)` | pipeline + 一次综合 agent |
| Adversarial | `adversarial_verify(ctx, draft, rubric, *, max_rounds=2)` | 生成 → 反方 → 收敛或返回争议点 |
| Generate & Filter | `generate_and_filter(ctx, n, gen_fn, score_fn, top_k)` | 并行生成 → 过滤 |
| Tournament | `tournament(ctx, candidates, compare_fn)` | 两两比较至胜者 |
| Classify & Execute | `classify_and_execute(ctx, text, routes)` | 分类 agent → 路由调用 |
| Loop Until Done | `loop_until(ctx, step_fn, done_fn, *, max_iters)` | 有硬上限 |

Helpers 内部只调用 `ctx.agent` / `ctx.pipeline`，便于统一计数与进度。

---

## 8. 并发与配额

| 旋钮 | 默认 | 说明 |
|------|------|------|
| `SubAgentRunner.max_concurrent_agents` | 沿用现有（常 4） | 全局并行 |
| `WorkflowOptions.max_agent_invocations` | 100 | 单次 run 调用 `agent` 次数上限 |
| `pipeline` concurrency | None | None = 不另加层，只吃 Runner 信号量 |
| 生命周期总 agent 数 | 不设 1000 硬顶 | 用 `max_agent_invocations` 表达；可后续加 |

超限 → 失败并 checkpoint `failed`，已完成 phase 保留。

---

## 9. 错误、Abort、可观测性

- `WorkflowHandle.abort(run_id | None)` → runner 设 cancel flag + `SubAgentRunner.abort_all()`（仅当前 workflow 绑定的 active set；首版可简化为 abort_all 若单 run）  
- 进度只通过 `on_progress` → tool `details.workflow`；库不依赖 SSE  
- 结构化日志：`logging.getLogger("agent_core.workflows")`

---

## 10. 验收标准（库完备）

1. 无网络：`FakeProvider` 下可跑完 sample workflow（含 pipeline ≥3）  
2. 中间结果**不**进入 orchestrator `messages`（仅 tool result 摘要 + details）  
3. Checkpoint 写入 `CustomEntry`；`resume_run_id` 跳过已完成 phase  
4. 沙箱拒绝 `import os`  
5. `patterns.adversarial_verify` 至少 1 轮反方调用可测  
6. `install_workflows` 与 `create_multi_agent_harness` 可组合：同一 orchestrator 同时有 `delegate_task` + `run_workflow`  
7. `pytest tests/workflows/ -q` 全绿  
8. 设计文档与 `docs/Dynamic-Workflows.md` 的映射表写入计划文末  

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 沙箱逃逸 | AST 门禁 + 无 builtins 危险对象；持续用恶意脚本测试 |
| Token 爆炸 | `max_agent_invocations` + 默认低并发 + 文档强调成本 |
| 与 Plan 概念混淆 | 文档明确正交；不做自动双写 |
| Resume 语义不清 | 首版仅 phase 级；item 级标为非目标 |
| 动态脚本滥用 | `enable_dynamic_exec=False` 默认 |

---

## 12. 实施分期

| 期 | 内容 | 产出 |
|----|------|------|
| P0 | types / sandbox / runtime primitives | 可单测的 ctx.agent/pipeline |
| P1 | loader + runner + store + tool + factory | 静态 workflow 可跑通 |
| P2 | checkpoint / resume / abort / 配额 | 长任务可恢复 |
| P3 | patterns + 2 个内置 recipes | 模式完备 |
| P4 | （可选）动态脚本生成与校验 | 对齐 Claude「即时编写」 |
| P5 | 文档 / development-log / 可选 scene 事件映射说明 | 可交付 |

详细步骤见：`docs/superpowers/plans/2026-08-10-dynamic-workflows.md`
