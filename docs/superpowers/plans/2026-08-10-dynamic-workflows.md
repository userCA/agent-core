# Dynamic Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `agent_core` 落地库级 Dynamic Workflows：受限 Python 编排运行时 + 静态 workflow 资产 + `run_workflow` 工具 + phase 级 checkpoint/resume + 六大编排模式 helpers，复用现有 `SubAgentRunner`，不改 `core/loop.py`。

**Architecture:** Harness-in-Tool。`install_workflows` 向编排器注入 `run_workflow`；脚本在 AST 沙箱中执行，通过 `WorkflowContext.agent/pipeline/phase/log` 调用 `multi_agent.SubAgentRunner`；中间状态写入 `CustomEntry(workflow_checkpoint)`，回传主编排器的仅有 tool 摘要与 `details.workflow`。

**Tech Stack:** Python 3.11+, pydantic, pytest-asyncio, 现有 `FakeProvider` / `SubAgentRunner`

**Spec:** `docs/superpowers/specs/2026-08-10-dynamic-workflows-design.md`  
**背景:** `docs/Dynamic-Workflows.md`

---

## 文件结构

### 新建

| 文件 | 职责 |
|------|------|
| `agent_core/workflows/__init__.py` | 公共导出 |
| `agent_core/workflows/types.py` | Meta / Options / Checkpoint / Progress / RunResult |
| `agent_core/workflows/errors.py` | WorkflowError / SandboxError / CheckpointError / QuotaExceeded |
| `agent_core/workflows/sandbox.py` | AST 校验 + 构建受限 globals |
| `agent_core/workflows/runtime.py` | `WorkflowContext`（phase/log/agent/pipeline） |
| `agent_core/workflows/store.py` | `WorkflowStore` + CustomEntry 读写 |
| `agent_core/workflows/loader.py` | 发现与加载 `.pi/workflows/*.py` 与包内 recipes |
| `agent_core/workflows/runner.py` | `WorkflowRunner`：校验→执行→checkpoint→进度 |
| `agent_core/workflows/patterns.py` | 六大模式 helpers |
| `agent_core/workflows/tool.py` | `RunWorkflowTool` |
| `agent_core/workflows/factory.py` | `install_workflows` / `WorkflowHandle` |
| `agent_core/workflows/recipes/fanout_synthesize.py` | 内置配方 |
| `agent_core/workflows/recipes/adversarial_review.py` | 内置配方 |
| `tests/workflows/test_sandbox.py` | 沙箱允许/拒绝 |
| `tests/workflows/test_runtime_primitives.py` | agent/pipeline/phase |
| `tests/workflows/test_store.py` | checkpoint 持久化 |
| `tests/workflows/test_loader.py` | 资产发现 |
| `tests/workflows/test_runner_checkpoint.py` | 跑通 + resume |
| `tests/workflows/test_patterns.py` | 模式 helpers |
| `tests/workflows/test_tool_factory.py` | tool + 与 multi_agent 组合 |
| `tests/workflows/fixtures/sample_ok.py` | 合法样例 |
| `tests/workflows/fixtures/sample_bad_import.py` | 非法 import |

### 修改

| 文件 | 修改 |
|------|------|
| （无强制修改 multi_agent） | 若需 `schema` 结构化输出，**优先在 workflows 层用 prompt 约束 + JSON 解析**；不阻塞在改 Runner |
| `docs/design.md` | P5：增加 workflows 小节与包布局条目 |
| `docs/development-log/2026-08-10.md` | 提交时追加变更摘要 |

### 明确不改

- `agent_core/core/loop.py`
- `agent_core/planning/*`（正交，不做自动双写）
- Scene 前端 UI（本计划库完备验收不含；进度载荷形状在 spec 已定，Scene 另开）

---

## 依赖与组合约定

```
create_multi_agent_harness(...) -> (harness, ma_handle)
install_workflows(
    tools=harness 所用 registry,
    runner=ma_handle.runner,
    registry=ma_handle.registry,
    ...
)
```

`run_workflow` 与 `delegate_task` 可并存。Workflow 内部 **禁止** 再调 `run_workflow`（depth=0）；子 agent 默认仍 `allow_nested_delegate=False`。

---

## Phase P0 — 类型、沙箱、Runtime 原语

### Task 1: types + errors

