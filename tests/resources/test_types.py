from agent_core.resources.types import ResourceDiagnostic, SourceInfo


def test_source_info_creation():
    si = SourceInfo(source="project", scope="global", origin="/path", base_dir="/base")
    assert si.source == "project"


def test_resource_diagnostic_creation():
    rd = ResourceDiagnostic(type="warning", message="test")
    assert rd.type == "warning"
