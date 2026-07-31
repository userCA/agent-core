"""Extract frames from video files for short-drama continuity."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx

from agent_core.tools.media_utils import local_path_to_public_url, uploads_dir
from agent_core.tools.remote_upload import upload_bytes_to_remote

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 120.0


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_duration_seconds(path: Path) -> float:
    """Return media duration in seconds."""
    if not shutil.which("ffprobe"):
        raise RuntimeError("未找到 ffprobe")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:] or "ffprobe failed")
    return max(float(proc.stdout.strip()), 0.1)


def extract_last_frame_file(video_path: Path, *, output_path: Path | None = None) -> Path:
    """Extract the last frame from a local video file using ffmpeg."""
    if not ffmpeg_available():
        raise RuntimeError("未找到 ffmpeg")
    if not video_path.is_file():
        raise FileNotFoundError(str(video_path))

    dest = output_path or (video_path.parent / f"lastframe_{uuid.uuid4().hex[:8]}.jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.2",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(proc.stderr[-800:] or "ffmpeg last-frame extract failed")
    return dest


async def _download_video(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


async def extract_last_frame_url(
    video_source: str,
    *,
    cwd: str | None = None,
    public_base_url: str | None = None,
    upload_remote: bool = True,
) -> tuple[Path, str]:
    """Extract last frame from video URL/path; return local path and public URL.

    When *upload_remote* is True (default), uploads JPEG to Migu CDN so Agnes
    can fetch it. Otherwise returns local public URL via ``public_base_url``.
    """
    text = str(video_source).strip()
    tmp_dir: Path | None = None
    local_video: Path

    if text.startswith("http://") or text.startswith("https://"):
        tmp_dir = Path(tempfile.mkdtemp(prefix="short-drama-frame-"))
        local_video = tmp_dir / "clip.mp4"
        await _download_video(text, local_video)
    else:
        local_video = Path(text)
        if not local_video.is_file() and cwd:
            local_video = Path(cwd) / text
        if not local_video.is_file():
            raise FileNotFoundError(f"Video not found: {video_source}")

    try:
        out_dir = uploads_dir(cwd)
        frame_path = extract_last_frame_file(
            local_video,
            output_path=out_dir / f"lastframe_{uuid.uuid4().hex[:8]}.jpg",
        )
        raw = frame_path.read_bytes()
        if upload_remote:
            public_url = await upload_bytes_to_remote(
                data=raw,
                filename=frame_path.name,
                content_type="image/jpeg",
            )
        else:
            base = (public_base_url or "http://127.0.0.1:8001").rstrip("/")
            public_url = local_path_to_public_url(frame_path, public_base_url=base)
        return frame_path, public_url
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
