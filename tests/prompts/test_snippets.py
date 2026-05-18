from agent_core.prompts.snippets import extract_snippet
from agent_core.tools.base import ToolDefinition


def test_extract_snippet_from_prompt_snippet():
    d = ToolDefinition(name="read", description="Read files", parameters={}, prompt_snippet="Read a file")
    assert extract_snippet(d) == "Read a file"


def test_extract_snippet_from_description():
    d = ToolDefinition(name="read", description="Read a file from disk. Supports offsets.", parameters={})
    assert extract_snippet(d) == "Read a file from disk"


def test_extract_snippet_truncate_long_description():
    long_desc = "A" * 100 + ". More text here."
    d = ToolDefinition(name="read", description=long_desc, parameters={})
    result = extract_snippet(d)
    assert result.endswith("...")
    assert len(result) == 80


def test_extract_snippet_fallback_to_name():
    d = ToolDefinition(name="read", description="", parameters={})
    assert extract_snippet(d) == "read"
