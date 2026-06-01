"""Dynamic system prompt builder."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from agent_core.prompts.guidelines import generate_guidelines
from agent_core.prompts.snippets import extract_snippet
from agent_core.resources.types import ContextFile, Skill
from agent_core.tools.base import ToolDefinition


class SystemPromptSection(BaseModel):
    name: str
    content: str
    source: str | None = None


class SystemPrompt(BaseModel):
    text: str
    sections: list[SystemPromptSection]
    tool_count: int
    skill_count: int
    context_file_count: int


class SystemPromptBuilder:
    """Build system prompts dynamically from tools, skills, context files, and metadata."""

    def __init__(self, *, base_prompt: str | None = None) -> None:
        self._base_prompt = base_prompt

    def build(
        self,
        *,
        cwd: str | None = None,
        active_tools: list[ToolDefinition] | None = None,
        skills: list[Skill] | None = None,
        context_files: list[ContextFile] | None = None,
        date: datetime | None = None,
    ) -> SystemPrompt:
        sections: list[SystemPromptSection] = []

        # 1. Base prompt
        base = self._base_prompt or (
            "You are a helpful assistant with access to tools. "
            "When you need to perform actions on the user's system, use the available tools. "
            "Always prefer using tools over guessing when file or system information is needed."
        )
        sections.append(SystemPromptSection(name="base", content=base))

        # 2. Tools
        tools = active_tools or []
        tool_lines: list[str] = []
        if tools:
            tool_lines.append("")
            tool_lines.append("## Tools")
            tool_lines.append("")
            tool_lines.append("You have access to the following tools:")
            tool_lines.append("")
            for tool in sorted(tools, key=lambda t: t.name):
                snippet = extract_snippet(tool)
                tool_lines.append(f"- {tool.name}: {snippet}")
        sections.append(SystemPromptSection(name="tools", content="\n".join(tool_lines)))

        # 3. Guidelines
        guidelines = generate_guidelines(tools)
        if guidelines:
            guideline_text = "\n".join(["", "## Guidelines", ""] + guidelines)
            sections.append(SystemPromptSection(name="guidelines", content=guideline_text))

        # 4. Global tool output guidelines
        tool_guidelines: list[str] = [
            "判断工具结果是中间过程还是最终产物：",
            "- 最终产物（图片、生成的文件、用户直接需要的内容）→ 必须在回复中原样包含，不要只描述",
            "- 中间步骤（读文件用于推理、查状态、执行命令）→ 基于结果继续回答，不需要展示原始输出",
        ]
        # Tool-specific guidelines
        for tool in tools:
            for g in tool.prompt_guidelines:
                tool_guidelines.append(f"- {g}")
        if tool_guidelines:
            text = "\n".join(["", "## Tool Guidelines", ""] + tool_guidelines)
            sections.append(SystemPromptSection(name="tool_guidelines", content=text))

        # 5. Context files
        ctx_files = context_files or []
        if ctx_files:
            lines = ["", "## Project Context", ""]
            for cf in ctx_files:
                lines.append(f"### {cf.path}")
                lines.append("")
                lines.append(cf.content)
                lines.append("")
            sections.append(SystemPromptSection(name="context_files", content="\n".join(lines)))

        # 6. Skills
        skill_list = skills or []
        if skill_list:
            lines = ["", "## Skills", ""]
            lines.append("<available_skills>")
            for skill in skill_list:
                if not skill.disable_model_invocation:
                    lines.append(f'  <skill name="{skill.name}">{skill.description}</skill>')
            lines.append("</available_skills>")
            sections.append(SystemPromptSection(name="skills", content="\n".join(lines)))

        # 7. Meta
        now = date or datetime.now(tz=timezone.utc)
        meta_lines = [
            "",
            "## Meta",
            "",
            f"Current date: {now.strftime('%Y-%m-%d')}",
        ]
        if cwd:
            meta_lines.append(f"Current working directory: {cwd}")
        sections.append(SystemPromptSection(name="meta", content="\n".join(meta_lines)))

        # Assemble
        full_text = "\n".join(s.content for s in sections)
        return SystemPrompt(
            text=full_text,
            sections=sections,
            tool_count=len(tools),
            skill_count=len(skill_list),
            context_file_count=len(ctx_files),
        )
