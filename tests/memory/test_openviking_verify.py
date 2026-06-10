"""Verify OpenViking adapter correctness via actual use-case tests.

Run: .venv/bin/pytest tests/memory/test_openviking_verify.py -v
"""

import asyncio
import sys
from unittest.mock import MagicMock

import pytest
from agent_core.memory.adapters.openviking_adapter import OpenVikingMemoryStore
from agent_core.memory.base import MemoryRecord


class _FakeMatchedContext:
    def __init__(self, abstract, uri, score, level, context_type=""):
        self.abstract = abstract
        self.uri = uri
        self.score = score
        self.context_type = context_type
        self.level = level


class _FakeFindResult:
    def __init__(self, memories):
        self.memories = memories


# ── Known: find() is global, session_id used for API key resolution ───────

def test_recall_uses_find_without_session_id():
    """find() is global — session_id is for API key resolution, not scoping.

    The openviking search() API is experimental and unstable on current servers.
    find() is the stable API; memories live in a shared viking://user/memories
    namespace extracted from sessions via commit_session.
    """
    mock = MagicMock()
    mock.find.return_value = _FakeFindResult(memories=[])
    store = OpenVikingMemoryStore(client=mock)

    asyncio.run(store.recall(session_id="alice/s1", query="preferences"))

    call_kwargs = mock.find.call_args.kwargs
    assert "session_id" not in call_kwargs, "find() has no session_id parameter — search is global"
    assert call_kwargs["target_uri"] == "viking://user/memories"
    assert call_kwargs["node_limit"] is not None
    print(f"[KNOWN] recall() calls find() — search is global. session_id used for API key resolution.")


def test_recall_should_use_search_not_find():
    """Demonstrate: search() has session_id, find() does not."""
    import openviking as ov
    import inspect

    find_params = set(inspect.signature(ov.SyncHTTPClient.find).parameters)
    search_params = set(inspect.signature(ov.SyncHTTPClient.search).parameters)

    assert "session_id" not in find_params, "find() has no session_id — by design"
    assert "session_id" in search_params, "search() HAS session_id — the scoped API"

    print(f"[INFO] find params: {sorted(find_params)}")
    print(f"[INFO] search params: {sorted(search_params)}")


# ── Fix verification: empty session_id no longer crashes ──────────────────

def test_resolve_api_key_empty_session_falls_back_to_default():
    """FIX VERIFIED: empty session_id no longer crashes, falls back to default."""
    store = OpenVikingMemoryStore(
        url="http://localhost:1933",
        api_key="default_key",
    )
    result = store._resolve_api_key("")
    assert result == "default_key", (
        f"Empty session_id should fall back to default, got {result!r}"
    )
    print(f"[FIX VERIFIED] Empty session_id resolves to default key (no crash).")


def test_resolve_api_key_leading_slash_falls_back():
    """Leading-slash session_id like '/alice/s1' skips PurePosixPath parse."""
    store = OpenVikingMemoryStore(
        url="http://localhost:1933",
        api_key="default",
        api_keys={"alice": "key_alice"},
    )
    # "/alice/s1" — contains "/", so PurePosixPath says parts[0]="/"
    # Now guarded by "if '/' in session_id": parts[0]="/", not in api_keys, fallback
    result = store._resolve_api_key("/alice/s1")
    assert result == "default", (
        f"Leading-slash path not in api_keys should fall back, got {result!r}"
    )
    print(f"[FIX VERIFIED] Leading-slash session_id falls back to default.")


# ── Thread safety note ────────────────────────────────────────────────────

async def test_get_client_thread_safety_racy_check_then_set():
    """_get_client check-then-set is not atomic under concurrency."""
    mock_ov = MagicMock()
    sys.modules["openviking"] = mock_ov

    try:
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            api_key="shared_key",
        )
        c1 = store._get_client("alice/s1")
        c2 = store._get_client("bob/s2")
        assert c1 is c2, "Same api_key should reuse the same client"
        assert mock_ov.SyncHTTPClient.call_count == 1
        print("[NOTE] Same-key client reuse works; concurrency not stress-tested here.")
    finally:
        sys.modules.pop("openviking", None)


# ── Metadata serialization is lossy ──────────────────────────────────────

async def test_remember_metadata_lossy_string_format():
    """Metadata is string-appended, not stored as structured data."""
    store = OpenVikingMemoryStore(client=MagicMock())
    await store.remember(
        session_id="s1",
        text="User prefers Python",
        metadata={"key": None, "nested": {"a": 1}},
    )
    print("[NOTE] Metadata appended as string — type fidelity depends on str().")


# ── recall returns abstract, not full content ─────────────────────────────

def test_recall_uses_abstract_not_full_content():
    """recall() maps ctx.abstract → MemoryRecord.text (SDK behavior)."""
    mock = MagicMock()
    ctx = _FakeMatchedContext(
        abstract="User prefers dark mode",
        uri="viking://user/memories/pref",
        score=0.95,
        level=1,
    )
    mock.find.return_value = _FakeFindResult(memories=[ctx])
    store = OpenVikingMemoryStore(client=mock)

    records = asyncio.run(store.recall(session_id="s1", query="theme"))
    assert records[0].text == "User prefers dark mode"
    print("[NOTE] recall() returns abstract — full original content may differ.")


# ── Summary runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
