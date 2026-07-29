"""Agnes Image generation tool — text-to-image and image-to-image editing."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult

_AGNES_BASE_URL = os.environ.get("AGNES_BASE_URL", "https://agnes-ai.cn/v1")
API_BASE = f"{_AGNES_BASE_URL.rstrip('/')}/images/generations"
API_KEY = os.environ.get("AGNES_API_KEY", "")
TIMEOUT = 120


class AgnesImageTool(Tool):
    """Generate or edit images using Agnes-Image-2.0-Flash."""

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="generate_image",
            description=(
                "使用 Agnes-Image-2.0-Flash 模型生成或编辑图片。"
                "支持文字生成图片和图片编辑（需提供输入图片URL）。"
                "返回生成的图片URL。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "图片描述或编辑指令。描述你想要的图片内容、风格、场景。例如：'一只可爱的猫咪坐在花园里，阳光透过树叶，温馨的氛围'",
                    },
                    "size": {
                        "type": "string",
                        "enum": ["1024x768", "1024x1024", "768x1024"],
                        "description": "输出图片尺寸，默认 1024x1024",
                    },
                    "input_images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "输入图片URL列表（可选）。用于图片编辑或多图合成",
                    },
                },
                "required": ["prompt"],
            },
            prompt_snippet="generate_image $ARGUMENTS — 生成或编辑图片，返回图片URL",
            prompt_guidelines=[
                "生成图片后，必须在最终回复中包含图片的markdown语法 `![描述](URL)`，以便用户直接在对话中看到图片。",
                "不要只描述图片内容而不展示图片链接。工具返回的图片URL必须原样保留在回复中。",
            ],
            timeout_seconds=120,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        prompt = params.get("prompt", "")
        size = params.get("size", "1024x1024")
        input_images = params.get("input_images", []) or []

        if not API_KEY:
            return ToolResult(
                content=[TextContent(text="错误：未设置 AGNES_API_KEY 环境变量")]
            )

        body: dict[str, Any] = {
            "model": "agnes-image-2.0-flash",
            "prompt": prompt,
            "size": size,
        }

        if input_images:
            body["tags"] = ["img2img"]
            body["extra_body"] = {
                "image": input_images,
                "response_format": "url",
            }

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(API_BASE, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            results = data.get("data", [])
            if not results:
                return ToolResult(
                    content=[TextContent(text=f"未生成图片: {json.dumps(data, ensure_ascii=False)}")]
                )

            urls = []
            for item in results:
                url = item.get("url", "")
                if url:
                    urls.append(url)

            if not urls:
                return ToolResult(
                    content=[TextContent(text="生成失败：未返回图片URL")])

            # Output image URLs wrapped in markdown for inline rendering in chat.
            # These become part of the assistant's response and persist across session reloads.
            md = "\n\n".join(f"![生成图片]({u})" for u in urls)
            # Build display payload for v1 SSE image content blocks
            display_images = [{"url": u, "size": size} for u in urls]
            return ToolResult(
                content=[TextContent(text=md)],
                details={"urls": urls, "size": size, "usage": data.get("usage", {})},
                display={"image": display_images[0] if len(display_images) == 1 else display_images},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                content=[TextContent(text=f"API 错误 ({e.response.status_code}): {e.response.text[:500]}")]
            )
        except Exception as e:
            return ToolResult(content=[TextContent(text=f"生成失败: {e}")])


agnes_image_tool = AgnesImageTool()
