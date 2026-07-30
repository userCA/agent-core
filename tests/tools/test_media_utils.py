"""Tests for media URL helpers."""

from __future__ import annotations

import base64
from pathlib import Path

from agent_core.tools.media_utils import (
    local_path_to_public_url,
    resolve_media_url,
    save_data_uri,
)


def test_save_data_uri_and_public_url(tmp_path: Path) -> None:
    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    uri = f"data:image/png;base64,{png_b64}"
    saved = save_data_uri(uri, cwd=str(tmp_path))
    assert saved.is_file()
    url = local_path_to_public_url(saved, public_base_url="http://localhost:8001")
    assert url.startswith("http://localhost:8001/uploads/")


def test_resolve_relative_upload_path(tmp_path: Path) -> None:
    uploads = tmp_path / ".pi" / "uploads"
    uploads.mkdir(parents=True)
    f = uploads / "abc.jpg"
    f.write_bytes(b"jpg")
    url = resolve_media_url("/uploads/abc.jpg", cwd=str(tmp_path), public_base_url="http://localhost:8001")
    assert url == "http://localhost:8001/uploads/abc.jpg"