**Files:**
- Create: `agent_core/workflows/types.py`, `errors.py`, `__init__.py`
- Test: `tests/workflows/test_types_roundtrip.py`（可并入 test_store；本 task 做最小 pydantic roundtrip）

- [x] **Step 1: 写入类型定义**

`agent_core/workflows/types.py` 至少包含：

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


WorkflowStatus = Literal["running", "completed", "failed", "aborted", "paused"]


class WorkflowMeta(BaseModel):
    name: str
    description: str = ""
    phases: list[str] = Field(default_factory=list)


class WorkflowOptions(BaseModel):
    search_paths: list[str] = Field(default_factory=lambda: ["./.pi/workflows"])
    include_builtin_recipes: bool = True
    max_agent_invocations: int = 100
    enable_dynamic_exec: bool = False
    auto_checkpoint_phases: bool = True
    model_config = {"arbitrary_types_allowed": True}
    # runner / registry 在 Options 数据类或 factory 参数中注入（见 Task 8）
    # 推荐：WorkflowOptions 只保留纯配置；runner/registry 作 factory 独立参数


class WorkflowProgress(BaseModel):
    type: Literal["workflow"] = "workflow"
    run_id: str
    name: str
    status: WorkflowStatus
    phase: str | None = None
    phases: list[str] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)
    progress: dict[str, int] = Field(default_factory=dict)
    error_message: str | None = None
    result: Any | None = None


class WorkflowCheckpoint(BaseModel):
    run_id: str
    workflow_name: str
    status: WorkflowStatus
    current_phase: str | None = None
    completed_phases: list[str] = Field(default_factory=list)
    phase_outputs: dict[str, Any] = Field(default_factory=dict)
    args: dict[str, Any] = Field(default_factory=dict)
    agent_invocation_count: int = 0
    updated_at: float = 0.0
    owner: str = ""
    session_id: str = ""
    log: list[str] = Field(default_factory=list)


class WorkflowRunResult(BaseModel):
    run_id: str
    name: str
    status: WorkflowStatus
    result: Any | None = None
    error_message: str | None = None
    checkpoint: WorkflowCheckpoint | None = None
```

`errors.py`：

```python
class WorkflowError(Exception):
    """Base workflow error."""


class SandboxError(WorkflowError):
    """Script failed AST/sandbox validation."""


class CheckpointError(WorkflowError):
    """Checkpoint missing or incompatible."""


class QuotaExceeded(WorkflowError):
    """max_agent_invocations exceeded."""
```

- [x] **Step 2: `__init__.py` 导出 Meta/Options/Progress/Checkpoint/RunResult/Errors（后续 task 再补 runner）**

- [x] **Step 3: 最小测试**

```python
# tests/workflows/test_types_roundtrip.py
from agent_core.workflows.types import WorkflowCheckpoint

def test_checkpoint_roundtrip():
    c = WorkflowCheckpoint(
        run_id="r1",
        workflow_name="demo",
        status="running",
        completed_phases=["a"],
        phase_outputs={"a": {"ok": True}},
        args={"x": 1},
        agent_invocation_count=2,
        updated_at=1.0,
    )
    data = c.model_dump()
    assert WorkflowCheckpoint.model_validate(data).run_id == "r1"
```

- [x] **Step 4: `pytest tests/workflows/test_types_roundtrip.py -v` PASS**

- [x] **Step 5: Commit** `feat(workflows): add types and errors`

---

### Task 2: AST 沙箱

**Files:**
- Create: `agent_core/workflows/sandbox.py`
- Test: `tests/workflows/test_sandbox.py`
- Fixtures: `tests/workflows/fixtures/sample_ok.py`, `sample_bad_import.py`

- [x] **Step 1: 写失败测试**

```python
# tests/workflows/test_sandbox.py
import pytest
from agent_core.workflows.sandbox import validate_workflow_source, SandboxError
# 若 SandboxError 从 errors 导入，保持一致

OK = '''
async def run(ctx):
    await ctx.phase("p1")
    ctx.log("hi")
    return {"ok": True}
'''

BAD = '''
import os
async def run(ctx):
    return os.getcwd()
'''

def test_accepts_simple_async_run():
    validate_workflow_source(OK)  # no raise

def test_rejects_import():
    with pytest.raises(SandboxError):
        validate_workflow_source(BAD)

def test_rejects_dunder_attr():
    src = '''
async def run(ctx):
    return ctx.__class__
'''
    with pytest.raises(SandboxError):
        validate_workflow_source(src)
