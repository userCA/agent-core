from agent_core.core.content import TextContent
from agent_core.tools.base import (
    ToolContext,
    ToolDefinition,
    ToolInfo,
    ToolRegistry,
    ToolResult,
)


class FakeTool:
    definition = ToolDefinition(
        name="echo",
        description="echo args",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=str(params.get("x", "")))])


def test_registry_register_and_get():
    reg = ToolRegistry()
    reg.register(FakeTool())
    assert reg.get("echo") is not None
    assert reg.get("missing") is None


def test_registry_list():
    reg = ToolRegistry()
    reg.register(FakeTool(), source="test")
    infos = reg.list()
    assert len(infos) == 1
    assert isinstance(infos[0], ToolInfo)
    assert infos[0].name == "echo"


def test_registry_to_definitions():
    reg = ToolRegistry()
    reg.register(FakeTool())
    defs = reg.to_definitions()
    assert len(defs) == 1
    assert defs[0].name == "echo"


def test_tool_result_roundtrip():
    tr = ToolResult(content=[TextContent(text="ok")], details={"extra": 1})
    assert tr.model_dump()["content"] == [{"type": "text", "text": "ok"}]
