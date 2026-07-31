"""Tests for video frame extraction."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_core.tools.video_frame import (
    extract_last_frame_file,
    ffmpeg_available,
    ffprobe_duration_seconds,
)


def _make_tiny_mp4(path: Path, *, seconds: int = 1) -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=red:s=320x240:d={seconds}",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_extract_last_frame_file(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    _make_tiny_mp4(video)
    out = extract_last_frame_file(video, output_path=tmp_path / "last.jpg")
    assert out.is_file()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_ffprobe_duration_seconds(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    _make_tiny_mp4(video, seconds=2)
    duration = ffprobe_duration_seconds(video)
    assert duration >= 1.5
