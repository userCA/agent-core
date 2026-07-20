"""Planning feature flags for http_sse scene."""

from __future__ import annotations

import os


def planning_enabled() -> bool:
    return os.environ.get("ENABLE_PLANNING", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