```

- [x] **Step 2: 实现 `validate_workflow_source(source: str) -> ast.AST`**

规则（与 spec §6 一致）：

- walk AST：禁止 `ast.Import` / `ast.ImportFrom`
- 禁止 `Call` 到名字：`eval`, `exec`, `compile`, `__import__`, `open`, `breakpoint`, `getattr`, `globals`, `locals`, `vars`, `dir`
- 禁止 `Attribute` 且 `attr.startswith("__")`
- 允许其余控制流与 `async def` / `Await`

- [x] **Step 3: 实现 `build_sandbox_globals(ctx, args, *, extras: dict | None) -> dict`**

注入：`ctx`, `args`（浅拷贝）、安全 builtins 白名单、`json.dumps`/`json.loads`（可挂在 `json` 简易 namespace对象上）、以及后续 `patterns` 选中导出。

**不要**把真实 `__builtins__` 整包塞入。

- [x] **Step 4: `pytest tests/workflows/test_sandbox.py -v` PASS**

- [x] **Step 5: Commit** `feat(workflows): add AST sandbox validation`

---

### Task 3: WorkflowContext 原语

**Files:**
- Create: `agent_core/workflows/runtime.py`
- Test: `tests/workflows/test_runtime_primitives.py`
- 依赖：现有 `SubAgentRunner` / `AgentProfileRegistry` / `FakeProvider` 测试夹具（参考 `tests/multi_agent/test_sub_agent_runner.py`）

- [x] **Step 1: 写失败测试（用 FakeProvider + 最小 multi_agent 装配）**

覆盖：

1. `phase("a")` 更新 `current_phase`，触发 progress callback  
2. `log("x")` 追加到 log 列表（有上限，如 200 条，FIFO 丢弃旧）  
3. `agent("task", profile="worker")` 增加 `agent_invocation_count`，返回 `response_text`  
4. 超 `max_agent_invocations` 抛 `QuotaExceeded`  
5. `pipeline([1,2,3], fn)` 对每项调用，保持顺序结果列表（内部可并行，结果按 index 排序）

示意：

```python
@pytest.mark.asyncio
async def test_pipeline_preserves_order(runtime_ctx):
    async def fn(item, index):
        return item * 10
    out = await runtime_ctx.pipeline([1, 2, 3], fn)
    assert out == [10, 20, 30]
