from agent_core.prompts.guidelines import generate_guidelines
from agent_core.tools.base import ToolDefinition


def test_generate_guidelines_with_read():
    tools = [ToolDefinition(name="read", description="", parameters={})]
    guidelines = generate_guidelines(tools)
    assert any("truncated" in g for g in guidelines)


def test_generate_guidelines_with_edit():
    tools = [ToolDefinition(name="edit", description="", parameters={})]
    guidelines = generate_guidelines(tools)
    assert any("edit" in g for g in guidelines)


def test_generate_guidelines_with_grep_find_ls():
    tools = [
        ToolDefinition(name="grep", description="", parameters={}),
        ToolDefinition(name="find", description="", parameters={}),
        ToolDefinition(name="ls", description="", parameters={}),
    ]
    guidelines = generate_guidelines(tools)
    assert any("grep/find/ls" in g for g in guidelines)


def test_generate_guidelines_with_write_and_edit():
    tools = [
        ToolDefinition(name="write", description="", parameters={}),
        ToolDefinition(name="edit", description="", parameters={}),
    ]
    guidelines = generate_guidelines(tools)
    assert any("check if they already exist" in g for g in guidelines)


def test_generate_guidelines_empty():
    assert generate_guidelines([]) == []


def test_generate_guidelines_custom_rules():
    tools = [ToolDefinition(name="foo", description="", parameters={})]
    rules = [lambda t: "custom" if "foo" in t else None]
    guidelines = generate_guidelines(tools, rules=rules)
    assert guidelines == ["custom"]
