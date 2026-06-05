"""Domain types shared between companion library and extension."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CompanionBubble:
    text: str
    ttl_ms: int = 8000
    priority: str = "normal"
