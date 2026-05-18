import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.prompts import load_prompt_from_file


def test_load_prompt_template():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "review.md")
        with open(path, "w") as f:
            f.write("---\nname: code-review\ndescription: Review code\nparameters:\n  - language\n---\n\nReview {{language}} code.")
        diag = ResourceDiagnostics()
        pt = load_prompt_from_file(path, diag)
        assert pt is not None
        assert pt.name == "code-review"
        assert pt.parameters == ["language"]
        assert "Review {{language}} code." in pt.template
