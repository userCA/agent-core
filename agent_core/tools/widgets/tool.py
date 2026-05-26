"""ShowWidgetTool — renders LLM-generated HTML in a sandboxed iframe."""

from __future__ import annotations

from typing import Any

from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.core.content import TextContent
from agent_core.tools.widgets.spec import WIDGET_SPEC

MAX_HTML_BYTES = 50 * 1024
MAX_HEIGHT = 1200
DEFAULT_HEIGHT = 400

FORBIDDEN_TAGS = ["<html>", "<head>", "<body>", "<!doctype"]


class ShowWidgetTool:
    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="show_widget",
            description=WIDGET_SPEC,
            parameters={
                "type": "object",
                "properties": {
                    "html": {
                        "type": "string",
                        "description": "完整 HTML 片段,需遵守设计规范",
                    },
                    "title": {
                        "type": "string",
                        "description": "可选展示标题",
                    },
                    "height": {
                        "type": "integer",
                        "description": "可选 iframe 高度(px),默认 400,最大 1200",
                    },
                },
                "required": ["html"],
            },
            prompt_snippet=None,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        html = params.get("html", "")
        title = params.get("title")
        height = params.get("height")

        _validate_html(html)

        h = height if isinstance(height, int) and height > 0 else DEFAULT_HEIGHT
        h = min(h, MAX_HEIGHT)

        return ToolResult(
            content=[TextContent(text=f"[widget rendered: {title or '未命名'}]")],
            display={
                "widget": {
                    "version": 1,
                    "html": html,
                    "title": title,
                    "height": h,
                }
            },
        )


def _validate_html(html: str) -> None:
    html_bytes = len(html.encode("utf-8"))
    if html_bytes > MAX_HTML_BYTES:
        raise ValueError(
            f"html size exceeds 50KB limit (got {html_bytes} bytes)"
        )

    html_lower = html.lower()
    for tag in FORBIDDEN_TAGS:
        if tag in html_lower:
            display_tag = tag.rstrip(">") + ">" if ">" not in tag else tag
            raise ValueError(
                f"html contains forbidden tag {display_tag}; "
                "请删除后重新调用 show_widget"
            )
