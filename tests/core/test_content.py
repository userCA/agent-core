from agent_core.core.content import TextContent, ImageContent, ToolCallContent


def test_text_content_roundtrip():
    tc = TextContent(text="hello")
    assert tc.type == "text"
    assert tc.model_dump() == {"type": "text", "text": "hello"}


def test_image_content_roundtrip():
    ic = ImageContent(data="iVBORw0K", mime_type="image/png")
    assert ic.type == "image"
    assert ic.model_dump() == {"type": "image", "data": "iVBORw0K", "mime_type": "image/png"}


def test_tool_call_content_roundtrip():
    tc = ToolCallContent(id="call_1", name="search", arguments={"q": "x"})
    assert tc.type == "tool_call"
    assert tc.model_dump() == {
        "type": "tool_call",
        "id": "call_1",
        "name": "search",
        "arguments": {"q": "x"},
    }
