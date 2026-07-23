"""Path case store and top-k recall for skill evolution."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Polarity = Literal["positive", "negative"]

_TOKEN_RE = re.compile(r"[a-z0-9_\u4e00-\u9fff]+", re.IGNORECASE)


@dataclass
class PathCase:
    """One distilled path example stored beside a skill."""

    polarity: Polarity
    query: str
    path: str
    skill_name: str = ""
    source_trace_id: str | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PathCase:
        pol = data.get("polarity", "positive")
        if pol not in ("positive", "negative"):
            pol = "positive"
        return cls(
            polarity=pol,  # type: ignore[arg-type]
            query=str(data.get("query", "")),
            path=str(data.get("path", "")),
            skill_name=str(data.get("skill_name", "")),
            source_trace_id=data.get("source_trace_id"),
            created_at=float(data.get("created_at") or time.time()),
            metadata=dict(data.get("metadata") or {}),
        )


def cases_dir(skill_dir: Path | str, skill_name: str) -> Path:
    return Path(skill_dir) / skill_name / "cases"


def case_file(skill_dir: Path | str, skill_name: str, polarity: Polarity) -> Path:
    return cases_dir(skill_dir, skill_name) / f"{polarity}.jsonl"


def append_case(skill_dir: Path | str, case: PathCase) -> Path:
    """Append a case to positive.jsonl or negative.jsonl; create dirs as needed."""
    path = case_file(skill_dir, case.skill_name, case.polarity)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_cases(
    skill_dir: Path | str,
    skill_name: str,
    *,
    polarity: Polarity | None = None,
    limit: int = 200,
) -> list[PathCase]:
    """Load cases for a skill (newest last in file; return up to limit)."""
    polarities: list[Polarity]
    if polarity is None:
        polarities = ["positive", "negative"]
    else:
        polarities = [polarity]

    out: list[PathCase] = []
    for pol in polarities:
        path = case_file(skill_dir, skill_name, pol)
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(PathCase.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    if len(out) > limit:
        return out[-limit:]
    return out


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")}


def score_case_relevance(query: str, case: PathCase) -> float:
    """Simple token overlap score in [0, 1]."""
    q = _tokens(query)
    if not q:
        return 0.0
    c = _tokens(f"{case.query} {case.path}")
    if not c:
        return 0.0
    return len(q & c) / len(q | c)


def select_top_k_cases(
    query: str,
    cases: list[PathCase],
    *,
    k: int = 3,
    min_score: float = 0.05,
) -> list[PathCase]:
    """Rank cases by keyword overlap; prefer mixing polarities when possible."""
    if k <= 0 or not cases:
        return []
    ranked = sorted(
        ((score_case_relevance(query, c), c) for c in cases),
        key=lambda x: x[0],
        reverse=True,
    )
    picked: list[PathCase] = []
    for score, case in ranked:
        if score < min_score:
            break
        picked.append(case)
        if len(picked) >= k:
            break
    return picked


def format_cases_for_prompt(cases: list[PathCase], *, max_chars: int = 2000) -> str:
    """Format cases for system/context injection under a token budget."""
    if not cases:
        return ""
    lines = ["## Path Cases (retrieved)", ""]
    lines.append("Prefer positive paths; avoid negative paths when the task matches.")
    lines.append("")
    for i, case in enumerate(cases, 1):
        lines.append(f"### Case {i} [{case.polarity}]")
        lines.append(f"- query: {case.query[:200]}")
        lines.append(f"- path: {case.path[:300]}")
        lines.append("")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def parse_case_content_from_proposal(new_content: str | None) -> tuple[str, str]:
    """Parse Distiller add_case body: 'POSITIVE\\nquery: ...\\npath: ...'."""
    text = new_content or ""
    query = ""
    path = ""
    for line in text.splitlines():
        low = line.strip()
        if low.lower().startswith("query:"):
            query = low.split(":", 1)[1].strip()
        elif low.lower().startswith("path:"):
            path = low.split(":", 1)[1].strip()
    return query, path
