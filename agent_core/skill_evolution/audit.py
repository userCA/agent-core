"""Skill evolution audit log — append-only JSONL record of accept/reject decisions."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_DEFAULT_PATH = "~/.agent-core/skill-evolution-audit.jsonl"


def write_audit_entry(
    *,
    proposal_id: str,
    skill_name: str,
    action: str,  # "accept" | "reject"
    operation: str = "",
    target_rule_id: str | None = None,
    diff_summary: str = "",
    rationale: str = "",
    validation_score: float = 0.0,
    reject_reason: str | None = None,
    path: str | Path = _DEFAULT_PATH,
) -> str:
    """Write an audit entry and return its audit_id."""
    entry = {
        "audit_id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "proposal_id": proposal_id,
        "skill_name": skill_name,
        "action": action,
        "operation": operation,
        "target_rule_id": target_rule_id,
        "diff_summary": (diff_summary or "")[:200],
        "rationale": (rationale or "")[:500],
        "validation_score": validation_score,
        "reject_reason": reject_reason,
    }
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["audit_id"]


def read_audit_log(
    skill_name: str | None = None,
    limit: int = 50,
    path: str | Path = _DEFAULT_PATH,
) -> list[dict[str, Any]]:
    """Read recent audit entries, optionally filtered by skill."""
    p = Path(path).expanduser()
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skill_name and entry.get("skill_name") != skill_name:
                continue
            entries.append(entry)
    entries.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return entries[:limit]
