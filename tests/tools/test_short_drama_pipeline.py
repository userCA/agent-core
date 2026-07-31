"""Tests for short drama pipeline tool."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from agent_core.core.human_input import RequiresHumanInput
from agent_core.planning.store import PlanStore
from agent_core.tools.base import ToolContext, ToolResult
from agent_core.tools.short_drama_pipeline import (
    MAX_SHOTS,
    ShortDramaPipelineTool,
    _build_character_layout_hint,
    _build_still_prompt,
    _collect_still_reference_urls,
    _missing_anchor_scenes,
    _normalize_scenes,
    _normalize_shots,
    _scene_hitl_key,
    _should_inject_bridge,
    _validate_scenes,
    _validate_shots_continuity,
    create_short_drama_tool,
)


def test_normalize_shots_truncates_to_max() -> None:
    raw = [
        {"id": f"s{i}", "order": i, "still_prompt": "p", "motion_prompt": "m"}
        for i in range(1, 20)
    ]
    shots = _normalize_shots(raw)
    assert len(shots) == MAX_SHOTS


def test_normalize_shots_continuity_fields() -> None:
    raw = [
        {
            "id": "s1",
            "order": 1,
            "still_prompt": "a",
            "motion_prompt": "m1",
        },
        {
            "id": "s2",
            "order": 2,
            "still_prompt": "b",
            "motion_prompt": "m2",
            "continues_from": "s1",
            "transition": "dissolve",
            "end_pose": "转身",
            "camera": "medium shot",
            "scene_id": "street",
        },
    ]
    shots = _normalize_shots(raw)
    assert shots[1]["continues_from"] == "s1"
    assert shots[1]["transition"] == "dissolve"
    assert shots[1]["end_pose"] == "转身"
    assert shots[1]["scene_id"] == "street"


def test_validate_shots_continuity_invalid_ref() -> None:
    shots = _normalize_shots(
        [{"id": "s2", "order": 1, "still_prompt": "x", "motion_prompt": "y", "continues_from": "missing"}]
    )
    assert _validate_shots_continuity(shots) is not None


def test_should_inject_bridge() -> None:
    shot = {"id": "s2", "continues_from": "s1"}
    assert _should_inject_bridge(shot, 1) is False
    assert _should_inject_bridge(shot, 2) is True


def test_build_still_prompt_bridged() -> None:
    shot = {"still_prompt": "雨夜", "scene_id": "bus", "camera": "wide"}
    text = _build_still_prompt(
        shot,
        idx=2,
        bridged=True,
        style_preamble="电影感冷色调",
    )
    assert "承接上一画面" in text
    assert "电影感冷色调" in text
    assert "bus" in text


def test_character_layout_hint() -> None:
    shot = {
        "character_ids": ["hero", "villain"],
        "character_positions": {"hero": "left", "villain": "right"},
    }
    chars = {
        "hero": {"id": "hero", "name": "女主"},
        "villain": {"id": "villain", "name": "男主"},
    }
    text = _build_character_layout_hint(shot, chars)
    assert "左侧" in text
    assert "右侧" in text
    assert "禁止互换" in text


def test_normalize_scenes_and_hitl_key() -> None:
    scenes = _normalize_scenes([{"id": "street", "name": "街道", "anchor_urls": []}])
    assert scenes[0]["id"] == "street"
    assert _scene_hitl_key("street") == "scene_street"


def test_missing_anchor_scenes_only_when_referenced() -> None:
    scenes = _normalize_scenes([{"id": "street", "name": "街道", "anchor_urls": []}])
    shots = _normalize_shots(
        [{"id": "s1", "order": 1, "still_prompt": "a", "motion_prompt": "m", "scene_id": "street"}]
    )
    missing = _missing_anchor_scenes(scenes, shots)
    assert len(missing) == 1
    shots_no_scene = _normalize_shots([{"id": "s1", "order": 1, "still_prompt": "a", "motion_prompt": "m"}])
    assert _missing_anchor_scenes(scenes, shots_no_scene) == []


def test_validate_scenes_unknown_id() -> None:
    scenes = _normalize_scenes([{"id": "a", "name": "A", "anchor_urls": ["http://x"]}])
    shots = _normalize_shots(
        [{"id": "s1", "order": 1, "still_prompt": "x", "motion_prompt": "y", "scene_id": "missing"}]
    )
    assert _validate_scenes(scenes, shots) is not None


def test_collect_still_reference_urls_includes_scene() -> None:
    chars = [{"id": "hero", "name": "H", "anchor_urls": ["http://face.jpg"]}]
    scenes = {"street": {"id": "street", "anchor_urls": ["http://scene.jpg"]}}
    shot = {"character_ids": ["hero"], "scene_id": "street"}
    urls = _collect_still_reference_urls(
        characters=chars,
        shot=shot,
        scenes_by_id=scenes,
        prev_last_frame_url="http://last.jpg",
        bridged=True,
    )
    assert urls == ["http://face.jpg", "http://scene.jpg", "http://last.jpg"]


@pytest.mark.asyncio
async def test_hitl_when_scene_anchors_missing() -> None:
    tool = create_short_drama_tool(plan_store=PlanStore())
    ctx = ToolContext(signal=asyncio.Event())
    params = {
        "title": "测试",
        "characters": [{"id": "hero", "name": "主角", "anchor_urls": ["http://img/a.jpg"]}],
        "scenes": [{"id": "street", "name": "街道", "anchor_urls": []}],
        "shots": [
            {
                "id": "s1",
                "order": 1,
                "character_ids": ["hero"],
                "still_prompt": "雨夜",
                "motion_prompt": "走",
                "scene_id": "street",
            }
        ],
    }
    with patch("agent_core.tools.short_drama_pipeline.agnes_client.api_key_configured", return_value=True):
        with pytest.raises(RequiresHumanInput) as exc:
            await tool.execute("tc1", params, ctx)
    assert any(f["name"] == "scene_street" for f in exc.value.input_schema["fields"])


@pytest.mark.asyncio
async def test_hitl_when_anchors_missing() -> None:
    tool = create_short_drama_tool(plan_store=PlanStore())
    ctx = ToolContext(signal=asyncio.Event())
    params = {
        "title": "测试短剧",
        "characters": [{"id": "hero", "name": "主角", "anchor_urls": []}],
        "shots": [
            {
                "id": "s1",
                "order": 1,
                "character_ids": ["hero"],
                "still_prompt": "雨夜",
                "motion_prompt": "向前走",
            }
        ],
    }
    with patch("agent_core.tools.short_drama_pipeline.agnes_client.api_key_configured", return_value=True):
        with pytest.raises(RequiresHumanInput) as exc:
            await tool.execute("tc1", params, ctx)
    schema = exc.value.input_schema
    assert schema["type"] == "anchor_form"
    assert any(f["name"] == "hero" for f in schema["fields"])


@pytest.mark.asyncio
async def test_pipeline_success_mocked(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = PlanStore()
    tool = ShortDramaPipelineTool(plan_store=store)
    updates: list[ToolResult] = []

    def on_update(result: ToolResult) -> None:
        updates.append(result)

    ctx = ToolContext(
        signal=asyncio.Event(),
        on_update=on_update,
        metadata={"cwd": str(tmp_path), "public_base_url": "http://test.local"},
    )

    params = {
        "title": "雨夜",
        "aspect_ratio": "9:16",
        "characters": [{"id": "hero", "name": "女孩", "anchor_urls": ["http://img/anchor.jpg"]}],
        "shots": [
            {
                "id": "s1",
                "order": 1,
                "character_ids": ["hero"],
                "still_prompt": "雨夜站台",
                "motion_prompt": "缓推",
            },
            {
                "id": "s2",
                "order": 2,
                "character_ids": ["hero"],
                "still_prompt": "上车",
                "motion_prompt": "微笑",
                "continues_from": "s1",
            },
        ],
    }

    still_counter = {"n": 0, "anchors": []}
    video_counter = {"n": 0}

    async def fake_still(**kwargs: Any) -> list[str]:
        still_counter["n"] += 1
        still_counter["anchors"].append(kwargs.get("input_images"))
        return [f"http://img/still{still_counter['n']}.jpg"]

    async def fake_video(**kwargs: Any) -> dict[str, Any]:
        video_counter["n"] += 1
        return {"video_url": f"http://vid/clip{video_counter['n']}.mp4"}

    async def fake_last_frame(video_source: str, **kwargs: Any) -> tuple[Any, str]:
        return tmp_path / "frame.jpg", f"http://img/last_{video_source.split('/')[-1]}.jpg"

    async def fake_concat(sources: list[str], **kwargs: Any) -> tuple[Any, str]:
        assert kwargs.get("mute_output") is True
        return tmp_path / "final.mp4", "http://test.local/renders/final.mp4"

    with patch("agent_core.tools.short_drama_pipeline.agnes_client.api_key_configured", return_value=True):
        with patch("agent_core.tools.short_drama_pipeline.agnes_client.generate_image_urls", fake_still):
            with patch(
                "agent_core.tools.short_drama_pipeline.agnes_client.generate_video_from_image",
                fake_video,
            ):
                with patch(
                    "agent_core.tools.short_drama_pipeline.extract_last_frame_url",
                    fake_last_frame,
                ):
                    with patch("agent_core.tools.short_drama_pipeline.concat_videos", fake_concat):
                        result = await tool.execute("tc1", params, ctx)

    text = result.content[0].text  # type: ignore[union-attr]
    assert "短剧" in text
    assert result.details["video_url"] == "http://test.local/renders/final.mp4"
    assert still_counter["n"] == 2
    assert video_counter["n"] == 2
    assert store.plan is not None
    assert store.plan.status == "completed"
    assert any(u.details and u.details.get("plan") for u in updates)
    assert len(result.details["shots"]) == 2
    assert result.details["shots"][1].get("bridged") is True


@pytest.mark.asyncio
async def test_pipeline_rerun_reuses_cached_shot(tmp_path: Any) -> None:
    tool = ShortDramaPipelineTool(plan_store=PlanStore())
    ctx = ToolContext(
        signal=asyncio.Event(),
        metadata={"cwd": str(tmp_path), "public_base_url": "http://test.local"},
    )
    params = {
        "title": "重跑",
        "characters": [{"id": "hero", "name": "女孩", "anchor_urls": ["http://img/anchor.jpg"]}],
        "shots": [
            {
                "id": "s1",
                "order": 1,
                "character_ids": ["hero"],
                "still_prompt": "a",
                "motion_prompt": "m1",
            },
            {
                "id": "s2",
                "order": 2,
                "character_ids": ["hero"],
                "still_prompt": "b",
                "motion_prompt": "m2",
            },
        ],
        "resume_shots": [
            {
                "shot_id": "s1",
                "still_url": "http://img/still1.jpg",
                "video_url": "http://vid/clip1.mp4",
                "last_frame_url": "http://img/last1.jpg",
            }
        ],
        "rerun_shot_ids": ["s2"],
    }

    still_counter = {"n": 0}
    video_counter = {"n": 0}

    async def fake_still(**kwargs: Any) -> list[str]:
        still_counter["n"] += 1
        return ["http://img/still2.jpg"]

    async def fake_video(**kwargs: Any) -> dict[str, Any]:
        video_counter["n"] += 1
        return {"video_url": "http://vid/clip2.mp4"}

    async def fake_last_frame(video_source: str, **kwargs: Any) -> tuple[Any, str]:
        return tmp_path / "frame.jpg", "http://img/last2.jpg"

    async def fake_concat(sources: list[str], **kwargs: Any) -> tuple[Any, str]:
        assert sources == ["http://vid/clip1.mp4", "http://vid/clip2.mp4"]
        return tmp_path / "final.mp4", "http://test.local/renders/final.mp4"

    with patch("agent_core.tools.short_drama_pipeline.agnes_client.api_key_configured", return_value=True):
        with patch("agent_core.tools.short_drama_pipeline.agnes_client.generate_image_urls", fake_still):
            with patch(
                "agent_core.tools.short_drama_pipeline.agnes_client.generate_video_from_image",
                fake_video,
            ):
                with patch(
                    "agent_core.tools.short_drama_pipeline.extract_last_frame_url",
                    fake_last_frame,
                ):
                    with patch("agent_core.tools.short_drama_pipeline.concat_videos", fake_concat):
                        result = await tool.execute("tc1", params, ctx)

    assert still_counter["n"] == 1
    assert video_counter["n"] == 1
    assert result.details["shots"][0]["reused"] is True
