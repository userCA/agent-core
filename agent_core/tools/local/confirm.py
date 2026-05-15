"""Human-in-the-loop confirmation tool."""

from __future__ import annotations

from typing import Any

from agent_core.core.human_input import RequiresHumanInput
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult


class ConfirmTool:
    """A tool that pauses execution to ask the user for input via an interactive card.

    The LLM should call this tool whenever it needs additional information,
    confirmation, or rich input (images, voice) from the user.
    """

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="confirm",
            description=(
                "当需要用户确认、补充信息或提供额外参数时调用此工具。"
                "支持文本输入、多行文本、图片上传和语音录音。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "向用户展示的问题或提示语",
                    },
                    "fields": {
                        "type": "array",
                        "description": "需要用户填写的字段列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "字段标识名"},
                                "label": {"type": "string", "description": "展示给用户的标签"},
                                "type": {
                                    "type": "string",
                                    "enum": ["text", "textarea", "image_upload", "audio_record"],
                                    "description": "输入类型",
                                },
                                "placeholder": {
                                    "type": "string",
                                    "description": "输入框占位提示",
                                },
                            },
                            "required": ["name", "label", "type"],
                        },
                    },
                },
                "required": ["prompt"],
            },
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        """Raise RequiresHumanInput so the loop pauses for user input."""
        prompt = params.get("prompt", "请确认")
        fields = params.get(
            "fields",
            [{"name": "confirm", "label": "确认", "type": "text"}],
        )
        raise RequiresHumanInput(prompt=prompt, input_schema={"fields": fields})


def create_confirm_tool() -> ConfirmTool:
    return ConfirmTool()


confirm_tool = ConfirmTool()
