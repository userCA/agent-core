"""Channel configuration persistence — .pi/channels.json"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

CHANNELS_FILE = "channels.json"


def _channels_path(cwd: str) -> Path:
    return Path(cwd) / ".pi" / CHANNELS_FILE


def load_channels(cwd: str) -> list[dict[str, Any]]:
    """Load channel configs from .pi/channels.json."""
    path = _channels_path(cwd)
    if not path.exists():
        return _defaults()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        channels = data.get("channels", [])
        return [_sanitize_channel(c) for c in channels]
    except Exception:
        _log.warning("Failed to load channels, using defaults")
        return _defaults()


def save_channels(cwd: str, channels: list[dict[str, Any]]) -> None:
    """Save channel configs to .pi/channels.json."""
    path = _channels_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Strip secrets for non-active channels
    cleaned = []
    for ch in channels:
        c = dict(ch)
        c["app_secret"] = "********"  # Mask in saved file
        cleaned.append(c)
    path.write_text(json.dumps({"channels": channels}, ensure_ascii=False, indent=2))


def _defaults() -> list[dict[str, Any]]:
    """Default channel configs from env vars (backward compat)."""
    channels = []
    # Feishu from env
    app_id = os.environ.get("FEISHU_APP_ID", "")
    if app_id:
        channels.append({
            "id": "feishu",
            "name": "飞书",
            "type": "feishu",
            "enabled": True,
            "app_id": app_id,
            "app_secret": os.environ.get("FEISHU_APP_SECRET", ""),
        })
    return channels


def _sanitize_channel(ch: dict) -> dict:
    """Ensure channel dict has required fields."""
    ch.setdefault("id", ch.get("name", "unknown"))
    ch.setdefault("enabled", True)
    ch.setdefault("type", "feishu")
    ch.setdefault("app_id", "")
    ch.setdefault("app_secret", "")
    if "name" not in ch:
        ch["name"] = ch["id"]
    return ch
