"""Tests for video concat tool."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from agent_core.tools.base import ToolContext
from agent_core.tools.video_concat_tool import (
    concat_video_files,
    concat_videos_tool,
    ffmpeg_available,
)


def _make_tiny_mp4(path: Path, *, color: str = "red", seconds: int = 1) -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=320x240:d={seconds}",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_concat_video_files(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_tiny_mp4(a, color="red")
    _make_tiny_mp4(b, color="blue")
    out = concat_video_files([a, b], output_path=tmp_path / "out.mp4", cwd=str(tmp_path))
    assert out.is_file()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_concat_video_files_mute(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_tiny_mp4(a, color="red")
    _make_tiny_mp4(b, color="blue")
    out = concat_video_files([a, b], output_path=tmp_path / "out.mp4", cwd=str(tmp_path), mute_output=True)
    assert out.is_file()
    assert out.stat().st_size > 0


@pytest.mark.asyncio
async def test_concat_videos_tool_local_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")

    renders = tmp_path / ".pi" / "renders"
    renders.mkdir(parents=True)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _make_tiny_mp4(a)
    _make_tiny_mp4(b)

    monkeypatch.setenv("PUBLIC_BASE_URL", "http://test.local")

    ctx = ToolContext(signal=asyncio.Event(), metadata={"cwd": str(tmp_path), "public_base_url": "http://test.local"})
    result = await concat_videos_tool.execute(
        "tc1",
        {"video_urls": [str(a), str(b)], "name": "demo"},
        ctx,
    )
    text = result.content[0].text  # type: ignore[union-attr]
    assert "视频URL" in text
    assert result.details and result.details.get("video_url")
