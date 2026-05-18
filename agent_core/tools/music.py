"""Text-to-music tool using Migu AI API."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "http://app.c.vip.migu.cn/aiTask/create/v1.0"
DEFAULT_QUERY_URL = "http://app.c.vip.migu.cn/aiTask/query/v1.0"
DEFAULT_UID = "123456"
DEFAULT_CHANNEL = "014000D"
POLL_INTERVAL = 3.0
POLL_MAX_ATTEMPTS = 60


class TextToMusicTool:
    """Generate music from text description via Migu AI."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        query_url: str | None = None,
        uid: str | None = None,
        channel: str | None = None,
    ) -> None:
        self._api_url = api_url or os.environ.get("MIGU_MUSIC_API_URL", DEFAULT_API_URL)
        self._query_url = query_url or os.environ.get("MIGU_MUSIC_QUERY_URL", DEFAULT_QUERY_URL)
        self._uid = uid or os.environ.get("MIGU_MUSIC_UID", DEFAULT_UID)
        self._channel = channel or os.environ.get("MIGU_MUSIC_CHANNEL", DEFAULT_CHANNEL)

        self.definition = ToolDefinition(
            name="text_to_music",
            description=(
                "根据文本描述生成音乐。支持中文提示词，如风格、情绪、场景等。"
                "生成过程需要几十秒到几分钟，请耐心等待。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "描述想要生成的音乐，如'一首轻快的流行歌曲，关于春天和花开'",
                    },
                    "count": {
                        "type": "integer",
                        "description": "生成数量（1-3），默认1",
                        "minimum": 1,
                        "maximum": 3,
                        "default": 1,
                    },
                    "style": {
                        "type": "string",
                        "description": "音乐风格，如流行、古典、摇滚、电子、民谣等",
                    },
                },
                "required": ["prompt"],
            },
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        prompt = params.get("prompt", "")
        count = min(max(params.get("count", 1), 1), 3)
        style = params.get("style", "")

        # Combine style into prompt if provided
        full_prompt = prompt
        if style:
            full_prompt = f"[{style}] {prompt}"

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "uid": self._uid,
            "msisdn": "",
            "Trust-Headers": "uid,msisdn",
            "channel": self._channel,
        }

        payload = {
            "inputModel": {
                "contents": [
                    {"type": "TEXT", "content": full_prompt}
                ],
                "metaInfo": {
                    "relatedTaskId": "",
                    "hit_cache_url": "",
                    "hit_cache_title": "",
                    "hit_cache_lyric": "",
                    "hit_cache_cover": "",
                },
            },
            "platform": "aigc-text2music",
            "outputOption": {
                "type": "AUDIO",
                "count": count,
                "sync": False,
            },
            "priority": 0,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: Create task
                logger.info("Creating music task: %s", full_prompt)
                resp = await client.post(self._api_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                logger.debug("Create response: %s", data)

                task_id = self._extract_task_id(data)
                if not task_id:
                    return ToolResult(
                        content=[TextContent(text=f"创建任务失败: {data}")]
                    )

                # Step 2: Poll for result
                result = await self._poll_result(client, headers, task_id, ctx)
                return ToolResult(content=[TextContent(text=result)])

        except httpx.HTTPStatusError as exc:
            text = f"HTTP {exc.response.status_code}: {exc.response.text}"
            logger.warning("Music API error: %s", text)
            return ToolResult(content=[TextContent(text=text)], details={"error": text})
        except Exception as exc:
            logger.exception("Music generation failed")
            return ToolResult(
                content=[TextContent(text=f"生成音乐失败: {exc}")],
                details={"error": str(exc)},
            )

    def _extract_task_id(self, data: dict[str, Any]) -> str | None:
        """Extract task ID from create response."""
        # Try common response shapes
        if isinstance(data, dict):
            # Direct taskId
            if "taskId" in data:
                return str(data["taskId"])
            # Nested in data
            nested = data.get("data") or data.get("result") or data.get("body")
            if isinstance(nested, dict):
                if "taskId" in nested:
                    return str(nested["taskId"])
                if "id" in nested:
                    return str(nested["id"])
        return None

    async def _poll_result(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        task_id: str,
        ctx: ToolContext,
    ) -> str:
        """Poll query endpoint until task completes or times out."""
        query_payload = {
            "taskId": task_id,
            "platform": "aigc-text2music",
        }

        for attempt in range(POLL_MAX_ATTEMPTS):
            if ctx.signal.is_set():
                return f"任务 {task_id} 已取消"

            resp = await client.get(
                self._query_url,
                headers=headers,
                params=query_payload,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.debug("Poll #%d response: %s", attempt, data)

            status = self._extract_status(data)
            if status in ("SUCCESS", "COMPLETED", "FINISHED", "DONE"):
                urls = self._extract_audio_urls(data)
                if urls:
                    lines = [f"音乐生成完成！任务ID: {task_id}"]
                    for i, url in enumerate(urls, 1):
                        lines.append(f"  音频 {i}: {url}")
                    return "\n".join(lines)
                return f"任务完成，但未找到音频URL。原始响应: {data}"

            if status in ("FAILED", "ERROR", "FAILURE"):
                return f"任务失败: {data}"

            # Push progress update so the UI doesn't appear frozen
            if ctx.on_update is not None:
                progress = f"第 {attempt + 1} 次查询，状态: {status or '处理中'}…"
                ctx.on_update(ToolResult(content=[TextContent(text=progress)]))

            await asyncio.sleep(POLL_INTERVAL)

        return f"任务 {task_id} 轮询超时，请稍后手动查询结果"

    def _extract_status(self, data: dict[str, Any]) -> str | None:
        """Extract task status from query response."""
        if isinstance(data, dict):
            for key in ("status", "taskStatus", "state", "taskState"):
                if key in data:
                    val = data[key]
                    if isinstance(val, str):
                        return val.upper()
            nested = data.get("data") or data.get("result") or data.get("body")
            if isinstance(nested, dict):
                for key in ("status", "taskStatus", "state", "taskState"):
                    if key in nested:
                        val = nested[key]
                        if isinstance(val, str):
                            return val.upper()
        return None

    def _extract_audio_urls(self, data: dict[str, Any]) -> list[str]:
        """Extract audio URLs from completed task response."""
        urls: list[str] = []
        if not isinstance(data, dict):
            return urls

        # Try various response shapes
        for root in (data, data.get("data"), data.get("result"), data.get("body")):
            if not isinstance(root, dict):
                continue
            # Look for output/result/audios/contents array
            for out_key in ("output", "outputs", "result", "results", "audios", "audioList", "contents"):
                out = root.get(out_key)
                if isinstance(out, list):
                    for item in out:
                        if isinstance(item, dict):
                            for url_key in ("url", "audioUrl", "fileUrl", "downloadUrl", "link", "content"):
                                val = item.get(url_key)
                                if val and isinstance(val, str):
                                    urls.append(val)
                        elif isinstance(item, str):
                            urls.append(item)
                elif isinstance(out, dict):
                    for url_key in ("url", "audioUrl", "fileUrl", "downloadUrl", "link", "content"):
                        val = out.get(url_key)
                        if val and isinstance(val, str):
                            urls.append(val)

            # Look for single url at top level
            for url_key in ("url", "audioUrl", "fileUrl", "downloadUrl"):
                val = root.get(url_key)
                if val and isinstance(val, str):
                    urls.append(val)

        return list(dict.fromkeys(urls))  # dedupe preserving order


def create_text_to_music_tool(
    *,
    api_url: str | None = None,
    query_url: str | None = None,
    uid: str | None = None,
    channel: str | None = None,
) -> TextToMusicTool:
    return TextToMusicTool(
        api_url=api_url,
        query_url=query_url,
        uid=uid,
        channel=channel,
    )


text_to_music_tool = TextToMusicTool()
