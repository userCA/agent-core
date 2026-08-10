"""Workflow feature flags for http_sse scene."""

from __future__ import annotations

import os


def workflows_enabled() -> bool:
    return os.environ.get("ENABLE_WORKFLOWS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
