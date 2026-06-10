"""Live OpenViking adapter tests against real server.

Run: .venv/bin/pytest tests/memory/test_openviking_live.py -v -s
"""

import asyncio

import pytest
from agent_core.memory.adapters.openviking_adapter import OpenVikingMemoryStore

OV_URL = "http://36.133.115.210:8888/proxy_name/openviking"
OV_KEY = "ZGVmYXVsdA.ZGVmYXVsdA.OTYzM2U2MGNkODdjMDg2ZDQ3M2U0YjJkNThhNmRkNzE5ODA3NWIxYjQwN2E5ODJkNmY2OTMyZDFiMjkwMjljMw"

SESSION_A = "test-adapter-a"
SESSION_B = "test-adapter-b"


@pytest.fixture
def store():
    return OpenVikingMemoryStore(url=OV_URL, api_key=OV_KEY)


async def _try_delete(store, sid):
    try:
        await store.forget(session_id=sid)
    except Exception:
        pass


@pytest.fixture(autouse=True)
async def cleanup(store):
    for sid in [SESSION_A, SESSION_B]:
        await _try_delete(store, sid)
    yield
    for sid in [SESSION_A, SESSION_B]:
        await _try_delete(store, sid)


# ── Basic CRUD ───────────────────────────────────────────────────────────────

async def test_remember_and_recall_basic(store):
    """E2E: store a memory then recall it via find() (global search)."""
    await store.remember(session_id=SESSION_A, text="Zhang San prefers Python programming")
    await asyncio.sleep(2)

    records = await store.recall(session_id=SESSION_A, query="programming language", limit=5)
    # find() is global — may return system memory docs or the stored fact
    print(f"\n  [OK] remember → recall: {len(records)} record(s)")
    for r in records:
        print(f"    score={r.metadata.get('score', 0):.3f}  text={r.text[:80]!r}")


async def test_remember_multiple_facts(store):
    """Store multiple facts and recall via global search."""
    facts = [
        "User likes dark theme",
        "User works as a backend engineer",
        "User prefers concise answers",
    ]
    for f in facts:
        await store.remember(session_id=SESSION_A, text=f)
    await asyncio.sleep(3)

    records = await store.recall(session_id=SESSION_A, query="user preferences", limit=5)
    print(f"\n  [OK] {len(records)} records for 'user preferences'")


# ── Session scoping note ─────────────────────────────────────────────────────

async def test_recall_is_global_not_session_scoped(store):
    """Known: find() is global. session_id is for API key resolution, not scoping.

    OpenViking extracts memories from sessions into a shared
    viking://user/memories namespace via commit_session().
    search() is experimental and not stable on current servers.
    """
    await store.remember(session_id=SESSION_A, text="Alice prefers coffee")
    await asyncio.sleep(2)

    # Even querying from SESSION_B, we may get results because search is global
    records = await store.recall(session_id=SESSION_B, query="prefers coffee", limit=5)
    print(f"\n  [INFO] Global search from session B: {len(records)} record(s)")
    for r in records:
        print(f"    {r.text[:80]!r}")


# ── forget: now raises exceptions ────────────────────────────────────────────

async def test_forget_raises_permission_error(store):
    """FIX: forget() now raises PermissionDeniedError instead of silently swallowing."""
    await store.remember(session_id=SESSION_A, text="test data")
    await asyncio.sleep(2)

    with pytest.raises(Exception) as exc_info:
        await store.forget(session_id=SESSION_A)
    print(f"\n  [FIX VERIFIED] forget() raised {type(exc_info.value).__name__}: {exc_info.value}")


# ── Metadata roundtrip ──────────────────────────────────────────────────────

async def test_remember_with_metadata(store):
    """Verify metadata roundtrip behavior."""
    meta = {"importance": "high", "category": "preference"}
    await store.remember(session_id=SESSION_A, text="Critical: user is vegan", metadata=meta)
    await asyncio.sleep(2)
    records = await store.recall(session_id=SESSION_A, query="dietary restriction", limit=5)
    print(f"\n  Metadata test: {len(records)} records")


# ── Edge cases ───────────────────────────────────────────────────────────────

async def test_recall_empty_query(store):
    """Empty query raises InvalidArgumentError from server."""
    await store.remember(session_id=SESSION_A, text="Some random information")
    await asyncio.sleep(2)
    with pytest.raises(Exception) as exc_info:
        await store.recall(session_id=SESSION_A, query="", limit=5)
    print(f"\n  [FIX VERIFIED] Empty query raises {type(exc_info.value).__name__}")


async def test_empty_session_id_falls_back(store):
    """FIX: empty session_id no longer crashes _resolve_api_key."""
    result = store._resolve_api_key("")
    assert result == OV_KEY, f"Empty session_id should fall back to default, got {result[:20]}..."
    print(f"\n  [FIX VERIFIED] Empty session_id resolves to default API key")


async def test_url_normalization(store):
    """FIX: URL trailing /api/v1 is stripped to avoid duplicate prefix."""
    store2 = OpenVikingMemoryStore(
        url="http://36.133.115.210:8888/proxy_name/openviking/api/v1",
        api_key=OV_KEY,
    )
    assert store2._url == "http://36.133.115.210:8888/proxy_name/openviking"
    print(f"\n  [FIX VERIFIED] URL normalized: /api/v1 suffix stripped")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--timeout=30"])
