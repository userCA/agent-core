"""Tests for short drama pipeline tool."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_core.core.human_input import RequiresHumanInput
from agent_core.planning.store import PlanStore
from agent_core.tools.base import ToolContext, ToolResult
from agent_core.tools.short_drama_pipeline import (
    MAX_SHOTS,
    ShortDramaPipelineTool,
    _normalize_shots,
    create_short_drama_tool,
)


def test_normalize_shots_truncates_to_max() -> None:
    raw = [
        {"id": f"s{i}", "order": i, "still_prompt": "p", "motion_prompt": "m"}
        for i in range(1, 20)
    ]
    shots = _normalize_shots(raw)
    assert len(shots) == MAX_SHOTS


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
            },
        ],
    }

    still_counter = {"n": 0}
    video_counter = {"n": 0}

    async def fake_still(**kwargs: Any) -> list[str]:
        still_counter["n"] += 1
        return [f"http://img/still{still_counter['n']}.jpg"]

    async def fake_video(**kwargs: Any) -> dict[str, Any]:
        video_counter["n"] += 1
        return {"video_url": f"http://vid/clip{video_counter['n']}.mp4"}

    async def fake_concat(sources: list[str], **kwargs: Any) -> tuple[Any, str]:
        return tmp_path / "final.mp4", "http://test.local/renders/final.mp4"

    with patch("agent_core.tools.short_drama_pipeline.agnes_client.api_key_configured", return_value=True):
        with patch("agent_core.tools.short_drama_pipeline.agnes_client.generate_image_urls", fake_still):
            with patch(
                "agent_core.tools.short_drama_pipeline.agnes_client.generate_video_from_image",
                fake_video,
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
