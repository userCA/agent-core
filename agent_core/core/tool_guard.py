"""Guards that block pathological tool-call patterns (H1)."""

from __future__ import annotations

import json
import threading
from typing import Any

DUPLICATE_TOOL_CALL = "DUPLICATE_TOOL_CALL"


def tool_call_fingerprint(name: str, arguments: dict[str, Any] | None) -> str:
    """Stable fingerprint for (tool name, raw arguments).

    Fingerprints use raw call arguments (before hooks / args_model normalization).
    Non-JSON-serializable values fall back via ``default=str``; circular
    structures degrade to an unhashable marker so the tool path does not crash.
    """
    try:
        payload = json.dumps(
            arguments or {},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        payload = "<unhashable>"
    return f"{name}:{payload}"


class DuplicateToolCallGuard:
    """Block consecutive identical tool+args after *max_repeats* checks.

    Allows the first *max_repeats* consecutive identical fingerprints (whether
    the subsequent tool execution succeeds or fails), then returns an error
    for further consecutive duplicates. A different fingerprint resets the
    streak. Blocked checks do not append to the recent history.
    """

    def __init__(self, *, max_repeats: int = 3) -> None:
        if max_repeats < 1:
            raise ValueError("max_repeats must be >= 1")
        self._max_repeats = max_repeats
        self._recent: list[str] = []
        self._lock = threading.Lock()

    @property
    def max_repeats(self) -> int:
        return self._max_repeats

    def check(self, name: str, arguments: dict[str, Any] | None) -> str | None:
        """Return an error string when the call should be blocked, else None."""
        fp = tool_call_fingerprint(name, arguments)
        with self._lock:
            streak = 0
            for prev in reversed(self._recent):
                if prev != fp:
                    break
                streak += 1
            if streak >= self._max_repeats:
                return (
                    f"{DUPLICATE_TOOL_CALL}: tool '{name}' with identical arguments "
                    f"was already called {streak} times consecutively; "
                    f"refusing further repeats (limit={self._max_repeats}). "
                    "Change arguments or choose a different tool."
                )
            self._recent.append(fp)
            if len(self._recent) > 256:
                self._recent = self._recent[-128:]
        return None
