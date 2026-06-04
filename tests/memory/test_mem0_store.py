from unittest.mock import MagicMock, patch

import pytest
from agent_core.memory.adapters.mem0_adapter import Mem0MemoryStore
from agent_core.memory.base import MemoryRecord


@pytest.fixture
def mock_memory():
    return MagicMock()


@pytest.fixture
def store(mock_memory):
    return Mem0MemoryStore(memory=mock_memory)


async def test_remember_sends_correct_messages(store, mock_memory):
    await store.remember(session_id="s1", text="User loves Go")
    mock_memory.add.assert_called_once()
    call_args, call_kwargs = mock_memory.add.call_args
    assert call_args[0] == [{"role": "user", "content": "User loves Go"}]
    assert call_kwargs["user_id"] == "s1"


async def test_remember_passes_metadata(store, mock_memory):
    await store.remember(session_id="s1", text="fact", metadata={"k": "v"})
    call_kwargs = mock_memory.add.call_args.kwargs
    assert call_kwargs["metadata"] == {"k": "v"}


async def test_recall_maps_mem0_results_to_records(store, mock_memory):
    mock_memory.search.return_value = {
        "results": [{"memory": "User loves Go", "metadata": {}, "id": "m1", "created_at": "..."}]
    }
    records = await store.recall(session_id="s1", query="language", limit=5)
    assert len(records) == 1
    assert isinstance(records[0], MemoryRecord)
    assert records[0].text == "User loves Go"
    assert records[0].session_id == "s1"


async def test_recall_passes_filters_and_top_k(store, mock_memory):
    mock_memory.search.return_value = {"results": []}
    await store.recall(session_id="s1", query="q", limit=3)
    mock_memory.search.assert_called_once()
    call_kwargs = mock_memory.search.call_args.kwargs
    assert call_kwargs["filters"] == {"user_id": "s1"}
    assert call_kwargs["top_k"] == 3


async def test_recall_returns_empty_on_search_error(store, mock_memory):
    mock_memory.search.side_effect = RuntimeError("network down")
    records = await store.recall(session_id="s1", query="q", limit=5)
    assert records == []


async def test_forget_calls_delete_all(store, mock_memory):
    await store.forget(session_id="s1")
    mock_memory.delete_all.assert_called_once()
    assert mock_memory.delete_all.call_args.kwargs["user_id"] == "s1"


async def test_lazy_client_imports_mem0():
    with patch("agent_core.memory.adapters.mem0_adapter.Mem0MemoryStore._get_client", autospec=True) as mock_get:
        mock_get.return_value = MagicMock()
        s = Mem0MemoryStore()
        assert s._client is None
        assert s._memory is None
