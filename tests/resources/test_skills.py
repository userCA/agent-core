import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.skills import load_skill_from_file


def test_load_skill_from_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "SKILL.md")
        with open(path, "w") as f:
            f.write("---\nname: test-skill\ndescription: A test skill\n---\n\nContent here.")
        diag = ResourceDiagnostics()
        skill = load_skill_from_file(path, diag)
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert "Content here" in skill.content
