"""install_planning — register manage_plan + optional context extension."""

from __future__ import annotations

from typing import Any

from agent_core.planning.context import PlanningContextExtension
from agent_core.planning.plan_tool import ManagePlanTool
from agent_core.planning.store import PlanStore
from agent_core.planning.types import DEFAULT_PLANNING_HINT, PlanningOptions
from agent_core.session.store import SessionStore
from agent_core.session.tool_utils import resolve_tool_name
from agent_core.tools.base import ToolRegistry


async def install_planning(
    tool_registry: ToolRegistry,
    *,
    store: SessionStore | None = None,
    session_id: str = "",
    owner: str = "",
    options: PlanningOptions | None = None,
    extensions: list[Any] | None = None,
    restore: bool = True,
) -> tuple[PlanStore, ManagePlanTool, list[Any]]:
    """Register manage_plan on *tool_registry* and return store + tool + extensions.

    Appends PlanningContextExtension to *extensions* (or a new list).
    When *restore* is True, loads the latest plan_snapshot from the session.
    """
    opts = options or PlanningOptions()
    plan_store = PlanStore(
        session_store=store,
        session_id=session_id,
        owner=owner,
        persist=opts.persist,
    )
    if restore:
        await plan_store.load_latest()

    tool = ManagePlanTool(plan_store=plan_store, name=opts.tool_name)
    name = resolve_tool_name(tool)
    if tool_registry.get(name) is None:
        tool_registry.register(tool)

    ext_list = list(extensions or [])
    # Avoid duplicate planning_context
    if not any(getattr(e, "name", None) == "planning_context" for e in ext_list):
        ext_list.append(PlanningContextExtension(plan_store))

    return plan_store, tool, ext_list


def planning_prompt_snippet(options: PlanningOptions | None = None) -> str:
    opts = options or PlanningOptions()
    return (opts.prompt_snippet or DEFAULT_PLANNING_HINT).strip()
