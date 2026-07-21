"""Safe cut-point helpers for compaction (tool/assistant pairing)."""

from __future__ import annotations

from typing import Any

DEFAULT_MIN_KEEP = 6
DEFAULT_MIN_DELETE = 2


def find_safe_cutoff(
    messages: list[Any],
    keep_recent: int,
    *,
    min_keep: int = DEFAULT_MIN_KEEP,
    min_delete: int = DEFAULT_MIN_DELETE,
) -> int | None:
    """Return start index of the kept suffix, or None if compaction should skip.

    Rules (aligned with agent_engineering L3):
    - Prefer keeping at least *min_keep* when the transcript is long enough.
    - Delete at least *min_delete* only under the same long-transcript gate
      (so short lists honor *keep_recent* exactly).
    - Never start the kept window on a ``tool_result`` — walk back so tool
      pairs stay intact.
    """
    n = len(messages)
    if n == 0 or keep_recent <= 0:
        return None
    if n <= keep_recent:
        return None

    keep = keep_recent
    long_enough = n >= min_keep + min_delete
    if long_enough:
        keep = max(keep_recent, min_keep)
        keep = min(keep, n - min_delete)

    if keep >= n:
        return None

    cutoff = n - keep

    while cutoff < n and getattr(messages[cutoff], "role", None) == "tool_result":
        cutoff -= 1
        if cutoff <= 0:
            return None

    if cutoff <= 0:
        return None
    if long_enough and cutoff < min_delete:
        return None
    return cutoff
