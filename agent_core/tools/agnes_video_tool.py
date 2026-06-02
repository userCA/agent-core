"""Agnes Video generation tool — text-to-video, image-to-video, multi-image, keyframes."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult

API_BASE = "https://apihub.agnes-ai.com/v1/videos"
API_KEY = os.environ.get("AGNES_API_KEY", "")
REQUEST_TIMEOUT = 30
POLL_INTERVAL = 8
MAX_WAIT_SECONDS = 300
PROGRESS_INTERVAL = 15  # report progress to frontend every N seconds

VALID_FRAMES = {
    81, 121, 161, 201, 241, 281, 321, 361, 401, 441,
}


class AgnesVideoTool(Tool):
    """Generate videos using Agnes-Video-V2.0."""

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="generate_video",
            description=(
                "使用 Agnes-Video-V2.0 模型生成视频。"
                "支持文字转视频、图片转视频、多图视频、关键帧动画。"
                "视频生成需要等待，请耐心。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "视频描述。文字转视频：描述主体、动作、场景、镜头、灯光、风格。"
                            "图片转视频：描述哪些应移动，同时保持主体稳定。"
                        ),
                    },
                    "image": {
                        "type": "string",
                        "description": "输入图片URL（可选）。用于图片转视频",
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "多张输入图片URL列表（可选）。用于多图视频或关键帧动画",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["keyframes"],
                        "description": "设为 keyframes 进行关键帧动画（需配合 images 参数）",
                    },
                    "width": {
                        "type": "integer",
                        "description": "视频宽度，默认 1152",
                    },
                    "height": {
                        "type": "integer",
                        "description": "视频高度，默认 768",
                    },
                    "num_frames": {
                        "type": "integer",
                        "description": "帧数，必须为 8n+1 格式且 ≤441：81/121/161/201/241/281/321/361/401/441",
                    },
                    "frame_rate": {
                        "type": "integer",
                        "description": "帧率，默认 24",
                    },
                    "seed": {
                        "type": "integer",
                        "description": "随机种子（可选）。用于可重复结果",
                    },
                },
                "required": ["prompt"],
            },
            prompt_snippet="generate_video $ARGUMENTS — 生成视频，返回视频URL",
            prompt_guidelines=[
                "生成视频后，必须在最终回复中包含视频URL，以便用户查看。",
                "视频生成需要较长时间（通常1-5分钟），调用工具后耐心等待结果，不要重复调用。",
                "如果工具返回了 task_id 而不是视频URL，说明视频仍在生成中，告知用户稍后可以询问进度，不要重试。",
            ],
            timeout_seconds=MAX_WAIT_SECONDS + 30,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        prompt = params.get("prompt", "")
        image = params.get("image")
        images = params.get("images")
        mode = params.get("mode")
        width = params.get("width", 1152)
        height = params.get("height", 768)
        num_frames = params.get("num_frames", 121)
        frame_rate = params.get("frame_rate", 24)
        seed = params.get("seed")

        if not API_KEY:
            return ToolResult(
                content=[TextContent(text="错误：未设置 AGNES_API_KEY 环境变量")]
            )

        # Validate num_frames
        if num_frames > 441:
            num_frames = 121
        if num_frames not in VALID_FRAMES:
            # Round up to nearest valid frame count
            for f in sorted(VALID_FRAMES):
                if f >= num_frames:
                    num_frames = f
                    break
            else:
                num_frames = 121

        body: dict[str, Any] = {
            "model": "agnes-video-v2.0",
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }

        if image is not None:
            body["image"] = image

        if images is not None or mode is not None:
            extra: dict[str, Any] = {}
            if images is not None:
                extra["image"] = images
            if mode is not None:
                extra["mode"] = mode
            body["extra_body"] = extra

        if seed is not None:
            body["seed"] = seed

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(API_BASE, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            task_id = data.get("id", "")
            if not task_id:
                return ToolResult(
                    content=[TextContent(text=f"创建视频任务失败: {json.dumps(data, ensure_ascii=False)}")]
                )

            # Poll for completion with progress reporting
            started = asyncio.get_event_loop().time()
            last_progress = 0.0
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                while True:
                    elapsed = asyncio.get_event_loop().time() - started
                    if elapsed > MAX_WAIT_SECONDS:
                        return ToolResult(
                            content=[TextContent(
                                text=f"视频仍在生成中（已等待 {MAX_WAIT_SECONDS}s）。"
                                f"任务ID: {task_id}，请稍后询问'检查视频 {task_id}的状态'。"
                            )]
                        )

                    await asyncio.sleep(POLL_INTERVAL)

                    poll_resp = await client.get(
                        f"{API_BASE}/{task_id}", headers=headers
                    )
                    poll_resp.raise_for_status()
                    poll_data = poll_resp.json()

                    status = poll_data.get("status", "")
                    progress = poll_data.get("progress", 0)

                    # Send progress update to frontend (works in sequential mode)
                    if ctx and ctx.on_update and (elapsed - last_progress) >= PROGRESS_INTERVAL:
                        last_progress = elapsed
                        try:
                            ctx.on_update(ToolResult(
                                content=[TextContent(
                                    text=f"视频生成中... {status} ({progress}%)"
                                )]
                            ))
                        except Exception:
                            pass

                    if status == "completed":
                        video_url = poll_data.get("video_url", "")
                        seconds = poll_data.get("seconds", "?")
                        size = poll_data.get("size", "?")
                        if not video_url:
                            return ToolResult(
                                content=[TextContent(text="生成完成但未返回视频URL")]
                            )
                        return ToolResult(
                            content=[TextContent(
                                text=f"视频已生成！\n\n"
                                f"![视频封面]({video_url})\n\n"
                                f"**视频URL**: {video_url}\n"
                                f"**分辨率**: {size} | **时长**: {seconds}s"
                            )],
                            details={
                                "video_url": video_url,
                                "task_id": task_id,
                                "size": size,
                                "seconds": seconds,
                                "usage": poll_data.get("usage", {}),
                            },
                        )
                    elif status == "failed":
                        return ToolResult(
                            content=[TextContent(text=f"视频生成失败。任务ID: {task_id}")]
                        )
                    # else: queued or in_progress — keep polling

        except httpx.HTTPStatusError as e:
            return ToolResult(
                content=[TextContent(text=f"API 错误 ({e.response.status_code}): {e.response.text[:500]}")]
            )
        except Exception as e:
            return ToolResult(content=[TextContent(text=f"生成失败: {e}")])


agnes_video_tool = AgnesVideoTool()
