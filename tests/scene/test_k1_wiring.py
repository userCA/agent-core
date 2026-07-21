"""Tests for Scene memory / skill-evolution wiring flags."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import scene.http_sse.memory_config as memory_config
from scene.http_sse.evolution_config import (
    build_skill_trace_collector,
    skill_evolution_enabled,
)
from scene.http_sse.memory_config import (
    build_memory_extensions,
    resolve_memory_backend,
    shared_inmemory_store,
)


@pytest.fixture(autouse=True)
def _reset_shared_memory():
    memory_config._SHARED_INMEMORY = None
    yield
    memory_config._SHARED_INMEMORY = None


def test_resolve_memory_backend_default_inmemory(monkeypatch):
    monkeypatch.delenv("ENABLE_MEMORY", raising=False)
    monkeypatch.delenv("MEMORY_BACKEND", raising=False)
    assert resolve_memory_backend("") == "inmemory"
    assert resolve_memory_backend("mem0") == "mem0"


def test_resolve_memory_backend_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_MEMORY", "0")
    assert resolve_memory_backend("") == ""


def test_shared_inmemory_store_singleton():
    a = shared_inmemory_store()
    b = shared_inmemory_store()
    assert a is b


def test_build_memory_extensions_inmemory():
    exts = build_memory_extensions("inmemory", {}, "sess-1")
    assert len(exts) == 1
    assert exts[0].name == "memory"


def test_build_memory_extensions_off():
    assert build_memory_extensions("", {}, "sess-1") == []


@pytest.mark.asyncio
async def test_shared_store_session_isolation():
    store = shared_inmemory_store()
    await store.remember(session_id="a", text="secret-a")
    await store.remember(session_id="b", text="secret-b")
    recs = await store.recall(session_id="a", query="secret", limit=10)
    assert recs
    assert all(r.session_id == "a" for r in recs)
    assert all("secret-b" not in r.text for r in recs)


def test_skill_evolution_enabled_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SKILL_EVOLUTION", raising=False)
    assert skill_evolution_enabled() is True


def test_skill_evolution_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SKILL_EVOLUTION", "0")
    assert skill_evolution_enabled() is False
    assert build_skill_trace_collector() is None


def test_default_jsonl_path_matches_evolution_api():
    """Collector factory and REST APIs share the same default path (no mkdir)."""
    from agent_core.skill_evolution.store import JsonlSkillEvolutionStore

    expected = Path("~/.agent-core/skill-evolution-traces.jsonl").expanduser()
    default = inspect.signature(JsonlSkillEvolutionStore.__init__).parameters[
        "storage_path"
    ].default
    assert Path(default).expanduser() == expected


def test_build_skill_trace_collector_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SKILL_EVOLUTION", "1")
    from agent_core.skill_evolution.store import InMemorySkillEvolutionStore

    monkeypatch.setattr(
        "agent_core.skill_evolution.store.create_skill_evolution_store",
        lambda *a, **k: InMemorySkillEvolutionStore(),
    )
    collector = build_skill_trace_collector()
    assert collector is not None
    assert collector.name == "skill_trace_collector"
