"""Pending skill evolution proposals store.

Stores proposals that have been generated but not yet approved/rejected.
Blocks new evolution cycles while there are pending proposals.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def pending_proposals_path() -> Path:
    """Path to the pending proposals JSONL file."""
    return Path(
        os.environ.get(
            "EVOLUTION_PENDING_PATH",
            "~/.agent-core/skill-evolution-pending.jsonl",
        )
    ).expanduser()


def _read_pending() -> list[dict[str, Any]]:
    """Read all pending proposals from JSONL file."""
    path = pending_proposals_path()
    if not path.exists():
        return []
    proposals: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                proposals.append(json.loads(line))
            except json.JSONDecodeError:
                _log.warning("Skipping malformed pending proposal line")
    return proposals


def _write_pending(proposals: list[dict[str, Any]]) -> None:
    """Write all pending proposals to JSONL file (overwrite)."""
    path = pending_proposals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def get_pending_proposals(skill_name: str | None = None) -> list[dict[str, Any]]:
    """Get pending proposals, optionally filtered by skill name."""
    proposals = _read_pending()
    if skill_name is None:
        return proposals
    return [p for p in proposals if p.get("skill_name") == skill_name]


def has_pending_proposals(skill_name: str | None = None) -> bool:
    """Check if there are any pending proposals."""
    return len(get_pending_proposals(skill_name)) > 0


def add_pending_proposals(proposals: list[dict[str, Any]]) -> None:
    """Add new proposals to pending list."""
    if not proposals:
        return
    existing = _read_pending()
    # Add created_at timestamp
    for p in proposals:
        p.setdefault("pending_since", time.time())
    existing.extend(proposals)
    _write_pending(existing)
    _log.info("Added %d proposals to pending store", len(proposals))


def remove_pending_proposal(proposal_id: str) -> dict[str, Any] | None:
    """Remove a proposal by ID and return it (or None if not found)."""
    proposals = _read_pending()
    found = None
    remaining = []
    for p in proposals:
        if p.get("proposal_id") == proposal_id:
            found = p
        else:
            remaining.append(p)
    if found:
        _write_pending(remaining)
        _log.info("Removed proposal %s from pending store", proposal_id)
    return found


def clear_pending_proposals(skill_name: str | None = None) -> int:
    """Clear all pending proposals, or only for a specific skill.

    Returns the number of proposals cleared.
    """
    if skill_name is None:
        count = len(_read_pending())
        _write_pending([])
        _log.info("Cleared all %d pending proposals", count)
        return count

    proposals = _read_pending()
    remaining = [p for p in proposals if p.get("skill_name") != skill_name]
    count = len(proposals) - len(remaining)
    _write_pending(remaining)
    _log.info("Cleared %d pending proposals for skill=%s", count, skill_name)
    return count


def get_pending_summary() -> dict[str, Any]:
    """Get summary of pending proposals by skill."""
    proposals = _read_pending()
    by_skill: dict[str, int] = {}
    for p in proposals:
        skill = p.get("skill_name", "unknown")
        by_skill[skill] = by_skill.get(skill, 0) + 1
    return {
        "total": len(proposals),
        "by_skill": by_skill,
        "oldest": min((p.get("pending_since", float("inf")) for p in proposals), default=None),
    }
