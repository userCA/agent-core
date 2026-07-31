"""Upload local files to Migu remote storage and return a public URL."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, BinaryIO

import httpx

logger = logging.getLogger(__name__)

DEFAULT_UPLOAD_URL = "http://upload.musicapp.nf.migu.cn/file/upload/v1.1"
DEFAULT_SERVICE_TYPE = "100"
UPLOAD_TIMEOUT = 100.0


def remote_upload_url() -> str:
    return os.environ.get("MIGU_UPLOAD_URL", DEFAULT_UPLOAD_URL).rstrip("/")


def remote_upload_service_type() -> str:
    return os.environ.get("MIGU_UPLOAD_SERVICE_TYPE", DEFAULT_SERVICE_TYPE)


async def upload_bytes_to_remote(
    *,
    data: bytes,
    filename: str,
    content_type: str | None = None,
) -> str:
    """Upload raw bytes to Migu file service; return the public URL."""
    if not data:
        raise ValueError("empty file data")

    url = remote_upload_url()
    headers = {"sid": str(uuid.uuid4())}
    form_data = {"serviceType": remote_upload_service_type()}
    mime = content_type or "application/octet-stream"
    files = {"files": (filename, data, mime)}

    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, data=form_data, files=files)
        resp.raise_for_status()
        payload = resp.json()

    return _extract_url(payload, filename=filename)


async def upload_file_to_remote(
    path: str | Path,
    *,
    content_type: str | None = None,
) -> str:
    path = Path(path)
    return await upload_bytes_to_remote(
        data=path.read_bytes(),
        filename=path.name,
        content_type=content_type,
    )


async def upload_fileobj_to_remote(
    file_obj: BinaryIO,
    *,
    filename: str,
    content_type: str | None = None,
) -> str:
    data = file_obj.read()
    return await upload_bytes_to_remote(
        data=data,
        filename=filename,
        content_type=content_type,
    )


def _extract_url(payload: dict[str, Any], *, filename: str) -> str:
    code = str(payload.get("code", ""))
    data = payload.get("data") or []
    if code != "000000" or not isinstance(data, list) or not data:
        message = payload.get("message") or payload.get("info") or "upload failed"
        logger.warning("remote upload failed for %s: code=%s msg=%s", filename, code, message)
        raise RuntimeError(f"远端上传失败: code={code}, message={message}")

    first = data[0] if isinstance(data[0], dict) else {}
    url = first.get("url") or first.get("fileUrl") or first.get("downloadUrl")
    if not url:
        raise RuntimeError(f"远端上传成功但未返回 URL: {payload}")
    return str(url)
