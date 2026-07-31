"""Shared upload handler: local save + remote Migu URL."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from agent_core.tools.remote_upload import upload_bytes_to_remote

logger = logging.getLogger(__name__)


async def save_and_remote_upload(
    *,
    raw: bytes,
    filename: str | None,
    cwd: str,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Persist file under .pi/uploads and upload to remote storage.

    Returns dict with success/filename/path/size/url. Raises on remote failure
    after local save (local path still returned in exception context via log).
    """
    uploads_dir = os.path.join(cwd, ".pi", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    original = filename or "upload.bin"
    ext = ""
    if "." in original:
        ext = "." + original.rsplit(".", 1)[-1].lower()
    saved_name = f"{uuid.uuid4().hex[:12]}{ext}"
    saved_path = os.path.join(uploads_dir, saved_name)

    with open(saved_path, "wb") as f:
        f.write(raw)

    remote_url = await upload_bytes_to_remote(
        data=raw,
        filename=original,
        content_type=content_type,
    )
    return {
        "success": True,
        "filename": original,
        "path": f".pi/uploads/{saved_name}",
        "size": len(raw),
        "url": remote_url,
    }
