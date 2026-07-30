"""Internal Agnes API helpers for pipeline orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_AGNES_BASE_URL = os.environ.get("AGNES_BASE_URL", "https://api.agnes-ai.cn/v1")
_IMAGE_API = f"{_AGNES_BASE_URL.rstrip('/')}/images/generations"
_VIDEO_API = f"{_AGNES_BASE_URL.rstrip('/')}/videos"
_API_KEY = os.environ.get("AGNES_API_KEY", "")

IMAGE_TIMEOUT = 120
VIDEO_REQUEST_TIMEOUT = 30
VIDEO_POLL_INTERVAL = 10.0
VIDEO_MAX_POLL_SECONDS = 600

VALID_FRAMES = {
    81, 121, 161, 201, 241, 281, 321, 361, 401, 441,
}


def api_key_configured() -> bool:
    return bool(_API_KEY)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }


def normalize_num_frames(num_frames: int) -> int:
    if num_frames > 441:
        return 121
    if num_frames in VALID_FRAMES:
        return num_frames
    for frame in sorted(VALID_FRAMES):
        if frame >= num_frames:
            return frame
    return 121


async def generate_image_urls(
    *,
    prompt: str,
    size: str = "768x1024",
    input_images: list[str] | None = None,
) -> list[str]:
    if not _API_KEY:
        raise RuntimeError("未设置 AGNES_API_KEY 环境变量")

    body: dict[str, Any] = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "size": size,
    }
    if input_images:
        body["tags"] = ["img2img"]
        body["extra_body"] = {
            "image": input_images,
            "response_format": "url",
        }

    async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT) as client:
        resp = await client.post(_IMAGE_API, json=body, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    results = data.get("data", [])
    urls = [item.get("url", "") for item in results if item.get("url")]
    if not urls:
        raise RuntimeError(f"未生成图片: {json.dumps(data, ensure_ascii=False)}")
    return urls


async def submit_video_task(
    *,
    prompt: str,
    image: str | None = None,
    width: int = 768,
    height: int = 1152,
    num_frames: int = 121,
    frame_rate: int = 24,
) -> str:
    if not _API_KEY:
        raise RuntimeError("未设置 AGNES_API_KEY 环境变量")

    body: dict[str, Any] = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_frames": normalize_num_frames(num_frames),
        "frame_rate": frame_rate,
    }
    if image:
        body["image"] = image

    async with httpx.AsyncClient(timeout=VIDEO_REQUEST_TIMEOUT) as client:
        resp = await client.post(_VIDEO_API, json=body, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    task_id = data.get("id", "")
    if not task_id:
        raise RuntimeError(f"创建视频任务失败: {json.dumps(data, ensure_ascii=False)}")
    return task_id


async def poll_video_task(
    task_id: str,
    *,
    max_seconds: float = VIDEO_MAX_POLL_SECONDS,
    interval: float = VIDEO_POLL_INTERVAL,
) -> dict[str, Any]:
    """Poll until completed/failed/timeout. Returns poll payload or raises."""
    started = asyncio.get_event_loop().time()
    last_status = "queued"
    async with httpx.AsyncClient(timeout=VIDEO_REQUEST_TIMEOUT) as client:
        while True:
            elapsed = asyncio.get_event_loop().time() - started
            if elapsed > max_seconds:
                raise TimeoutError(
                    f"视频任务超时 ({max_seconds:.0f}s): task_id={task_id}, status={last_status}"
                )

            resp = await client.get(f"{_VIDEO_API}/{task_id}", headers=_headers())
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            last_status = status

            if status == "completed":
                video_url = data.get("remixed_from_video_id", "") or data.get("video_url", "")
                if not video_url:
                    raise RuntimeError(
                        f"视频完成但未返回 URL: {json.dumps(data, ensure_ascii=False)}"
                    )
                return {
                    "video_url": video_url,
                    "task_id": task_id,
                    "size": data.get("size"),
                    "seconds": data.get("seconds"),
                }
            if status == "failed":
                raise RuntimeError(
                    f"视频生成失败: task_id={task_id}, error={data.get('error', '')}"
                )

            await asyncio.sleep(interval)


async def generate_video_from_image(
    *,
    prompt: str,
    image: str,
    width: int = 768,
    height: int = 1152,
    num_frames: int = 121,
    frame_rate: int = 24,
    max_poll_seconds: float = VIDEO_MAX_POLL_SECONDS,
) -> dict[str, Any]:
    task_id = await submit_video_task(
        prompt=prompt,
        image=image,
        width=width,
        height=height,
        num_frames=num_frames,
        frame_rate=frame_rate,
    )
    result = await poll_video_task(task_id, max_seconds=max_poll_seconds)
    return result
