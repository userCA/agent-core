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
    to_data_uri,
)
from agent_core.tools.video_concat_tool import concat_videos
from agent_core.tools.video_frame import extract_last_frame_url

logger = logging.getLogger(__name__)

MAX_SHOTS = 8
PIPELINE_TIMEOUT_SECONDS = 3600
VIDEO_NUM_FRAMES = 121
VIDEO_FRAME_RATE = 24
DEFAULT_CROSSFADE_SECONDS = 0.25

VALID_TRANSITIONS = frozenset({"hard_cut", "match_cut", "dissolve"})
VALID_POSITIONS = frozenset({"left", "center", "right"})
SCENE_HITL_PREFIX = "scene_"

POSITION_LABELS = {
    "left": "左侧",
    "center": "中央",
    "right": "右侧",
}

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

BRIDGE_SCHEME = "C"  # 静帧链 + 单图 i2v；末帧作下一镜参考图


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
            bridge = f"（承接镜 {i - 1} 末帧）" if i > 1 else ""
            steps.append(
                {"id": f"still_{i}", "title": f"生成静帧 {i}/{shot_count}{bridge}", "status": "pending"}
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


def _normalize_scenes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        anchors = item.get("anchor_urls") or []
        if not isinstance(anchors, list):
            anchors = [anchors] if anchors else []
        out.append(
            {
                "id": sid,
                "name": str(item.get("name") or sid),
                "anchor_urls": [str(u) for u in anchors if u],
            }
        )
    return out


def _scene_hitl_key(scene_id: str) -> str:
    return f"{SCENE_HITL_PREFIX}{scene_id}"


def _normalize_character_positions(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for cid, pos in raw.items():
        key = str(cid).strip()
        value = str(pos or "center").strip().lower()
        if key and value in VALID_POSITIONS:
            out[key] = value
    return out


def _normalize_transition(raw: Any) -> str:
    value = str(raw or "hard_cut").strip().lower()
    return value if value in VALID_TRANSITIONS else "hard_cut"


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
        continues_from = item.get("continues_from")
        if continues_from is not None:
            continues_from = str(continues_from).strip() or None
        out.append(
            {
                "id": sid,
                "order": order,
                "character_ids": [str(c) for c in char_ids if c],
                "still_prompt": str(item.get("still_prompt") or ""),
                "motion_prompt": str(item.get("motion_prompt") or item.get("still_prompt") or ""),
                "continues_from": continues_from,
                "transition": _normalize_transition(item.get("transition")),
                "end_pose": str(item.get("end_pose") or "").strip(),
                "camera": str(item.get("camera") or "").strip(),
                "scene_id": str(item.get("scene_id") or "").strip(),
                "character_positions": _normalize_character_positions(item.get("character_positions")),
            }
        )
    out.sort(key=lambda s: s["order"])
    return out[:MAX_SHOTS]


def _validate_shots_continuity(shots: list[dict[str, Any]]) -> str | None:
    """Return error message if continuity fields are invalid."""
    ids = {s["id"] for s in shots}
    for shot in shots:
        prev_id = shot.get("continues_from")
        if prev_id and prev_id not in ids:
            return f"分镜 {shot['id']} 的 continues_from 指向不存在的镜头: {prev_id}"
    return None


def _validate_scenes(scenes: list[dict[str, Any]], shots: list[dict[str, Any]]) -> str | None:
    scene_ids = {s["id"] for s in scenes}
    for shot in shots:
        sid = shot.get("scene_id")
        if sid and scenes and sid not in scene_ids:
            return f"分镜 {shot['id']} 的 scene_id 未在 scenes[] 中定义: {sid}"
    return None


def _scenes_referenced_by_shots(shots: list[dict[str, Any]]) -> set[str]:
    return {s["scene_id"] for s in shots if s.get("scene_id")}


def _should_inject_bridge(shot: dict[str, Any], idx: int) -> bool:
    """Whether to inject previous last-frame into still references."""
    if idx <= 1:
        return False
    if "continues_from" in shot and shot["continues_from"] is None:
        return False
    if shot.get("continues_from"):
        return True
    return True


def _build_character_layout_hint(
    shot: dict[str, Any],
    characters_by_id: dict[str, dict[str, Any]],
) -> str:
    char_ids = shot.get("character_ids") or []
    if len(char_ids) <= 1:
        return ""
    positions = shot.get("character_positions") or {}
    parts: list[str] = []
    for cid in char_ids:
        char = characters_by_id.get(cid, {})
        name = char.get("name") or cid
        pos = positions.get(cid, "center")
        parts.append(f"{name}位于画面{POSITION_LABELS.get(pos, '中央')}")
    parts.append("各角色严格保持各自参考图中的脸型与服装，禁止互换身份或服装")
    return "。".join(parts)


def _build_still_prompt(
    shot: dict[str, Any],
    *,
    idx: int,
    bridged: bool,
    style_preamble: str = "",
    characters_by_id: dict[str, dict[str, Any]] | None = None,
) -> str:
    parts: list[str] = []
    if style_preamble:
        parts.append(style_preamble)
    parts.append(shot["still_prompt"])
    layout = _build_character_layout_hint(shot, characters_by_id or {})
    if layout:
        parts.append(layout)
    if bridged:
        parts.append("承接上一画面，同一角色与场景连续，禁止跳切到无关场景")
    if shot.get("scene_id"):
        parts.append(f"场景标识: {shot['scene_id']}，保持同一场景风格一致")
    if shot.get("camera"):
        parts.append(f"镜头: {shot['camera']}")
    parts.append("严格保持参考图中人物的脸型、发型与服装一致，不要更换角色身份")
    return "。".join(p for p in parts if p)


def _build_motion_prompt(shot: dict[str, Any], *, style_preamble: str = "") -> str:
    parts: list[str] = []
    if style_preamble:
        parts.append(style_preamble)
    parts.append(shot["motion_prompt"])
    if shot.get("end_pose"):
        parts.append(f"本镜结束姿态: {shot['end_pose']}")
    if shot.get("camera"):
        parts.append(f"运镜: {shot['camera']}")
    transition = shot.get("transition") or "hard_cut"
    if transition == "match_cut":
        parts.append("动作与结束姿态需便于与下一镜硬切或匹配剪辑衔接")
    elif transition == "dissolve":
        parts.append("动作平缓，便于叠化转场")
    return "。".join(p for p in parts if p)


def _boundary_transitions(shots: list[dict[str, Any]]) -> list[str]:
    """Transition type for each boundary (between shot i and i+1)."""
    if len(shots) <= 1:
        return []
    return [shots[i].get("transition") or "hard_cut" for i in range(1, len(shots))]


def _normalize_resume_shots(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("shot_id") or item.get("id") or "").strip()
        if not sid:
            continue
        out[sid] = {
            "still_url": str(item.get("still_url") or ""),
            "video_url": str(item.get("video_url") or ""),
            "last_frame_url": str(item.get("last_frame_url") or ""),
        }
    return out


def _merge_hitl_scenes(
    scenes: list[dict[str, Any]],
    params: dict[str, Any],
) -> None:
    for scene in scenes:
        if scene["anchor_urls"]:
            continue
        key = _scene_hitl_key(scene["id"])
        hitl_val = params.get(key)
        if hitl_val is None:
            continue
        if isinstance(hitl_val, list):
            scene["anchor_urls"] = [str(v) for v in hitl_val if v]
        elif hitl_val:
            scene["anchor_urls"] = [str(hitl_val)]


def _missing_anchor_scenes(
    scenes: list[dict[str, Any]],
    shots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    referenced = _scenes_referenced_by_shots(shots)
    return [
        s for s in scenes
        if not s["anchor_urls"] and s["id"] in referenced
    ]


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


def _build_combined_hitl_schema(
    missing_chars: list[dict[str, Any]],
    missing_scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for char in missing_chars:
        fields.append(
            {
                "name": char["id"],
                "label": f"{char['name']}（{char['id']}）人物锚点图",
                "type": "image_upload",
                "required": True,
                "max": 3,
                "accept": "image/*",
            }
        )
    for scene in missing_scenes:
        fields.append(
            {
                "name": _scene_hitl_key(scene["id"]),
                "label": f"{scene['name']}（{scene['id']}）场景参考图",
                "type": "image_upload",
                "required": True,
                "max": 2,
                "accept": "image/*",
            }
        )
    desc_parts: list[str] = []
    if missing_chars:
        desc_parts.append(f"人物：{'、'.join(c['name'] for c in missing_chars)}")
    if missing_scenes:
        desc_parts.append(f"场景：{'、'.join(s['name'] for s in missing_scenes)}")
    return {
        "type": "anchor_form",
        "title": "上传人物/场景锚点图",
        "fields": fields,
        "description": "请上传以下参考图：" + "；".join(desc_parts),
    }


def _build_anchor_hitl_schema(missing: list[dict[str, Any]]) -> dict[str, Any]:
    return _build_combined_hitl_schema(missing, [])


def _collect_scene_anchor_urls(
    scene_id: str,
    scenes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    scene = scenes_by_id.get(scene_id)
    if not scene:
        return []
    return list(scene.get("anchor_urls") or [])


def _collect_still_reference_urls(
    *,
    characters: list[dict[str, Any]],
    shot: dict[str, Any],
    scenes_by_id: dict[str, dict[str, Any]],
    prev_last_frame_url: str | None,
    bridged: bool,
) -> list[str]:
    urls = _collect_anchor_urls(characters, shot["character_ids"])
    scene_id = shot.get("scene_id")
    if scene_id:
        urls.extend(_collect_scene_anchor_urls(scene_id, scenes_by_id))
    if bridged and prev_last_frame_url:
        urls.append(prev_last_frame_url)
    return list(dict.fromkeys(urls))


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


def _anchors_for_agnes(anchors: list[str], *, cwd: str | None = None) -> list[str] | None:
    """Prefer public http(s) URLs; fall back to data URI for local-only assets."""
    if not anchors:
        return None
    out: list[str] = []
    for a in anchors:
        text = str(a).strip()
        if text.startswith("http://") or text.startswith("https://"):
            out.append(text)
        else:
            out.append(to_data_uri(text, cwd=cwd))
    return out


async def _generate_still_with_retry(
    *,
    prompt: str,
    anchors: list[str],
    image_size: str,
    cwd: str | None = None,
    retries: int = 1,
) -> str:
    last_err: Exception | None = None
    input_imgs = _anchors_for_agnes(anchors, cwd=cwd)
    for attempt in range(retries + 1):
        try:
            urls = await agnes_client.generate_image_urls(
                prompt=prompt,
                size=image_size,
                input_images=input_imgs,
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
                "全自动短剧流水线：基于用户上传的人物锚点图，串行生成分镜静帧（承接上一镜末帧）、"
                "图生视频，并按分镜转场策略拼接为竖屏/横屏 MV。"
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
                    "style_preamble": {
                        "type": "string",
                        "description": "全片统一视觉风格描述（色调、质感、时代感等）",
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
                    "scenes": {
                        "type": "array",
                        "description": "场景列表；有 anchor_urls 时同 scene_id 分镜强制参考",
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
                                "continues_from": {
                                    "type": "string",
                                    "description": "承接的上一镜 id；缺省则自动承接上一镜末帧",
                                },
                                "transition": {
                                    "type": "string",
                                    "enum": ["hard_cut", "match_cut", "dissolve"],
                                    "description": "与上一镜的转场方式",
                                },
                                "end_pose": {
                                    "type": "string",
                                    "description": "本镜结束姿态，供下一镜参考",
                                },
                                "camera": {
                                    "type": "string",
                                    "description": "景别/运镜描述",
                                },
                                "scene_id": {
                                    "type": "string",
                                    "description": "场景标识，同场景保持风格一致",
                                },
                                "character_positions": {
                                    "type": "object",
                                    "description": "多角色站位，如 {\"hero\": \"left\", \"villain\": \"right\"}",
                                    "additionalProperties": {
                                        "type": "string",
                                        "enum": ["left", "center", "right"],
                                    },
                                },
                            },
                            "required": ["still_prompt", "motion_prompt"],
                        },
                    },
                    "resume_shots": {
                        "type": "array",
                        "description": "上次运行的分镜中间产物，用于单镜重跑时复用未改镜头",
                        "items": {
                            "type": "object",
                            "properties": {
                                "shot_id": {"type": "string"},
                                "still_url": {"type": "string"},
                                "video_url": {"type": "string"},
                                "last_frame_url": {"type": "string"},
                            },
                            "required": ["shot_id"],
                        },
                    },
                    "rerun_shot_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "需要重新生成的分镜 id 列表；配合 resume_shots 使用",
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
                "拆镜时尽量填写 continues_from、end_pose、camera、scene_id，保证镜间连贯。",
                "同一场景应在 scenes[] 中定义 id/name/anchor_urls，并在 shots 中引用 scene_id。",
                "多角色同框时在 character_positions 标注 left/center/right，防止串脸。",
                "style_preamble 填写全片统一视觉风格（如「电影感冷色调写实」）。",
                "transition 可选 hard_cut / match_cut / dissolve；dissolve 会在拼接时使用短叠化。",
                "若用户消息已附带人物图片（http/https 图片 URL），将其填入对应 characters[].anchor_urls。",
                "若没有可用锚点 URL，将 characters[].anchor_urls 设为 []，工具会通过 HITL 让用户上传。",
                "禁止在无用户锚点的情况下用 generate_image 发明新角色脸。",
                "禁止向用户索要本地路径；只使用公网图片 URL 或 HITL 上传结果。",
                "单镜重跑：将上次 details.shots 填入 resume_shots，并在 rerun_shot_ids 列出要重跑的 shot_id。",
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
        style_preamble = str(params.get("style_preamble") or "").strip()
        preset = ASPECT_PRESETS.get(aspect, ASPECT_PRESETS["9:16"])

        characters = _normalize_characters(params.get("characters"))
        scenes = _normalize_scenes(params.get("scenes"))
        shots = _normalize_shots(params.get("shots"))
        if not characters:
            return ToolResult(content=[TextContent(text="错误：至少需要一个角色（characters）")])
        if not shots:
            return ToolResult(content=[TextContent(text="错误：至少需要一个分镜（shots）")])

        continuity_err = _validate_shots_continuity(shots)
        if continuity_err:
            return ToolResult(content=[TextContent(text=f"错误：{continuity_err}")])

        scenes_err = _validate_scenes(scenes, shots)
        if scenes_err:
            return ToolResult(content=[TextContent(text=f"错误：{scenes_err}")])

        resume_map = _normalize_resume_shots(params.get("resume_shots"))
        rerun_ids = {
            str(x).strip()
            for x in (params.get("rerun_shot_ids") or [])
            if str(x).strip()
        }

        _merge_hitl_anchors(characters, params)
        _merge_hitl_scenes(scenes, params)
        missing_chars = _missing_anchor_characters(characters)
        missing_scenes = _missing_anchor_scenes(scenes, shots)
        if missing_chars or missing_scenes:
            names: list[str] = []
            if missing_chars:
                names.append("、".join(c["name"] for c in missing_chars))
            if missing_scenes:
                names.append("、".join(s["name"] for s in missing_scenes))
            raise RequiresHumanInput(
                prompt=f"请上传锚点参考图：{' / '.join(names)}",
                input_schema=_build_combined_hitl_schema(missing_chars, missing_scenes),
            )

        cwd = (ctx.metadata.get("cwd") if ctx else None) or os.getcwd()
        public_base = (ctx.metadata.get("public_base_url") if ctx else None) or default_public_base_url()

        characters_by_id = {c["id"]: c for c in characters}
        scenes_by_id = {s["id"]: s for s in scenes}

        for char in characters:
            char["anchor_urls"] = resolve_media_list(
                char["anchor_urls"], cwd=cwd, public_base_url=public_base
            )
        for scene in scenes:
            scene["anchor_urls"] = resolve_media_list(
                scene["anchor_urls"], cwd=cwd, public_base_url=public_base
            )

        reporter = _PlanReporter(self._plan_store, ctx, title)
        await reporter.init_steps(len(shots))

        video_urls: list[str] = []
        shot_summaries: list[dict[str, Any]] = []
        prev_last_frame_url: str | None = None

        try:
            for idx, shot in enumerate(shots, start=1):
                sid = shot["id"]
                cached = resume_map.get(sid)
                reuse = cached and sid not in rerun_ids and cached.get("video_url")

                summary: dict[str, Any] = {"shot_id": sid, "shot_index": idx}

                if reuse:
                    still_url = cached["still_url"]
                    video_url = cached["video_url"]
                    last_frame_url = cached.get("last_frame_url") or ""
                    await reporter.complete(f"still_{idx}", detail=f"复用 {sid}")
                    await reporter.complete(f"video_{idx}", detail=f"复用 {sid}")
                    summary.update(
                        {
                            "still_url": still_url,
                            "video_url": video_url,
                            "last_frame_url": last_frame_url,
                            "reused": True,
                        }
                    )
                    video_urls.append(video_url)
                    prev_last_frame_url = last_frame_url or prev_last_frame_url
                    shot_summaries.append(summary)
                    continue

                bridged = _should_inject_bridge(shot, idx) and bool(prev_last_frame_url)
                still_step = f"still_{idx}"
                await reporter.start(still_step, detail=sid)
                anchors = _collect_still_reference_urls(
                    characters=characters,
                    shot=shot,
                    scenes_by_id=scenes_by_id,
                    prev_last_frame_url=prev_last_frame_url,
                    bridged=bridged,
                )
                still_prompt = _build_still_prompt(
                    shot,
                    idx=idx,
                    bridged=bridged,
                    style_preamble=style_preamble,
                    characters_by_id=characters_by_id,
                )
                try:
                    still_url = await _generate_still_with_retry(
                        prompt=still_prompt,
                        anchors=anchors,
                        image_size=preset["image_size"],
                        cwd=cwd,
                    )
                except Exception as exc:
                    await reporter.fail(still_step, detail=str(exc))
                    raise
                await reporter.complete(still_step, detail=still_url[:120])
                summary["still_url"] = still_url
                summary["bridged"] = bridged
                if shot.get("scene_id"):
                    summary["scene_id"] = shot["scene_id"]

                video_step = f"video_{idx}"
                await reporter.start(video_step, detail=sid)
                motion_prompt = _build_motion_prompt(shot, style_preamble=style_preamble)
                try:
                    video_url = await _generate_video_with_retry(
                        prompt=motion_prompt,
                        image=still_url,
                        width=preset["width"],
                        height=preset["height"],
                    )
                except Exception as exc:
                    await reporter.fail(video_step, detail=str(exc))
                    raise
                video_urls.append(video_url)
                summary["video_url"] = video_url
                await reporter.complete(video_step, detail=video_url[:120])

                try:
                    _, last_frame_url = await extract_last_frame_url(
                        video_url,
                        cwd=cwd,
                        public_base_url=public_base,
                    )
                except Exception as exc:
                    logger.warning("last frame extract failed for %s: %s", sid, exc)
                    last_frame_url = still_url
                summary["last_frame_url"] = last_frame_url
                prev_last_frame_url = last_frame_url
                shot_summaries.append(summary)

            boundaries = _boundary_transitions(shots)
            use_crossfade = any(t in ("dissolve", "match_cut") for t in boundaries)

            await reporter.start("concat")
            _, final_url = await concat_videos(
                video_urls,
                name=title,
                cwd=cwd,
                public_base_url=public_base,
                transition="crossfade" if use_crossfade else "none",
                crossfade_seconds=DEFAULT_CROSSFADE_SECONDS,
                boundary_transitions=boundaries,
                mute_output=True,
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
                    "bridge_scheme": BRIDGE_SCHEME,
                },
                display={"type": "plan_error", "error": str(exc)},
            )

        text = (
            f"短剧《{title}》已生成！\n"
            f"**视频URL**: {final_url}\n"
            f"**镜头数**: {len(shots)} | **画幅**: {aspect} | **桥接**: 方案{BRIDGE_SCHEME}"
        )
        return ToolResult(
            content=[TextContent(text=text)],
            details={
                "video_url": final_url,
                "title": title,
                "aspect_ratio": aspect,
                "style_preamble": style_preamble or None,
                "scenes": [{"id": s["id"], "name": s["name"]} for s in scenes],
                "shots": shot_summaries,
                "bridge_scheme": BRIDGE_SCHEME,
            },
            display={"video": {"url": final_url}},
        )


def create_short_drama_tool(*, plan_store: PlanStore | None = None) -> ShortDramaPipelineTool:
    return ShortDramaPipelineTool(plan_store=plan_store)
