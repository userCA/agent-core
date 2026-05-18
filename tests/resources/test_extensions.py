import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.extensions import discover_extension_specs


def test_discover_extension_specs():
    with tempfile.TemporaryDirectory() as d:
        ext_dir = os.path.join(d, "my_ext")
        os.makedirs(ext_dir)
        with open(os.path.join(ext_dir, "extension.py"), "w") as f:
            f.write("class MyExt:\n    pass\n")
        diag = ResourceDiagnostics()
        specs = discover_extension_specs([d], diag)
        assert len(specs) >= 1
        assert specs[0].name == "extension"
