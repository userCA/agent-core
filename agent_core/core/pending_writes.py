"""Pending session writes — queued during busy phase, flushed at save points.

When the harness is running a turn (phase=TURN), config changes like
``set_model()`` or ``set_thinking_level()`` cannot be persisted immediately.
They are enqueued as ``PendingSessionWrite`` entries and flushed at the
next save point (between turns) or at agent_end.

This mirrors TS ``pendingSessionWrites`` (agent-harness.ts:168, 462-486).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingSessionWrite:
    """A deferred persistence operation.

    ``type`` values:
        * ``message`` — append a message to the session
        * ``model_change`` — persist model switch
        * ``thinking_level_change`` — persist thinking level switch
        * ``active_tools_change`` — persist active tool set
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)
