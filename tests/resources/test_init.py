from agent_core.resources import (
    ContextFile,
    ExtensionSpec,
    PromptTemplate,
    ResourceDiagnostic,
    ResourceDiagnostics,
    ResourceLoader,
    Skill,
    SourceInfo,
    Theme,
)


def test_all_exports_importable():
    assert ContextFile is not None
    assert ExtensionSpec is not None
    assert PromptTemplate is not None
    assert ResourceDiagnostic is not None
    assert ResourceDiagnostics is not None
    assert ResourceLoader is not None
    assert Skill is not None
    assert SourceInfo is not None
    assert Theme is not None
