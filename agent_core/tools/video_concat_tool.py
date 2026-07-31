"""FFmpeg-based video concatenation tool."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.media_utils import (
    default_public_base_url,
    local_path_to_public_url,
    renders_dir,
    resolve_media_url,
)

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 120.0


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def _download_video(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def _resolve_local_video(path_or_url: str, *, cwd: str, public_base_url: str) -> Path:
    del public_base_url
    text = path_or_url.strip()
    if text.startswith("http://") or text.startswith("https://"):
        raise ValueError("HTTP URL must be downloaded first")

    candidates: list[Path] = []
    if text.startswith("/uploads/"):
        candidates.append(Path(cwd) / ".pi" / "uploads" / Path(text).name)
    elif text.startswith("/renders/"):
        candidates.append(Path(cwd) / ".pi" / "renders" / Path(text).name)
    elif text.startswith(".pi/uploads/") or text.startswith(".pi/renders/"):
        candidates.append(Path(cwd) / text)
    else:
        candidates.extend([Path(text), Path(cwd) / text])

    parsed = urlparse(text)
    if parsed.path.startswith("/uploads/") or parsed.path.startswith("/renders/"):
        bucket = "uploads" if parsed.path.startswith("/uploads/") else "renders"
        candidates.append(Path(cwd) / ".pi" / bucket / Path(parsed.path).name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(f"Video file not found: {path_or_url}")


async def prepare_video_paths(
    sources: list[str],
    *,
    cwd: str,
    public_base_url: str,
) -> list[Path]:
    paths: list[Path] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="short-drama-clips-"))
    try:
        for idx, src in enumerate(sources):
            text = str(src).strip()
            if text.startswith("http://") or text.startswith("https://"):
                dest = tmp_dir / f"clip_{idx:02d}.mp4"
                await _download_video(text, dest)
                paths.append(dest)
                continue
            resolved = resolve_media_url(text, cwd=cwd, public_base_url=public_base_url)
            if resolved.startswith("http://") or resolved.startswith("https://"):
                dest = tmp_dir / f"clip_{idx:02d}.mp4"
                await _download_video(resolved, dest)
                paths.append(dest)
            else:
                paths.append(_resolve_local_video(resolved, cwd=cwd, public_base_url=public_base_url))
        return paths
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def concat_video_files(
    input_paths: list[Path],
    *,
    output_path: Path | None = None,
    cwd: str | None = None,
) -> Path:
    if not input_paths:
        raise ValueError("No video clips to concat")
    if not ffmpeg_available():
        raise RuntimeError("未找到 ffmpeg，请先安装并加入 PATH")

    out_dir = renders_dir(cwd)
    dest = output_path or (out_dir / f"mv_{uuid.uuid4().hex[:12]}.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)

    list_file = dest.with_suffix(".txt")
    lines = []
    for path in input_paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(dest),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            # Re-encode fallback when stream copy fails
            cmd_reencode = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(dest),
            ]
            proc = subprocess.run(
                cmd_reencode,
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr[-1000:] or "ffmpeg concat failed")
    finally:
        list_file.unlink(missing_ok=True)

    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced empty output")
    return dest


async def concat_videos(
    video_sources: list[str],
    *,
    name: str = "short-drama",
    cwd: str | None = None,
    public_base_url: str | None = None,
) -> tuple[Path, str]:
    root = cwd or os.getcwd()
    base = public_base_url or default_public_base_url()
    paths = await prepare_video_paths(video_sources, cwd=root, public_base_url=base)
    tmp_parent = paths[0].parent if paths and str(paths[0]).find("short-drama-clips-") >= 0 else None
    try:
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:48]
        out = concat_video_files(
            paths,
            output_path=renders_dir(root) / f"{safe_name}_{uuid.uuid4().hex[:8]}.mp4",
            cwd=root,
        )
        url = local_path_to_public_url(out, public_base_url=base)
        return out, url
    finally:
        if tmp_parent and tmp_parent.name.startswith("short-drama-clips-"):
            shutil.rmtree(tmp_parent, ignore_errors=True)


class ConcatVideosTool(Tool):
    """Concatenate multiple video clips into one MP4."""

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="concat_videos",
            description="将多个视频片段按顺序拼接为一条 MP4 成片，返回可下载 URL。",
            parameters={
                "type": "object",
                "properties": {
                    "video_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "有序视频 URL 或本地路径列表",
                    },
                    "name": {
                        "type": "string",
                        "description": "输出文件名前缀",
                    },
                },
                "required": ["video_urls"],
            },
            prompt_snippet="concat_videos $ARGUMENTS — 拼接多段视频为一条成片",
            timeout_seconds=600,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        del tool_call_id
        urls = params.get("video_urls") or []
        name = str(params.get("name") or "short-drama")
        if not isinstance(urls, list) or not urls:
            return ToolResult(content=[TextContent(text="错误：video_urls 不能为空")])

        cwd = (ctx.metadata.get("cwd") if ctx else None) or os.getcwd()
        public_base = (ctx.metadata.get("public_base_url") if ctx else None) or default_public_base_url()

        try:
            out_path, public_url = await concat_videos(
                [str(u) for u in urls],
                name=name,
                cwd=cwd,
                public_base_url=public_base,
            )
        except Exception as exc:
            logger.warning("concat_videos failed: %s", exc)
            return ToolResult(content=[TextContent(text=f"视频拼接失败: {exc}")])

        size_mb = out_path.stat().st_size / (1024 * 1024)
        text = (
            f"短剧成片已生成！\n"
            f"**视频URL**: {public_url}\n"
            f"**文件大小**: {size_mb:.2f} MB"
        )
        return ToolResult(
            content=[TextContent(text=text)],
            details={
                "video_url": public_url,
                "path": str(out_path),
                "clip_count": len(urls),
            },
            display={"video": {"url": public_url}},
        )


concat_videos_tool = ConcatVideosTool()
