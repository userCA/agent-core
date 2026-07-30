"""Short drama pipeline: anchor stills → image-to-video → ffmpeg concat."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.core.human_input import RequiresHumanInput
from agent_core.planning.store import PlanStore
from agent_core.tools import agnes_client
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult
from agent_core.tools.media_utils import (
    default_public_base_url,
    resolve_media_list,
)
from agent_core.tools.video_concat_tool import concat_videos

logger = logging.getLogger(__name__)

MAX_SHOTS = 8
STILL_PARALLEL = 3
PIPELINE_TIMEOUT_SECONDS = 3600
VIDEO_NUM_FRAMES = 121
VIDEO_FRAME_RATE = 24

ASPECT_PRESETS: dict[str, dict[str, Any]] = {
    "9:16": {
        "image_size": "768x1024",
        "width": 768,
        "height": 1152,
    },
    "16:9": {
        "image_size": "1024x768",
        "width": 1152,
        "height": 768,
    },
}


class _PlanReporter:
    """Push plan snapshots through PlanStore + ToolContext.on_update."""

    def __init__(
        self,
        store: PlanStore | None,
        ctx: ToolContext | None,
        title: str,
    ) -> None:
        self._store = store
        self._ctx = ctx
        self._title = title
        self._initialized = False

    async def init_steps(self, shot_count: int) -> None:
        if self._store is None:
            return
        steps: list[dict[str, Any]] = [{"id": "anchors", "title": "确认人物锚点", "status": "completed"}]
        for i in range(1, shot_count + 1):
            steps.append(
                {"id": f"still_{i}", "title": f"生成静帧 {i}/{shot_count}", "status": "pending"}
            )
        for i in range(1, shot_count + 1):
            steps.append(
                {"id": f"video_{i}", "title": f"生成视频 {i}/{shot_count}", "status": "pending"}
            )
        steps.extend(
            [
                {"id": "concat", "title": "拼接成片", "status": "pending"},
                {"id": "done", "title": "完成", "status": "pending"},
            ]
        )
        self._store.replace(title=self._title, steps=steps)
        await self._emit("replaced")
        self._initialized = True

    async def start(self, step_id: str, detail: str | None = None) -> None:
        if self._store is None:
            return
        self._store.set_status(step_id=step_id, status="in_progress", detail=detail)
        await self._emit("updated")

    async def complete(self, step_id: str, detail: str | None = None) -> None:
        if self._store is None:
            return
        self._store.set_status(step_id=step_id, status="completed", detail=detail)
        await self._emit("updated")

    async def fail(self, step_id: str, detail: str | None = None) -> None:
        if self._store is None:
            return
        self._store.set_status(step_id=step_id, status="failed", detail=detail)
        await self._emit("error")

    async def finish(self) -> None:
        if self._store is None:
            return
        self._store.complete_plan()
        await self._emit("completed")

    async def _emit(self, phase: str) -> None:
        if self._store is None:
            return
        await self._store.persist()
        payload = self._store.snapshot_payload(phase=phase)
        if self._ctx and self._ctx.on_update is not None:
            self._ctx.on_update(
                ToolResult(
                    content=[TextContent(text="")],
                    details={"plan": payload},
                )
            )


def _normalize_characters(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        if not cid:
            continue
        anchors = item.get("anchor_urls") or []
        if not isinstance(anchors, list):
            anchors = [anchors] if anchors else []
        out.append(
            {
                "id": cid,
                "name": str(item.get("name") or cid),
                "anchor_urls": [str(u) for u in anchors if u],
            }
        )
    return out


def _normalize_shots(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or f"s{len(out) + 1}")
        order = int(item.get("order") or len(out) + 1)
        char_ids = item.get("character_ids") or []
        if not isinstance(char_ids, list):
            char_ids = [char_ids]
        out.append(
            {
                "id": sid,
                "order": order,
                "character_ids": [str(c) for c in char_ids if c],
                "still_prompt": str(item.get("still_prompt") or ""),
                "motion_prompt": str(item.get("motion_prompt") or item.get("still_prompt") or ""),
            }
        )
    out.sort(key=lambda s: s["order"])
    return out[:MAX_SHOTS]


def _merge_hitl_anchors(
    characters: list[dict[str, Any]],
    params: dict[str, Any],
) -> None:
    """Apply top-level HITL field values (keyed by character id) onto characters."""
    for char in characters:
        cid = char["id"]
        if char["anchor_urls"]:
            continue
        hitl_val = params.get(cid)
        if hitl_val is None:
            continue
        if isinstance(hitl_val, list):
            char["anchor_urls"] = [str(v) for v in hitl_val if v]
        elif hitl_val:
            char["anchor_urls"] = [str(hitl_val)]


def _missing_anchor_characters(characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in characters if not c["anchor_urls"]]


def _build_anchor_hitl_schema(missing: list[dict[str, Any]]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for char in missing:
        fields.append(
            {
                "name": char["id"],
                "label": f"{char['name']}（{char['id']}）锚点图",
                "type": "image_upload",
                "required": True,
                "max": 3,
                "accept": "image/*",
            }
        )
    names = "、".join(c["name"] for c in missing)
    return {
        "type": "anchor_form",
        "title": "上传人物锚点图",
        "fields": fields,
        "description": f"请上传以下角色的参考图，系统将严格以这些图片作为人物身份锚点：{names}",
    }


def _collect_anchor_urls(
    characters: list[dict[str, Any]],
    character_ids: list[str],
) -> list[str]:
    by_id = {c["id"]: c for c in characters}
    urls: list[str] = []
    for cid in character_ids:
        char = by_id.get(cid)
        if char:
            urls.extend(char.get("anchor_urls") or [])
    return list(dict.fromkeys(urls))


async def _generate_still_with_retry(
    *,
    prompt: str,
    anchors: list[str],
    image_size: str,
    retries: int = 1,
) -> str:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            urls = await agnes_client.generate_image_urls(
                prompt=prompt,
                size=image_size,
                input_images=anchors or None,
            )
            return urls[0]
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                await asyncio.sleep(1.0)
    raise RuntimeError(str(last_err or "静帧生成失败"))


async def _generate_video_with_retry(
    *,
    prompt: str,
    image: str,
    width: int,
    height: int,
    retries: int = 1,
) -> str:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = await agnes_client.generate_video_from_image(
                prompt=prompt,
                image=image,
                width=width,
                height=height,
                num_frames=VIDEO_NUM_FRAMES,
                frame_rate=VIDEO_FRAME_RATE,
            )
            return str(result["video_url"])
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                await asyncio.sleep(2.0)
    raise RuntimeError(str(last_err or "视频生成失败"))


class ShortDramaPipelineTool:
    """Orchestrate short drama MV generation inside agent-core."""

    def __init__(self, *, plan_store: PlanStore | None = None) -> None:
        self._plan_store = plan_store
        self.definition = ToolDefinition(
            name="create_short_drama",
            description=(
                "全自动短剧流水线：基于用户上传的人物锚点图，生成分镜静帧、图生视频，并拼接为竖屏/横屏 MV。"
                "当用户要求制作短剧、多镜头剧情视频、MV 拼接时使用此工具。"
                "需要 structured 参数：title、characters、shots。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "短剧标题"},
                    "aspect_ratio": {
                        "type": "string",
                        "enum": ["9:16", "16:9"],
                        "description": "画幅，默认 9:16 竖屏",
                    },
                    "characters": {
                        "type": "array",
                        "description": "角色列表，每角色需 id/name/anchor_urls",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "anchor_urls": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["id", "name"],
                        },
                    },
                    "shots": {
                        "type": "array",
                        "description": "分镜列表，最多 8 镜",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "order": {"type": "integer"},
                                "character_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "still_prompt": {"type": "string"},
                                "motion_prompt": {"type": "string"},
                            },
                            "required": ["still_prompt", "motion_prompt"],
                        },
                    },
                },
                "required": ["title", "characters", "shots"],
            },
            prompt_snippet=(
                "create_short_drama $ARGUMENTS — 短剧流水线（锚点静帧→图生视频→拼接成片）"
            ),
            prompt_guidelines=[
                "用户要制作短剧、分镜剧情视频、MV 时，必须立即调用 create_short_drama，不要零散多次 generate_video。",
                "先从自然语言提取 title、characters、shots（≤8 镜），再调用本工具。",
                "characters 中 anchor_urls 必须留空数组 []；工具会自动通过 HITL 让用户上传锚点图。",
                "禁止在无用户锚点的情况下用 generate_image 发明新角色脸。",
                "禁止向用户索要图片 URL/路径——系统已自动存储用户上传图片，工具可直接引用。",
                "禁止先调 manage_plan 或 confirm，必须直接调 create_short_drama。",
                "HITL 返回锚点图后，系统会自动续跑本工具，无需用户再说「继续」。",
                "重要：HITL 完成后不要再调用 confirm 工具。",
            ],
            timeout_seconds=PIPELINE_TIMEOUT_SECONDS,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        del tool_call_id

        if not agnes_client.api_key_configured():
            return ToolResult(content=[TextContent(text="错误：未设置 AGNES_API_KEY 环境变量")])

        title = str(params.get("title") or "短剧").strip()
        aspect = str(params.get("aspect_ratio") or "9:16")
        preset = ASPECT_PRESETS.get(aspect, ASPECT_PRESETS["9:16"])

        characters = _normalize_characters(params.get("characters"))
        shots = _normalize_shots(params.get("shots"))
        if not characters:
            return ToolResult(content=[TextContent(text="错误：至少需要一个角色（characters）")])
        if not shots:
            return ToolResult(content=[TextContent(text="错误：至少需要一个分镜（shots）")])

        _merge_hitl_anchors(characters, params)
        missing = _missing_anchor_characters(characters)
        if missing:
            raise RequiresHumanInput(
                prompt=f"请上传以下角色的锚点参考图：{'、'.join(c['name'] for c in missing)}",
                input_schema=_build_anchor_hitl_schema(missing),
            )

        cwd = (ctx.metadata.get("cwd") if ctx else None) or os.getcwd()
        public_base = (ctx.metadata.get("public_base_url") if ctx else None) or default_public_base_url()

        for char in characters:
            char["anchor_urls"] = resolve_media_list(
                char["anchor_urls"], cwd=cwd, public_base_url=public_base
            )

        reporter = _PlanReporter(self._plan_store, ctx, title)
        await reporter.init_steps(len(shots))

        still_urls: list[str] = []
        video_urls: list[str] = []
        shot_summaries: list[dict[str, Any]] = []

        try:
            # --- still frames (limited parallelism) ---
            sem = asyncio.Semaphore(STILL_PARALLEL)

            async def _one_still(idx: int, shot: dict[str, Any]) -> tuple[int, str]:
                async with sem:
                    step_id = f"still_{idx}"
                    await reporter.start(step_id, detail=shot["id"])
                    anchors = _collect_anchor_urls(characters, shot["character_ids"])
                    prompt = (
                        f"{shot['still_prompt']}。"
                        "严格保持参考图中人物的脸型、发型与服装一致，不要更换角色身份。"
                    )
                    url = await _generate_still_with_retry(
                        prompt=prompt,
                        anchors=anchors,
                        image_size=preset["image_size"],
                    )
                    await reporter.complete(step_id, detail=url[:120])
                    return idx, url

            still_tasks = [_one_still(i, shot) for i, shot in enumerate(shots, start=1)]
            still_results = await asyncio.gather(*still_tasks, return_exceptions=True)
            ordered_stills: dict[int, str] = {}
            for item in still_results:
                if isinstance(item, Exception):
                    await reporter.fail("still_1", detail=str(item))
                    raise item
                idx, url = item
                ordered_stills[idx] = url
            still_urls = [ordered_stills[i] for i in range(1, len(shots) + 1)]
            for idx, url in enumerate(still_urls, start=1):
                shot_summaries.append({"shot_index": idx, "still_url": url})

            # --- image-to-video (serial) ---
            for idx, shot in enumerate(shots, start=1):
                step_id = f"video_{idx}"
                await reporter.start(step_id, detail=shot["id"])
                still_url = still_urls[idx - 1]
                try:
                    video_url = await _generate_video_with_retry(
                        prompt=shot["motion_prompt"],
                        image=still_url,
                        width=preset["width"],
                        height=preset["height"],
                    )
                except Exception as exc:
                    await reporter.fail(step_id, detail=str(exc))
                    raise
                video_urls.append(video_url)
                shot_summaries[idx - 1]["video_url"] = video_url
                await reporter.complete(step_id, detail=video_url[:120])

            # --- concat ---
            await reporter.start("concat")
            _, final_url = await concat_videos(
                video_urls,
                name=title,
                cwd=cwd,
                public_base_url=public_base,
            )
            await reporter.complete("concat", detail=final_url)
            await reporter.complete("done")
            await reporter.finish()

        except Exception as exc:
            logger.warning("create_short_drama failed: %s", exc)
            partial = "\n".join(f"- 镜 {i + 1} 视频: {u}" for i, u in enumerate(video_urls))
            msg = f"短剧流水线失败: {exc}"
            if partial:
                msg += f"\n\n已生成片段:\n{partial}"
            return ToolResult(
                content=[TextContent(text=msg)],
                details={
                    "error": str(exc),
                    "shots": shot_summaries,
                    "video_clips": video_urls,
                },
                display={"type": "plan_error", "error": str(exc)},
            )

        text = (
            f"短剧《{title}》已生成！\n"
            f"**视频URL**: {final_url}\n"
            f"**镜头数**: {len(shots)} | **画幅**: {aspect}"
        )
        return ToolResult(
            content=[TextContent(text=text)],
            details={
                "video_url": final_url,
                "title": title,
                "aspect_ratio": aspect,
                "shots": shot_summaries,
            },
            display={"video": {"url": final_url}},
        )


def create_short_drama_tool(*, plan_store: PlanStore | None = None) -> ShortDramaPipelineTool:
    return ShortDramaPipelineTool(plan_store=plan_store)
