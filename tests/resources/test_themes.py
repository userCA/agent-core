import json
import os
import tempfile

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.themes import load_theme_from_file


def test_load_theme():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "dark.json")
        with open(path, "w") as f:
            json.dump({"name": "dark", "colors": {"primary": "#000"}}, f)
        diag = ResourceDiagnostics()
        theme = load_theme_from_file(path, diag)
        assert theme is not None
        assert theme.name == "dark"
