"""AIGC content creation tool for Migu AI."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from agent_core.core.content import TextContent
from agent_core.core.human_input import RequiresHumanInput
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

_DEFAULT_CREATE_URL = os.environ.get(
    "MIGU_AIGC_CREATE_URL", "http://app.c.vip.migu.cn/user/h5/ai-gc/create/v1.0"
)
_DEFAULT_QUERY_URL = os.environ.get(
    "MIGU_AIGC_QUERY_URL", "http://app.c.vip.migu.cn/user/h5/ai-gc/query/v1.0"
)
_DEFAULT_CHANNEL = "014000D"
_DEFAULT_UID = ""
_DEFAULT_DEVICE_ID = ""
_DEFAULT_POLL_INTERVAL = 3.0
_DEFAULT_POLL_MAX_ATTEMPTS = 60


def _generate_session_id() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16]


@dataclass
class AigcToolConfig:
    """Generic configuration shared across AIGC creation tools."""

    api_url: str | None = None
    query_url: str | None = None
    uid: str | None = None
    device_id: str | None = None
    channel: str | None = None
    poll_interval: float = _DEFAULT_POLL_INTERVAL
    poll_max_attempts: int = _DEFAULT_POLL_MAX_ATTEMPTS


class AigcCreationTool:
    """Generic AIGC content creation tool for Migu AI."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        scene: str,
        content_type: str,
        config: AigcToolConfig | None = None,
        hitl_schema_builder: Callable[[list[str]], dict[str, Any]] | None = None,
    ) -> None:
        cfg = config or AigcToolConfig()
        self._scene = scene
        self._content_type = content_type
        self._api_url = cfg.api_url or _DEFAULT_CREATE_URL
        self._query_url = cfg.query_url or _DEFAULT_QUERY_URL
        self._uid = cfg.uid
        self._device_id = cfg.device_id
        self._channel = cfg.channel
        self._poll_interval = cfg.poll_interval
        self._poll_max_attempts = cfg.poll_max_attempts
        self._hitl_schema_builder = hitl_schema_builder

        self.definition = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        del tool_call_id  # unused
        # 1. Resolve auth
        auth_headers = self._resolve_auth(ctx.metadata)

        # 2. Check required params
        required = self.definition.parameters.get("required", [])
        missing = [p for p in required if p not in params or params[p] in (None, "", [])]
        if missing and self._hitl_schema_builder is not None:
            raise RequiresHumanInput(
                prompt="请补充以下创作参数",
                input_schema=self._hitl_schema_builder(missing),
            )
        if missing:
            return ToolResult(
                content=[TextContent(text=f"缺少必需参数: {', '.join(missing)}")]
            )

        # 3. Build payload and create task
        payload = self._build_payload(params, auth_headers)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info("Creating AIGC task: scene=%s", self._scene)
                resp = await client.post(
                    self._api_url, headers=auth_headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                logger.debug("Create response: %s", data)

                task_id = self._extract_task_id(data)
                if not task_id:
                    return ToolResult(
                        content=[TextContent(text=f"创建任务失败: {data}")]
                    )

                # 4. Poll for result
                result = await self._poll_result(client, auth_headers, task_id, ctx)
                return ToolResult(content=[TextContent(text=result)])

        except httpx.HTTPStatusError as exc:
            text = f"HTTP {exc.response.status_code}: {exc.response.text}"
            logger.warning("AIGC API error: %s", text)
            return ToolResult(content=[TextContent(text=text)], details={"error": text})
        except Exception as exc:
            logger.exception("AIGC creation failed")
            return ToolResult(
                content=[TextContent(text=f"创作失败: {exc}")],
                details={"error": str(exc)},
            )

    def _resolve_auth(self, metadata: dict[str, Any]) -> dict[str, str]:
        """Resolve auth from metadata > constructor > env > defaults."""
        auth = metadata.get("aigc_auth", {})
        return {
            "Content-Type": "application/json; charset=utf-8",
            "uid": auth.get("uid") or self._uid or os.environ.get("MIGU_UID") or _DEFAULT_UID,
            "deviceid": auth.get("deviceid")
            or self._device_id
            or os.environ.get("MIGU_DEVICE_ID")
            or _DEFAULT_DEVICE_ID,
            "channel": auth.get("channel")
            or self._channel
            or os.environ.get("MIGU_CHANNEL")
            or _DEFAULT_CHANNEL,
            "pacmtoken": auth.get("pacmtoken") or os.environ.get("MIGU_PACM_TOKEN") or "",
        }

    def _build_payload(
        self, params: dict[str, Any], auth_headers: dict[str, str]
    ) -> dict[str, Any]:
        # inputMeta receives all params except known list fields
        input_meta: dict[str, Any] = {}
        for key, val in params.items():
            if key == "input_images":
                continue
            input_meta[key] = val

        # Build aigcInputContentList from image inputs
        content_list: list[dict[str, Any]] = []
        for img_id in params.get("input_images", []):
            content_list.append(
                {
                    "contentType": "pic",
                    "picType": "thirdParty",
                    "picFileId": img_id,
                    "contentMeta": {"rawFileId": img_id},
                }
            )

        return {
            "scene": self._scene,
            "taskSessionId": _generate_session_id(),
            "aigcContentResultInput": {"contentType": self._content_type},
            "ext": {"rcToken": auth_headers.get("pacmtoken", "")},
            "inputContent": {
                "inputMeta": input_meta,
                "aigcInputContentList": content_list,
            },
        }

    def _extract_task_id(self, data: dict[str, Any]) -> str | None:
        if not isinstance(data, dict):
            return None
        if "taskId" in data:
            return str(data["taskId"])
        for key in ("data", "result", "body"):
            nested = data.get(key)
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
        for attempt in range(self._poll_max_attempts):
            if ctx.signal.is_set():
                return f"任务 {task_id} 已取消"

            resp = await client.get(
                self._query_url,
                headers=headers,
                params={"taskId": task_id},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.debug("Poll #%d response: %s", attempt, data)

            status = self._extract_status(data)
            if status in ("SUCCESS", "COMPLETED", "FINISHED", "DONE"):
                urls = self._extract_result_urls(data)
                if urls:
                    lines = [f"创作完成！任务ID: {task_id}"]
                    for i, url in enumerate(urls, 1):
                        lines.append(f"  结果 {i}: {url}")
                    return "\n".join(lines)
                return f"任务完成，但未找到结果URL。原始响应: {data}"

            if status in ("FAILED", "ERROR", "FAILURE"):
                error_msg = self._extract_error(data)
                return f"创作失败: {error_msg or data}"

            if ctx.on_update is not None:
                progress = f"创作中... 第 {attempt + 1} 次查询，状态: {status or '处理中'}"
                ctx.on_update(ToolResult(content=[TextContent(text=progress)]))

            await asyncio.sleep(self._poll_interval)

        return f"轮询超时，任务ID: {task_id}"

    def _extract_status(self, data: dict[str, Any]) -> str | None:
        if not isinstance(data, dict):
            return None
        for key in ("status", "taskStatus", "state", "taskState"):
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    return val.upper()
        for root_key in ("data", "result", "body"):
            nested = data.get(root_key)
            if isinstance(nested, dict):
                for key in ("status", "taskStatus", "state", "taskState"):
                    if key in nested:
                        val = nested[key]
                        if isinstance(val, str):
                            return val.upper()
        return None

    def _extract_result_urls(self, data: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        if not isinstance(data, dict):
            return urls
        for root in (data, data.get("data"), data.get("result"), data.get("body")):
            if not isinstance(root, dict):
                continue
            for out_key in ("output", "outputs", "result", "results", "urls", "urlList", "contents"):
                out = root.get(out_key)
                if isinstance(out, list):
                    for item in out:
                        if isinstance(item, dict):
                            for url_key in ("url", "fileUrl", "downloadUrl", "link", "content"):
                                val = item.get(url_key)
                                if val and isinstance(val, str):
                                    urls.append(val)
                        elif isinstance(item, str):
                            urls.append(item)
                elif isinstance(out, dict):
                    for url_key in ("url", "fileUrl", "downloadUrl", "link", "content"):
                        val = out.get(url_key)
                        if val and isinstance(val, str):
                            urls.append(val)
            for url_key in ("url", "fileUrl", "downloadUrl"):
                val = root.get(url_key)
                if val and isinstance(val, str):
                    urls.append(val)
        return list(dict.fromkeys(urls))

    def _extract_error(self, data: dict[str, Any]) -> str | None:
        if not isinstance(data, dict):
            return None
        for key in ("error", "errorMessage", "errMsg", "message", "msg"):
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    return val
        for root_key in ("data", "result", "body"):
            nested = data.get(root_key)
            if isinstance(nested, dict):
                for key in ("error", "errorMessage", "errMsg", "message", "msg"):
                    if key in nested:
                        val = nested[key]
                        if isinstance(val, str):
                            return val
        return None


def _nolo_hitl_schema(missing: list[str]) -> dict[str, Any]:
    """Build HITL input schema for nolo video creation."""
    fields: list[dict[str, Any]] = []
    if "templateId" in missing:
        fields.append(
            {
                "name": "templateId",
                "label": "模板",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "426", "label": "时光温柔"},
                    {"value": "427", "label": "夏日海边"},
                ],
            }
        )
    if "input_images" in missing:
        fields.append(
            {
                "name": "input_images",
                "label": "上传照片",
                "type": "image_upload",
                "required": True,
                "max": 3,
                "accept": ["image/jpeg", "image/png"],
            }
        )
    return {
        "type": "template_form",
        "title": "选择视频创作模板",
        "fields": fields,
    }


def create_nolo_video_tool(
    *,
    api_url: str | None = None,
    query_url: str | None = None,
    uid: str | None = None,
    device_id: str | None = None,
    channel: str | None = None,
) -> AigcCreationTool:
    """Create nolo scene video generation tool."""
    return AigcCreationTool(
        name="create_nolo_video",
        description="生成nolo场景视频。需要选择模板并上传照片。",
        scene="nolo",
        content_type="video",
        parameters={
            "type": "object",
            "properties": {
                "templateId": {
                    "type": "string",
                    "description": "视频模板ID（可选，默认426-时光温柔）",
                },
                "aiTemplateName": {
                    "type": "string",
                    "description": "模板名称（可选，默认时光温柔）",
                },
                "input_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "输入照片URL或fileId列表（1-3张）",
                },
                "gender": {
                    "type": "string",
                    "description": "性别（可选）",
                },
                "messageData": {
                    "type": "string",
                    "description": "附加消息数据JSON字符串（可选）",
                },
            },
            "required": ["templateId", "input_images"],
        },
        hitl_schema_builder=_nolo_hitl_schema,
        config=AigcToolConfig(
            api_url=api_url,
            query_url=query_url,
            uid=uid,
            device_id=device_id,
            channel=channel,
        ),
    )
