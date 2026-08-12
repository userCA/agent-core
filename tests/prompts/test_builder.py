from datetime import datetime, timezone

from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.types import ContextFile, Skill, SourceInfo
from agent_core.tools.base import ToolDefinition


def test_builder_basic():
    builder = SystemPromptBuilder()
    result = builder.build(cwd="/tmp")
    assert "helpful assistant" in result.text
    assert "/tmp" in result.text
    assert len(result.sections) >= 2
    assert result.tool_count == 0
    assert result.skill_count == 0
    assert result.context_file_count == 0


def test_builder_with_tools():
    builder = SystemPromptBuilder()
    tools = [
        ToolDefinition(name="read", description="Read files from disk.", parameters={}),
        ToolDefinition(name="bash", description="Run shell commands.", parameters={}),
    ]
    result = builder.build(cwd="/tmp", active_tools=tools)
    assert "read" in result.text
    assert "bash" in result.text
    assert result.tool_count == 2
    # Check snippets are present
    assert "Read files from disk" in result.text
    assert "Run shell commands" in result.text


def test_builder_with_context_files():
    builder = SystemPromptBuilder()
    files = [ContextFile(path="/p/AGENTS.md", content="# Agents", source="cwd")]
    result = builder.build(cwd="/p", context_files=files)
    assert "# Agents" in result.text
    assert result.context_file_count == 1


def test_builder_with_skills_progressive_instructions():
    builder = SystemPromptBuilder()
    skills = [
        Skill(
            name="test-skill",
            description="A test skill",
            content="---\nname: test-skill\n---\n\nSecret body that must not appear.",
            source=SourceInfo(source="project", scope="project", origin="/x", base_dir="/x"),
        )
    ]
    result = builder.build(cwd="/p", skills=skills, skill_progressive=True)
    assert "load_skill" in result.text
    assert "test-skill" in result.text
    assert "A test skill" in result.text
    assert "Secret body that must not appear" not in result.text


def test_builder_with_skills():
    builder = SystemPromptBuilder()
    skills = [
        Skill(
            name="test-skill",
            description="A test skill",
            content="content",
            source=SourceInfo(source="project", scope="project", origin="/x", base_dir="/x"),
        )
    ]
    result = builder.build(cwd="/p", skills=skills)
    assert "test-skill" in result.text
    assert "A test skill" in result.text
    assert result.skill_count == 1


def test_builder_with_disabled_skill():
    builder = SystemPromptBuilder()
    skills = [
        Skill(
            name="hidden",
            description="Hidden skill",
            content="content",
            source=SourceInfo(source="project", scope="project", origin="/x", base_dir="/x"),
            disable_model_invocation=True,
        )
    ]
    result = builder.build(cwd="/p", skills=skills)
    assert "hidden" not in result.text


def test_builder_with_guidelines():
    builder = SystemPromptBuilder()
    tools = [ToolDefinition(name="read", description="Read files.", parameters={})]
    result = builder.build(cwd="/tmp", active_tools=tools)
    assert "truncated" in result.text


def test_builder_with_tool_guidelines():
    builder = SystemPromptBuilder()
    tools = [
        ToolDefinition(
            name="write",
            description="Write files.",
            parameters={},
            prompt_guidelines=["Always provide the full desired content of the file."],
        )
    ]
    result = builder.build(cwd="/tmp", active_tools=tools)
    assert "Tool Guidelines" in result.text
    assert "full desired content" in result.text


def test_builder_custom_base_prompt():
    builder = SystemPromptBuilder(base_prompt="Custom base prompt.")
    result = builder.build(cwd="/tmp")
    assert "Custom base prompt." in result.text
    assert "helpful assistant" not in result.text


def test_builder_date():
    builder = SystemPromptBuilder()
    date = datetime(2025, 1, 15, tzinfo=timezone.utc)
    result = builder.build(cwd="/tmp", date=date)
    assert "2025-01-15" in result.text


def test_builder_sections_ordered():
    builder = SystemPromptBuilder()
    tools = [
        ToolDefinition(
            name="read",
            description="Read files.",
            parameters={},
            prompt_guidelines=["Use offset for large files."],
        )
    ]
    files = [ContextFile(path="/p/AGENTS.md", content="# Agents", source="cwd")]
    skills = [
        Skill(
            name="s1",
            description="Skill one",
            content="c",
            source=SourceInfo(source="project", scope="project", origin="/x", base_dir="/x"),
        )
    ]
    result = builder.build(cwd="/p", active_tools=tools, context_files=files, skills=skills)
    names = [s.name for s in result.sections]
    assert names == ["base", "tools", "guidelines", "tool_guidelines", "context_files", "skills", "meta"]


def test_builder_empty_tools_with_guidelines():
    builder = SystemPromptBuilder()
    result = builder.build(cwd="/tmp", active_tools=[])
    # Global guidelines are always present
    assert "Tool Guidelines" in result.text
    assert "最终产物" in result.text
