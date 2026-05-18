import inspect

from agent_core.tools.operations import BashOperations, FileOperations, FileInfo


def test_file_info_is_dataclass():
    fi = FileInfo(name="x.py", path="/tmp/x.py", is_dir=False, size=100)
    assert fi.name == "x.py"
    assert not fi.is_dir


def test_file_operations_is_protocol():
    assert hasattr(FileOperations, "read")
    assert hasattr(FileOperations, "write")
    assert hasattr(FileOperations, "edit")


def test_bash_operations_is_protocol():
    assert hasattr(BashOperations, "execute")
