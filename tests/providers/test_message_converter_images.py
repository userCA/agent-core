"""Image URL vs base64 handling in OpenAI message converter."""

import asyncio

from agent_core.core.content import ImageContent, TextContent
from agent_core.core.messages import UserMessage
from agent_core.providers.message_converter import _user_content_to_openai, create_default_converter


def test_http_image_url_passthrough() -> None:
    parts = _user_content_to_openai([
        TextContent(text="see"),
        ImageContent(data="https://cdn.example.com/a.png", mime_type="image/png"),
    ])
    assert isinstance(parts, list)
    img = next(p for p in parts if p["type"] == "image_url")
    assert img["image_url"]["url"] == "https://cdn.example.com/a.png"


def test_base64_still_wrapped() -> None:
    parts = _user_content_to_openai([
        ImageContent(data="iVBORw0K", mime_type="image/png"),
    ])
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_user_message_with_remote_url() -> None:
    convert = create_default_converter()
    msg = UserMessage(
        content=[
            TextContent(text="短剧"),
            ImageContent(data="https://cdn.example.com/hero.jpg", mime_type="image/jpeg"),
        ],
        timestamp=1.0,
    )
    out = asyncio.run(convert([msg]))
    assert out[0]["role"] == "user"
    assert out[0]["content"][1]["image_url"]["url"] == "https://cdn.example.com/hero.jpg"
