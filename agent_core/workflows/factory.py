"""install_workflows — register run_workflow and return WorkflowHandle."""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.session.harness import AgentHarness
from agent_core.session.store import SessionStore
from agent_core.session.tool_utils import resolve_tool_name
from agent_core.tools.base import ToolRegistry
from agent_core.workflows.loader import WorkflowLoader
from agent_core.workflows.runner import WorkflowRunner
from agent_core.workflows.store import WorkflowStore
from agent_core.workflows.tool import RunWorkflowTool
from agent_core.workflows.types import WorkflowMeta, WorkflowOptions


@dataclass
class WorkflowHandle:
    runner: WorkflowRunner
    loader: WorkflowLoader
    store: WorkflowStore | None

    def list_workflows(self) -> list[WorkflowMeta]:
        return self.loader.list_meta()

    async def abort(self, run_id: str | None = None) -> None:
        await self.runner.abort(run_id)


def install_workflows(
    *,
    tool_registry: ToolRegistry,
    sub_agent_runner: SubAgentRunner,
    profile_registry: AgentProfileRegistry,
    session_store: SessionStore | None = None,
    session_id: str = "",
    owner: str = "",
    options: WorkflowOptions | None = None,
    parent_harness: AgentHarness | None = None,
) -> WorkflowHandle:
    """Register run_workflow on tool_registry; return handle for abort/list."""
    opts = options or WorkflowOptions()
    loader = WorkflowLoader(
        search_paths=list(opts.search_paths),
        include_builtin_recipes=opts.include_builtin_recipes,
    )
    store: WorkflowStore | None = None
    if session_store is not None and session_id:
        store = WorkflowStore(
            session_store=session_store,
            session_id=session_id,
            owner=owner,
        )

    runner = WorkflowRunner(
        loader=loader,
        store=store,
        runner=sub_agent_runner,
        registry=profile_registry,
        options=opts,
        parent_harness=parent_harness,
    )

    tool = RunWorkflowTool(
        runner=runner,
        enable_dynamic_exec=opts.enable_dynamic_exec,
    )
    name = resolve_tool_name(tool)
    if tool_registry.get(name) is None:
        tool_registry.register(tool)

    if parent_harness is not None:
        existing = {
            resolve_tool_name(t, i) for i, t in enumerate(parent_harness.state.tools)
        }
        if name not in existing:
            parent_harness.state.tools = [*parent_harness.state.tools, tool]

    return WorkflowHandle(runner=runner, loader=loader, store=store)
