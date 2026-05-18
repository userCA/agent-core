import tempfile
import os

from agent_core.resources.context_files import load_project_context_files


def test_load_context_files_from_cwd():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w") as f:
            f.write("# Agents")
        files = load_project_context_files(d)
        assert len(files) == 1
        assert files[0].path.endswith("AGENTS.md")
        assert files[0].source == "cwd"


def test_load_context_files_ancestor():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "CLAUDE.md"), "w") as f:
            f.write("# Claude")
        sub = os.path.join(d, "sub")
        os.makedirs(sub)
        files = load_project_context_files(sub)
        assert len(files) == 1
        assert files[0].source == "ancestor"
