import asyncio
import os
import tempfile

import pytest

from agent_core.tools.operations_local import LocalBashOperations, LocalFileOperations


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_local_file_operations_read(tmp_dir):
    path = os.path.join(tmp_dir, "test.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("hello world")

    ops = LocalFileOperations(cwd=tmp_dir)
    content = asyncio.run(ops.read("test.txt"))
    assert content == "hello world"


def test_local_file_operations_write_and_ls(tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    asyncio.run(ops.write("foo.txt", "bar"))
    infos = asyncio.run(ops.ls(tmp_dir))
    names = {i.name for i in infos}
    assert "foo.txt" in names


def test_local_file_operations_edit(tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    asyncio.run(ops.write("edit.txt", "old content here"))
    ok = asyncio.run(ops.edit("edit.txt", "old content", "new content"))
    assert ok
    content = asyncio.run(ops.read("edit.txt"))
    assert content == "new content here"


def test_local_bash_operations_echo():
    ops = LocalBashOperations()
    result = asyncio.run(ops.execute("echo hello"))
    assert result.returncode == 0
    assert "hello" in result.stdout
