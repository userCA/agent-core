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


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def store(mock_client):
    return OpenVikingMemoryStore(client=mock_client)


async def test_remember_add_message_and_commit(store, mock_client):
    await store.remember(session_id="s1", text="User prefers dark mode")
    mock_client.add_message.assert_called_once_with(
        session_id="s1", role="user", content="User prefers dark mode"
    )
    mock_client.commit_session.assert_called_once_with(session_id="s1")


async def test_remember_appends_metadata_to_content(store, mock_client):
    await store.remember(session_id="s1", text="fact", metadata={"key": "val"})
    call_kwargs = mock_client.add_message.call_args.kwargs
    assert "fact" in call_kwargs["content"]
    assert "metadata" in call_kwargs["content"]


async def test_recall_maps_find_results_to_records(store, mock_client):
    ctx = _FakeMatchedContext(abstract="User prefers Python", uri="viking://user/memories/pref", score=0.9, level=1)
    mock_client.find.return_value = _FakeFindResult(memories=[ctx])
    records = await store.recall(session_id="s1", query="language", limit=5)
    assert len(records) == 1
    assert isinstance(records[0], MemoryRecord)
    assert records[0].text == "User prefers Python"
    assert records[0].session_id == "s1"


async def test_recall_passes_query_params(store, mock_client):
    mock_client.find.return_value = _FakeFindResult(memories=[])
    await store.recall(session_id="s1", query="preferences", limit=3)
    call_kwargs = mock_client.find.call_args.kwargs
    assert call_kwargs["target_uri"] == "viking://user/memories"
    assert call_kwargs["node_limit"] == 3


async def test_recall_propagates_error(store, mock_client):
    mock_client.find.side_effect = RuntimeError("server down")
    with pytest.raises(RuntimeError, match="server down"):
        await store.recall(session_id="s1", query="q", limit=5)


async def test_forget_deletes_session(store, mock_client):
    await store.forget(session_id="s1")
    mock_client.delete_session.assert_called_once_with(session_id="s1")


import sys


def _install_mock_ov():
    mock_ov = MagicMock()
    sys.modules["openviking"] = mock_ov
    return mock_ov


def _clear_mock_ov():
    sys.modules.pop("openviking", None)


async def test_resolves_api_key_by_session_id_exact_match():
    mock_ov = _install_mock_ov()
    try:
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            api_keys={"alice": "key_alice", "bob": "key_bob"},
        )
        store._get_client("alice")
        store._get_client("bob")
        assert mock_ov.SyncHTTPClient.call_count == 2
        assert mock_ov.SyncHTTPClient.call_args_list[0].kwargs["api_key"] == "key_alice"
        assert mock_ov.SyncHTTPClient.call_args_list[1].kwargs["api_key"] == "key_bob"
    finally:
        _clear_mock_ov()


async def test_resolves_api_key_by_user_prefix():
    mock_ov = _install_mock_ov()
    try:
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            api_keys={"alice": "key_alice"},
        )
        store._get_client("alice/session_123")
        assert mock_ov.SyncHTTPClient.call_args.kwargs["api_key"] == "key_alice"
    finally:
        _clear_mock_ov()


async def test_resolves_api_key_caches_client_per_key():
    mock_ov = _install_mock_ov()
    try:
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            api_keys={"alice": "key_alice"},
        )
        c1 = store._get_client("alice/s1")
        c2 = store._get_client("alice/s2")
        assert c1 is c2
        assert mock_ov.SyncHTTPClient.call_count == 1
    finally:
        _clear_mock_ov()


async def test_resolve_api_key_callable_takes_priority():
    mock_ov = _install_mock_ov()
    try:
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            api_key="default_key",
            api_keys={"alice": "key_alice"},
            resolve_api_key=lambda sid: f"resolved_{sid}",
        )
        store._get_client("alice/s1")
        assert mock_ov.SyncHTTPClient.call_args.kwargs["api_key"] == "resolved_alice/s1"
    finally:
        _clear_mock_ov()


async def test_resolve_api_key_callable_handles_pure_uuid():
    mock_ov = _install_mock_ov()
    try:
        uuid_to_key = {
            "abc-123": "key_alice",
            "def-456": "key_bob",
        }
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            resolve_api_key=lambda sid: uuid_to_key[sid],
        )
        store._get_client("abc-123")
        store._get_client("def-456")
        assert mock_ov.SyncHTTPClient.call_args_list[0].kwargs["api_key"] == "key_alice"
        assert mock_ov.SyncHTTPClient.call_args_list[1].kwargs["api_key"] == "key_bob"
    finally:
        _clear_mock_ov()


async def test_falls_back_to_default_api_key():
    mock_ov = _install_mock_ov()
    try:
        store = OpenVikingMemoryStore(
            url="http://localhost:1933",
            api_key="default_key",
            api_keys={"alice": "key_alice"},
        )
        store._get_client("unknown_user/s1")
        assert mock_ov.SyncHTTPClient.call_args.kwargs["api_key"] == "default_key"
    finally:
        _clear_mock_ov()