```

- [x] **Step 2: 实现 `WorkflowContext`**

关键签名：

```python
class WorkflowContext:
    def __init__(
        self,
        *,
        run_id: str,
        workflow_name: str,
        phases: list[str],
        args: dict[str, Any],
        runner: SubAgentRunner,
        registry: AgentProfileRegistry,
        parent_harness: AgentHarness,
        max_agent_invocations: int = 100,
        on_progress: ProgressCallback | None = None,
        resume: WorkflowCheckpoint | None = None,
    ) -> None: ...

    async def phase(self, name: str) -> None: ...
    def log(self, message: str) -> None: ...
    async def agent(
        self,
        prompt: str,
        *,
        profile: str | None = None,
        label: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> Any: ...
    async def pipeline(
        self,
        items: list[Any],
        map_fn: Callable[..., Awaitable[Any]],
        *,
        concurrency: int | None = None,
    ) -> list[Any]: ...
```

实现要点：

- `agent`：解析 profile（缺省时用 registry 中名为 `default` 的 profile，若无则用第一个；若 registry 空则 fail）→ `runner.run_single`（或现有等价 API；若只有 `run(mode=...)` 则走 single）  
- `schema` 非空：在 prompt 末尾追加「只输出符合 schema 的 JSON」+ 解析 JSON；解析失败再 retry **1** 次；仍失败则返回 `{"raw": text, "parse_error": ...}`（不要静默吞）  
- Resume：若 `name in completed_phases`，`phase()` 直接 return 且不重复跑该 phase 内逻辑——**注意**：脚本是线性的，resume 由 **Runner** 在加载时注入 `phase_outputs` 并让脚本用约定方式跳过。首版采用更简单策略（见 Task 6）：Runner 在 resume 时把 `completed_phases` / `phase_outputs` 放进 `ctx`，脚本作者用：

```python
async def run(ctx):
    if not ctx.is_phase_done("fanout"):
        await ctx.phase("fanout")
        out = await ctx.pipeline(...)
        ctx.set_phase_output("fanout", out)
    else:
        out = ctx.get_phase_output("fanout")
```

为此 Context 需提供：`is_phase_done` / `set_phase_output` / `get_phase_output`。  
`phase()` 进入新 phase 时若 `auto_checkpoint`，由 Runner 钩子保存（Context 发事件即可）。

- [x] **Step 3: `pytest tests/workflows/test_runtime_primitives.py -v` PASS**

- [x] **Step 4: Commit** `feat(workflows): add WorkflowContext primitives`

---

## Phase P1 — Loader、Store、Runner、Tool、Factory

### Task 4: WorkflowStore（CustomEntry）

**Files:**
- Create: `agent_core/workflows/store.py`
- Test: `tests/workflows/test_store.py`

常量：`WORKFLOW_CHECKPOINT_TYPE = "workflow_checkpoint"`

- [x] **Step 1: 测试**

```python
@pytest.mark.asyncio
async def test_save_and_load_latest_checkpoint(inmemory_store):
    ws = WorkflowStore(session_store=inmemory_store, session_id="s1", owner="u1")
    await inmemory_store.create_session("s1", SessionHeader(...))
    cp = WorkflowCheckpoint(run_id="r1", workflow_name="demo", status="running", updated_at=1.0)
    await ws.save_checkpoint(cp)
    loaded = await ws.load_checkpoint("r1")
    assert loaded is not None
    assert loaded.workflow_name == "demo"

@pytest.mark.asyncio
async def test_load_missing_returns_none(inmemory_store):
    ...
```

参考 `PlanStore` 的 append `CustomEntry` 模式（`agent_core/planning/store.py`）。

- [x] **Step 2: 实现 `save_checkpoint` / `load_checkpoint(run_id)` / `list_checkpoints()`**

- 每次 save append 新 CustomEntry（与 Plan 一样，最新覆盖语义用扫描最后一条匹配 `run_id`）  
- data 内冗余 `owner` / `session_id`

- [x] **Step 3: pytest PASS → Commit** `feat(workflows): persist checkpoints via CustomEntry`

---

### Task 5: Loader（资产发现）

**Files:**
- Create: `agent_core/workflows/loader.py`
- Create: `agent_core/workflows/recipes/__init__.py`（可空）
- Test: `tests/workflows/test_loader.py`
- Fixture workflows under `tests/workflows/fixtures/`

约定：

- 文件：`*.py`  
- 必须导出 `meta`（dict 或可 model_validate）与 `async def run(ctx):`  
- 名称解析：`meta["name"]` 优先，否则 stem  
- 搜索：`options.search_paths` + 可选 builtin `agent_core/workflows/recipes/`

- [x] **Step 1: 测试 list / get / missing / bad sandbox file skipped or error**

```python
def test_loader_lists_fixture(tmp_path):
    # write sample_ok.py with meta + run
    loader = WorkflowLoader(search_paths=[str(tmp_path)])
    names = loader.list_names()
    assert "sample-ok" in names
    spec = loader.get("sample-ok")
    assert spec.meta.name == "sample-ok"
    assert "async def run" in spec.source
```

- [x] **Step 2: 实现 `WorkflowSpec(meta, source, path)` + `WorkflowLoader`**

加载时调用 `validate_workflow_source`；失败的文件：`list` 可跳过并记 diagnostic，或 `get` 时抛 `SandboxError`（推荐：**list 跳过 + logger.warning；get 抛错**）。

- [x] **Step 3: pytest PASS → Commit** `feat(workflows): add workflow asset loader`

---

### Task 6: WorkflowRunner

**Files:**
- Create: `agent_core/workflows/runner.py`
- Test: `tests/workflows/test_runner_checkpoint.py`

- [x] **Step 1: 测试跑通静态脚本**

```python
@pytest.mark.asyncio
async def test_runner_executes_sample(workflow_env):
    runner, loader, ... = workflow_env
    result = await runner.run(name="sample-ok", args={"n": 2})
    assert result.status == "completed"
    assert result.result["ok"] is True
```

样例脚本逻辑：`pipeline` 长度 `args["n"]` 的 agent 调用（FakeProvider 预排脚本）。

- [x] **Step 2: 测试 checkpoint + resume**

```python
@pytest.mark.asyncio
async def test_resume_skips_completed_phase(workflow_env):
    # 第一次：跑完 phase A 后人工 abort 或注入失败
    # 更可测做法：script 在 phase B 抛错；断言 checkpoint.completed_phases == ["A"]
    # 第二次 resume：phase A 的 set_phase_output 被恢复；FakeProvider 仅需为 phase B 排队
    ...
```

- [x] **Step 3: 实现 Runner**

伪流程：

```text
run(name, args, resume_run_id=None, inline_source=None, on_progress=None):
  1. 解析 source（loader.get 或 inline 若 enable_dynamic_exec）
  2. validate_workflow_source
  3. run_id = resume or new uuid
  4. load checkpoint if resume
  5. build WorkflowContext(...)
  6. globals = build_sandbox_globals(ctx, args, extras={patterns...})
  7. exec compile(ast) 得到 run 协程函数
  8. try: result = await run(ctx)
     except Cancelled / abort: status=aborted
     except QuotaExceeded / Exception: status=failed; save checkpoint
  9. status=completed; save checkpoint; emit progress; return WorkflowRunResult
```

Abort：`WorkflowRunner` 持有 `asyncio.Event` / flag；`ctx.agent` 开头检查；`abort()` 调 `SubAgentRunner.abort_all()`。

- [x] **Step 4: pytest PASS → Commit** `feat(workflows): add WorkflowRunner with checkpoint resume`

---

### Task 7: RunWorkflowTool

**Files:**
- Create: `agent_core/workflows/tool.py`
- Test: 可先放在 `test_tool_factory.py` 一部分

- [x] **Step 1: 实现工具**

对齐 `DelegateTaskTool` 风格：

- `definition.name = "run_workflow"`  
- parameters: `name`, `args`, `resume_run_id`, `inline_source`（后两者可选）  
- `execute`：调用 `WorkflowRunner.run`，`on_progress` → `ctx.on_update(ToolResult(details={"workflow": progress.model_dump()}))`  
- 最终 `ToolResult`：`content=[TextContent(摘要)]`，`details={"workflow": final_progress}`  
- `inline_source` 在 `enable_dynamic_exec=False` 时返回 failed 说明  

摘要格式建议：`[workflow:{name}] status={status} phase={phase}\n{short_result}`，控制在 ~2k chars；完整 result 放 details。

- [x] **Step 2: 单测 tool execute 成功路径（FakeProvider）**

- [x] **Step 3: Commit** `feat(workflows): add run_workflow tool`

---

### Task 8: install_workflows Factory

**Files:**
- Create: `agent_core/workflows/factory.py`
- Update: `agent_core/workflows/__init__.py` 完整导出
- Test: `tests/workflows/test_tool_factory.py`

- [x] **Step 1: API**

```python
@dataclass
class WorkflowHandle:
    runner: WorkflowRunner
    loader: WorkflowLoader
    store: WorkflowStore

    def list_workflows(self) -> list[WorkflowMeta]: ...
    async def abort(self, run_id: str | None = None) -> None: ...


def install_workflows(
    *,
    tool_registry: ToolRegistry,
    sub_agent_runner: SubAgentRunner,
    profile_registry: AgentProfileRegistry,
    parent_harness: AgentHarness,
    session_store: SessionStore | None = None,
    session_id: str = "",
    owner: str = "",
    options: WorkflowOptions | None = None,
) -> WorkflowHandle:
    """Register run_workflow on tool_registry; return handle."""
```

- [x] **Step 2: 集成测试**

```python
@pytest.mark.asyncio
async def test_install_with_multi_agent_combo():
    harness, ma = create_multi_agent_harness(...)
    # ensure delegate_task present
    handle = install_workflows(
        tool_registry=...,
        sub_agent_runner=ma.runner,
        profile_registry=ma.registry,
        parent_harness=harness,
        session_store=store,
        session_id=sid,
        options=WorkflowOptions(search_paths=[fixture_dir], include_builtin_recipes=False),
    )
    assert tool_registry.get("run_workflow") is not None
    assert tool_registry.get("delegate_task") is not None
    # optional: prompt harness to call run_workflow via FakeProvider scripted tool call
```

- [x] **Step 3: pytest `tests/workflows/` PASS → Commit** `feat(workflows): add install_workflows factory`

---

## Phase P2 — 强化恢复、配额、可观测性

### Task 9: 配额、进度字段、Abort 语义加固

**Files:**
- Modify: `runtime.py`, `runner.py`, `tool.py`
- Test: 扩展 `test_runner_checkpoint.py` / 新 `test_quota_abort.py`

- [x] **Step 1: 测试 `max_agent_invocations=2` 第三次 agent 失败且 checkpoint.status=failed**

- [x] **Step 2: 测试 `handle.abort()` 使 running run 变为 aborted（可用挂起的 FakeProvider / asyncio.sleep 模拟长任务）**

- [x] **Step 3: Progress 始终包含 `progress.completed_agents` / `total_agents`（pipeline 开始时设 total，每完成 +1）**

- [x] **Step 4: pytest PASS → Commit** `feat(workflows): harden quota, abort, and progress counters`

---

## Phase P3 — Patterns 与内置 Recipes

### Task 10: patterns.py 六大模式

**Files:**
- Create: `agent_core/workflows/patterns.py`
- Test: `tests/workflows/test_patterns.py`

每个 helper 用 FakeProvider 测 **至少 1 条路径**（不必穷尽分支）。

实现签名（锁死，避免后续任务命名漂移）：

```python
async def fanout_synthesize(
    ctx: WorkflowContext,
    items: list[Any],
    *,
    map_prompt: Callable[[Any, int], str],
    synthesize_prompt: Callable[[list[Any]], str],
    map_profile: str | None = None,
    synthesize_profile: str | None = None,
) -> Any: ...

async def adversarial_verify(
    ctx: WorkflowContext,
    draft: str,
    rubric: str,
    *,
    max_rounds: int = 2,
    author_profile: str | None = None,
    critic_profile: str | None = None,
) -> dict[str, Any]:
    """Returns {final, rounds: [{draft, critique, revised}], converged: bool}"""

async def generate_and_filter(
    ctx: WorkflowContext,
    n: int,
    *,
    gen_prompt: Callable[[int], str],
    score_prompt: Callable[[str], str],
    top_k: int = 1,
) -> list[Any]: ...

async def tournament(
    ctx: WorkflowContext,
    candidates: list[str],
    *,
    compare_prompt: Callable[[str, str], str],
    profile: str | None = None,
) -> str: ...

async def classify_and_execute(
    ctx: WorkflowContext,
    text: str,
    routes: dict[str, Callable[[WorkflowContext, str], Awaitable[Any]]],
    *,
    classify_prompt: Callable[[str], str] | None = None,
) -> Any: ...

async def loop_until(
    ctx: WorkflowContext,
    step: Callable[[WorkflowContext, int], Awaitable[Any]],
    done: Callable[[Any], bool],
    *,
    max_iters: int = 10,
) -> Any: ...
```

- [x] **Step 1: 先写 `adversarial_verify` 与 `fanout_synthesize` 测试 + 实现**（最高价值）  
- [x] **Step 2: 补齐其余四模式测试 + 实现**  
- [x] **Step 3: 沙箱 `extras` 注入 `patterns` 模块的上述六个函数（只读）**  
- [x] **Step 4: Commit** `feat(workflows): add six orchestration pattern helpers`

---

### Task 11: 内置 recipes

**Files:**
- Create: `agent_core/workflows/recipes/fanout_synthesize.py`
- Create: `agent_core/workflows/recipes/adversarial_review.py`
- Test: loader `include_builtin_recipes=True` 能 list 到二者；runner 能 dry-run（FakeProvider）

`fanout_synthesize.py` 示例结构：

```python
meta = {
    "name": "fanout-synthesize",
    "description": "Map items with sub-agents then synthesize",
    "phases": ["fanout", "synthesize"],
}

async def run(ctx):
    items = list(ctx.args.get("items") or [])
    await ctx.phase("fanout")
    if not ctx.is_phase_done("fanout"):
        partial = await patterns.fanout_synthesize(
            ctx,
            items,
            map_prompt=lambda it, i: f"Analyze: {it}",
            synthesize_prompt=lambda rows: "Synthesize:\n" + "\n".join(map(str, rows)),
        )
        # 若 fanout_synthesize 已含 synthesize，可拆 phase：
        # 更清晰：本 recipe 内手写 pipeline + synthesize 两段，便于 checkpoint
        ...
    return ctx.get_phase_output("synthesize")
```

建议 recipe **手写 phase 边界**（调用 `ctx.pipeline` + `ctx.agent`），patterns 用于应用代码；内置 recipe 保持可读、可教。

- [x] **Step 1: 两个 recipe + 测试**  
- [x] **Step 2: Commit** `feat(workflows): add builtin fanout and adversarial recipes`

---

## Phase P4 —（可选增强）动态脚本

> 库完备验收 **不依赖** 本 Phase。需要「对齐 Claude 即时编写」时再做。

### Task 12（Optional）: enable_dynamic_exec 路径

- [ ] `run_workflow(inline_source=...)` 在开关开启时：validate → 临时 exec → **不默认落盘**  
- [ ] 可选 `save_as` 参数写入 `search_paths[0]`  
- [ ] 测试：开关关拒绝；开关开跑通；恶意 import 拒绝  
- [ ] Commit `feat(workflows): optional inline workflow exec`

### Task 13（Optional）: generate_workflow 工具

- [ ] 另工具：主模型只产出脚本字符串 → sandbox validate → 返回预览；用户确认后再 save  
- [ ] 不与 `run_workflow` 混为同一工具  

---

## Phase P5 — 文档与收尾

### Task 14: 设计文档与开发日志

**Files:**
- Modify: `docs/design.md`（包布局增加 `workflows/`；§ 简述 Harness-in-Tool workflow）  
- Create/Update: `docs/development-log/2026-08-10.md`  
- Update: spec 状态 → `实施中` / `已落地`

- [x] 在 `docs/design.md` 增加与 multi_agent/planning 的边界说明（各 5–10 行即可）  
- [x] 开发日志记录：文件列表、类型（feat）、关联规则（Harness-in-Tool / 沙箱 / checkpoint）  
- [x] `pytest tests/workflows/ tests/multi_agent/ -q` 全绿（防回归）  

- [x] Commit `docs: document workflows module and development log`

---

## 建议实施顺序（工程师视角）

```text
Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 14
         └─(optional) 12 → 13
```

并行机会：Task 4（store）可与 Task 2/3 部分并行；Task 10 依赖 Task 3 完成。

---

## 测试策略总则

1. **一律 FakeProvider**，禁止默认单测打真实网络  
2. 装配 multi_agent 时复用 `tests/multi_agent/` 既有 helper；若无则在 `tests/workflows/conftest.py` 抽 `workflow_env` fixture  
3. TDD：每个 Task 先红后绿  
4. 不对 `loop.py` 写耦合测试  

`tests/workflows/conftest.py` 建议提供：

```python
@pytest.fixture
async def workflow_env(tmp_path):
    """InMemory store + FakeProvider + 1 profile + SubAgentRunner + loader path."""
    ...
```

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| Context offloading（中间态不进主 messages） | 6–8（tool 只回摘要） |
| Python DSL + AST 沙箱 | 2, 6 |
| `phase/log/agent/pipeline` | 3 |
| 静态资产 loader | 5, 11 |
| `run_workflow` + `install_workflows` | 7, 8 |
| Checkpoint / resume（phase 级） | 4, 6, 9 |
| 配额 / abort / progress | 9 |
| 六大 patterns | 10 |
| 内置 recipes | 11 |
| 与 multi_agent 组合 | 8 |
| 不改 core loop | 全程约束 |
| 动态生成（可选） | 12–13 |
| 文档 | 14 |

| Dynamic-Workflows.md 概念 | 本库映射 |
|---------------------------|----------|
| JS `agent()` / `pipeline()` / `phase()` / `log()` | `WorkflowContext` |
| `.claude/workflows/*.js` | `.pi/workflows/*.py` + builtin recipes |
| 上下文卸载 | runtime 变量 + checkpoint + tool 摘要 |
| 对抗验证等六模式 | `patterns.py` |
| `/workflows` UI | 非目标；`details.workflow` 载荷预留 |
| 16/1000 并发 | `max_concurrent_agents` + `max_agent_invocations` |
| 即时编写脚本 | P4 optional |

---

## 完成定义（DoD）

当且仅当：

1. `pytest tests/workflows/ -q` 全绿  
2. `pytest tests/multi_agent/ -q` 无回归  
3. Spec §10 验收标准 1–7 均有对应用例  
4. `docs/superpowers/specs/2026-08-10-dynamic-workflows-design.md` 状态更新  
5. P4 未做不影响 DoD  

---

## 后续可开但不在本计划

- Scene：`event: workflow` SSE + 进度树 UI（对标 `/workflows`）  
- item 级 checkpoint  
- worktree / 文件系统隔离  
- PlanStore 自动桥接（workflow phase → plan step）  
- Workflow 市场与可视化
