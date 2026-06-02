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
QUICK_POLL_SECONDS = 30   # quick poll window before returning task_id
QUICK_POLL_INTERVAL = 6   # short interval for quick checks

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
            prompt_snippet="当用户要求生成视频、制作视频时，必须调用 generate_video 工具。只调用一次，等待结果。",
            prompt_guidelines=[
                "用户说'生成视频'时必须调用 generate_video，不要只描述而不调用。",
                "只调用一次！返回结果后不要再调用第二次。",
                "如果返回了视频URL，在回复中展示给用户。",
                "如果返回了 task_id（视频仍在生成中），告诉用户'视频正在后台生成，预计2-5分钟，稍后可以让我检查进度'。",
            ],
            timeout_seconds=QUICK_POLL_SECONDS + 10,
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

        # Validate: keyframes mode requires images
        if mode == "keyframes" and not images and not image:
            return ToolResult(
                content=[TextContent(
                    text="错误：关键帧模式（keyframes）必须提供 images 参数（至少2张图片URL）。"
                    "请使用文字转视频模式（不传 mode 参数），或提供图片URL列表。"
                )]
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

            # Quick poll: return result immediately if video completes fast,
            # otherwise return task_id so the frontend doesn't block waiting.
            started = asyncio.get_event_loop().time()
            last_status = ""
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                while True:
                    elapsed = asyncio.get_event_loop().time() - started
                    if elapsed > QUICK_POLL_SECONDS:
                        return ToolResult(
                            content=[TextContent(
                                text=f"视频任务已创建，正在后台生成中。"
                                f"任务ID: {task_id}，当前状态: {last_status or 'queued'}。"
                                f"通常需要2-5分钟，请告诉用户稍后询问进度。不要重复调用。"
                            )]
                        )

                    await asyncio.sleep(QUICK_POLL_INTERVAL)

                    poll_resp = await client.get(
                        f"{API_BASE}/{task_id}", headers=headers
                    )
                    poll_resp.raise_for_status()
                    poll_data = poll_resp.json()

                    status = poll_data.get("status", "")
                    last_status = status

                    if status == "completed":
                        video_url = (
                            poll_data.get("remixed_from_video_id", "")
                            or poll_data.get("video_url", "")
                        )
                        if not video_url:
                            return ToolResult(
                                content=[TextContent(
                                    text=f"视频生成完成但未返回视频URL。"
                                    f"任务ID: {task_id}，原始响应: {json.dumps(poll_data, ensure_ascii=False)}"
                                )]
                            )
                        seconds = poll_data.get("seconds", "?")
                        size = poll_data.get("size", "?")
                        return ToolResult(
                            content=[TextContent(
                                text=f"视频已生成！\n"
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
                        error_info = poll_data.get("error", "")
                        return ToolResult(
                            content=[TextContent(
                                text=f"视频生成失败。任务ID: {task_id}，错误: {error_info}"
                            )]
                        )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                content=[TextContent(text=f"API 错误 ({e.response.status_code}): {e.response.text[:500]}")]
            )
        except Exception as e:
            return ToolResult(content=[TextContent(text=f"生成失败: {e}")])


class CheckVideoTool(Tool):
    """Query the status of a previously submitted video generation task."""

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="check_video_status",
            description="查询视频生成任务的进度。传入 task_id，返回当前状态和视频URL（如已完成）。",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "视频任务ID，由 generate_video 返回",
                    },
                },
                "required": ["task_id"],
            },
            prompt_snippet="check_video_status $ARGUMENTS — 查询视频任务进度",
            prompt_guidelines=[
                "当用户问'视频好了吗'、'检查进度'时，调用此工具查询。",
                "只调用一次。如果视频已完成，把URL展示给用户。",
            ],
            timeout_seconds=15,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        task_id = params.get("task_id", "")
        if not task_id:
            return ToolResult(content=[TextContent(text="请提供 task_id")])

        if not API_KEY:
            return ToolResult(content=[TextContent(text="错误：未设置 AGNES_API_KEY")])

        headers = {"Authorization": f"Bearer {API_KEY}"}
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(f"{API_BASE}/{task_id}", headers=headers)
                resp.raise_for_status()
                data = resp.json()

            status = data.get("status", "?")
            progress = data.get("progress", 0)

            if status == "completed":
                video_url = data.get("remixed_from_video_id", "") or data.get("video_url", "")
                if video_url:
                    return ToolResult(
                        content=[TextContent(
                            text=f"视频已生成！\n"
                            f"**视频URL**: {video_url}\n"
                            f"**分辨率**: {data.get('size', '?')} | **时长**: {data.get('seconds', '?')}s"
                        )],
                        details={
                            "video_url": video_url,
                            "task_id": task_id,
                            "size": data.get("size"),
                            "seconds": data.get("seconds"),
                            "usage": data.get("usage", {}),
                        },
                    )
                return ToolResult(content=[TextContent(
                    text=f"视频已完成但未返回URL。任务ID: {task_id}"
                )])
            elif status == "failed":
                return ToolResult(content=[TextContent(
                    text=f"视频生成失败。任务ID: {task_id}，错误: {data.get('error', '')}"
                )])
            else:
                return ToolResult(content=[TextContent(
                    text=f"视频仍在生成中。状态: {status} ({progress}%)，任务ID: {task_id}"
                )])
        except Exception as e:
            return ToolResult(content=[TextContent(text=f"查询失败: {e}")])


agnes_video_tool = AgnesVideoTool()
check_video_tool = CheckVideoTool()
