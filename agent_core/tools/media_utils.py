"""Media path/URL helpers for short-drama pipeline."""

from __future__ import annotations

import base64
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DATA_URI_RE = re.compile(r"^data:(image/[^;]+);base64,(.+)$", re.DOTALL)


def default_public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


def uploads_dir(cwd: str | None = None) -> Path:
    root = Path(cwd or os.getcwd())
    path = root / ".pi" / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def renders_dir(cwd: str | None = None) -> Path:
    root = Path(cwd or os.getcwd())
    path = root / ".pi" / "renders"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ext_for_mime(mime: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(mime.lower(), ".bin")


def save_data_uri(data_uri: str, *, cwd: str | None = None, subdir: str = "uploads") -> Path:
    """Persist a data URI to .pi/uploads or .pi/renders and return local path."""
    match = _DATA_URI_RE.match(data_uri.strip())
    if not match:
        raise ValueError("Invalid image data URI")
    mime, payload = match.group(1), match.group(2)
    raw = base64.b64decode(payload)
    base = uploads_dir(cwd) if subdir == "uploads" else renders_dir(cwd)
    name = f"{uuid.uuid4().hex[:12]}{_ext_for_mime(mime)}"
    dest = base / name
    dest.write_bytes(raw)
    return dest


def local_path_to_public_url(local_path: Path | str, *, public_base_url: str) -> str:
    """Map a file under .pi/uploads or .pi/renders to a /uploads or /renders URL."""
    path = Path(local_path).resolve()
    parts = path.parts
    if ".pi" in parts:
        idx = parts.index(".pi")
        if len(parts) > idx + 2 and parts[idx + 1] in ("uploads", "renders"):
            bucket = parts[idx + 1]
            filename = parts[idx + 2]
            return f"{public_base_url.rstrip('/')}/{bucket}/{filename}"
    return str(local_path)


def resolve_media_url(
    value: Any,
    *,
    cwd: str | None = None,
    public_base_url: str | None = None,
) -> str:
    """Normalize HITL uploads, relative paths, and http URLs for downstream APIs."""
    if not value:
        raise ValueError("Empty media reference")

    base = (public_base_url or default_public_base_url()).rstrip("/")
    text = str(value).strip()

    if text.startswith("data:"):
        saved = save_data_uri(text, cwd=cwd)
        rel = saved.relative_to(Path(cwd or os.getcwd()) / ".pi")
        return f"{base}/{rel.as_posix()}"

    if text.startswith("http://") or text.startswith("https://"):
        return text

    if text.startswith("/uploads/") or text.startswith("/renders/"):
        return f"{base}{text}"

    if text.startswith(".pi/uploads/"):
        return f"{base}/uploads/{Path(text).name}"
    if text.startswith(".pi/renders/"):
        return f"{base}/renders/{Path(text).name}"

    parsed = urlparse(text)
    if parsed.scheme == "" and os.path.isabs(text):
        return local_path_to_public_url(text, public_base_url=base)

    cwd_path = Path(cwd or os.getcwd()) / text
    if cwd_path.is_file():
        return local_path_to_public_url(cwd_path, public_base_url=base)

    return text


def resolve_media_list(
    values: list[Any] | None,
    *,
    cwd: str | None = None,
    public_base_url: str | None = None,
) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for item in values:
        if isinstance(item, list):
            out.extend(resolve_media_list(item, cwd=cwd, public_base_url=public_base_url))
        else:
            out.append(resolve_media_url(item, cwd=cwd, public_base_url=public_base_url))
    return out
