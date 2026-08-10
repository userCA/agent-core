"""Shared fixtures for workflow tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_factory import SubAgentFactory
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.multi_agent.types import AgentProfile
from agent_core.providers.auth import AuthSource
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.store import SessionHeader
from agent_core.workflows.loader import WorkflowLoader
from agent_core.workflows.runner import WorkflowRunner
from agent_core.workflows.store import WorkflowStore
from agent_core.workflows.types import WorkflowOptions
from tests.conftest import FakeProvider, fake_model

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def workflow_env(tmp_path):
    """WorkflowRunner + loader + store wired with FakeProvider and worker profile."""

    async def _setup(
        *,
        max_agent_invocations: int = 100,
        enable_dynamic_exec: bool = False,
        provider: FakeProvider | None = None,
        store: InMemoryStore | None = None,
    ):
        provider = provider or FakeProvider()
        store = store or InMemoryStore()
        try:
            await store.load_session("parent")
        except KeyError:
            await store.create_session(
                "parent",
                SessionHeader(
                    id="parent",
                    timestamp=datetime.now(tz=timezone.utc).isoformat(),
                    owner="alice",
                ),
            )
        registry = AgentProfileRegistry()
        registry.register(
            AgentProfile(
                name="worker",
                description="worker",
                system_prompt="You are a worker.",
            )
        )
        factory = SubAgentFactory(
            provider=provider,
            auth_source=AuthSource.static(api_key="fake"),
            store=store,
            parent_session_id="parent",
            default_model=fake_model(),
            all_tools=[],
            owner="alice",
        )
        sub_runner = SubAgentRunner(factory=factory, registry=registry, store=store)
        wf_store = WorkflowStore(session_store=store, session_id="parent", owner="alice")
        loader = WorkflowLoader(
            search_paths=[str(FIXTURES), str(tmp_path)],
            include_builtin_recipes=False,
        )
        options = WorkflowOptions(
            max_agent_invocations=max_agent_invocations,
            auto_checkpoint_phases=True,
            enable_dynamic_exec=enable_dynamic_exec,
        )
        runner = WorkflowRunner(
            loader=loader,
            store=wf_store,
            runner=sub_runner,
            registry=registry,
            options=options,
        )
        return runner, loader, wf_store, provider, store, tmp_path

    return _setup
