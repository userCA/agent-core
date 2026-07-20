"""Customer-service expert profiles for H5 multi-agent mode.

Reuses the same profile definitions as http_sse so both scenes stay aligned.
"""

from __future__ import annotations

from scene.http_sse.multi_agent_profiles import (
    default_cs_profiles,
    default_multi_agent_options,
    multi_agent_enabled,
)

__all__ = [
    "default_cs_profiles",
    "default_multi_agent_options",
    "multi_agent_enabled",
]
