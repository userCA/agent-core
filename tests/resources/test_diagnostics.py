from agent_core.resources.diagnostics import ResourceDiagnostics


def test_diagnostics_warning():
    d = ResourceDiagnostics()
    d.warning("test warning", source_path="/a")
    assert len(d.items) == 1
    assert d.items[0].type == "warning"


def test_diagnostics_collision():
    d = ResourceDiagnostics()
    d.collision("dup", winner_path="/a", loser_path="/b")
    assert d.has_errors is False
    assert d.items[0].winner_path == "/a"
