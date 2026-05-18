import asyncio
import tempfile

import pytest

from agent_core.tools.mutation_queue import FileMutationQueue
from agent_core.tools.operations_local import LocalFileOperations


@pytest.fixture
def queue():
    return FileMutationQueue()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.mark.asyncio
async def test_mutation_queue_serializes_access(queue, tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    await ops.write("counter.txt", "0")

    async def increment():
        async with queue.acquire("counter.txt"):
            val = int(await ops.read("counter.txt"))
            await ops.write("counter.txt", str(val + 1))

    await asyncio.gather(*[increment() for _ in range(10)])
    result = await ops.read("counter.txt")
    assert result == "10"


@pytest.mark.asyncio
async def test_mutation_queue_read_locked(queue, tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    await ops.write("test.txt", "hello")
    content = await queue.read_locked(ops, "test.txt")
    assert content == "hello"
