"""Session-scoped index of artifact refs for L4 DataBus."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RefEntry:
    ref_id: str
    session_id: str
    tool_name: str = ""
    chars: int = 0
    summary: str = ""


@dataclass
class ArtifactRefIndex:
    """In-memory ref catalog keyed by session (MVP)."""

    _by_session: dict[str, dict[str, RefEntry]] = field(default_factory=dict)

    def register(
        self,
        *,
        ref_id: str,
        session_id: str,
        tool_name: str = "",
        chars: int = 0,
        summary: str = "",
    ) -> None:
        if not ref_id or not session_id:
            return
        bucket = self._by_session.setdefault(session_id, {})
        bucket[ref_id] = RefEntry(
            ref_id=ref_id,
            session_id=session_id,
            tool_name=tool_name or "",
            chars=chars,
            summary=(summary or "")[:240],
        )

    def list_for_session(self, session_id: str) -> list[RefEntry]:
        bucket = self._by_session.get(session_id) or {}
        return list(bucket.values())

    def get(self, session_id: str, ref_id: str) -> RefEntry | None:
        return (self._by_session.get(session_id) or {}).get(ref_id)

    def format_index_block(self, session_id: str) -> str:
        entries = self.list_for_session(session_id)
        if not entries:
            return ""
        lines = ["## Artifact Ref Index"]
        lines.append(
            "Use inspect_artifact(action=outline|search|get_context) to fetch "
            "exact slices — do not invent missing data."
        )
        for e in entries:
            tool = f" tool={e.tool_name}" if e.tool_name else ""
            summ = f" — {e.summary}" if e.summary else ""
            lines.append(f"- refId={e.ref_id} chars={e.chars}{tool}{summ}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)
