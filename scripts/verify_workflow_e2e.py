#!/usr/bin/env python3
"""Verify demo-e2e workflow end-to-end (no network)."""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


async def main() -> int:
    from datetime import datetime, timezone

    from agent_core.multi_agent.factory import create_multi_agent_harness
    from agent_core.multi_agent.types import MultiAgentHarnessOptions, AgentProfile
    from agent_core.providers.auth import AuthSource
    from agent_core.session.inmemory_store import InMemoryStore
    from agent_core.session.store import SessionHeader
    from agent_core.tools.base import ToolRegistry
    from agent_core.workflows import WorkflowOptions, install_workflows
    from tests.conftest import FakeProvider, fake_model
    from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

    cwd = ROOT
    store = InMemoryStore()
    session_id = "wf-e2e"
    await store.create_session(
        session_id,
        SessionHeader(
            id=session_id,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            cwd=cwd,
            owner="verify",
        ),
    )

    provider = FakeProvider()
    # analyze: 3 items + summarize: 1
    for label in ("item-0", "item-1", "item-2", "summarize"):
        provider.queue_script([
            StreamTextDelta(text=f"ok-{label}"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=2),
        ])

    tool_registry = ToolRegistry()
    options = MultiAgentHarnessOptions(
        profiles=[
            AgentProfile(
                name="worker",
                description="general worker",
                system_prompt="Reply briefly.",
            )
        ],
        max_concurrent_agents=4,
    )
    harness, ma = create_multi_agent_harness(
        options=options,
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id=session_id,
        model=fake_model(),
        tools=[],
        tool_registry=tool_registry,
        owner="verify",
    )

    handle = install_workflows(
        tool_registry=tool_registry,
        sub_agent_runner=ma.runner,
        profile_registry=ma.registry,
        parent_harness=harness,
        session_store=store,
        session_id=session_id,
        owner="verify",
        options=WorkflowOptions(
            search_paths=[os.path.join(cwd, ".pi", "workflows")],
            include_builtin_recipes=False,
        ),
    )

    names = [w.name for w in handle.list_workflows()]
    if "demo-e2e" not in names:
        print(f"FAIL: demo-e2e not in workflows: {names}")
        return 1

    result = await handle.runner.run(
        name="demo-e2e",
        args={"items": ["alpha", "beta", "gamma"]},
    )
    if result.status != "completed":
        print(f"FAIL: status={result.status} error={result.error_message}")
        return 1
    if not result.result or "summary" not in result.result:
        print(f"FAIL: unexpected result={result.result!r}")
        return 1

    print("OK: demo-e2e workflow completed")
    print(f"  summary={result.result.get('summary')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
