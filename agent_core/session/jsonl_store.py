"""JSONL file-based SessionStore."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_core.session.store import (
    CompactionEntry,
    CustomEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionHeader,
    SessionMeta,
    SessionSnapshot,
    ThinkingLevelChangeEntry,
)


class JsonlStore:
    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        """Resolve the JSONL file path, guarding against path traversal via session_id."""
        path = (self._dir / f"{session_id}.jsonl").resolve()
        if not str(path).startswith(str(self._dir.resolve())):
            raise ValueError(f"Invalid session_id: path traversal detected")
        return path

    async def create_session(self, session_id: str, header: SessionHeader) -> None:
        path = self._path(session_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(header.model_dump(), ensure_ascii=False) + "\n")

    async def append_entry(self, session_id: str, entry: SessionEntry) -> None:
        path = self._path(session_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")

    async def load_session(self, session_id: str) -> SessionSnapshot:
        path = self._path(session_id)
        if not path.exists():
            raise KeyError(f"Session {session_id} not found")

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            raise ValueError(f"Session file {path} is empty")

        header = SessionHeader.model_validate(json.loads(lines[0]))
        entries: list[SessionEntry] = []
        for line in lines[1:]:
            data = json.loads(line)
            entries.append(_deserialize_entry(data))

        return SessionSnapshot(header=header, entries=entries)

    async def list_sessions(self, *, owner: str | None = None, limit: int = 50) -> list[SessionMeta]:
        result: list[SessionMeta] = []
        for file_path in sorted(self._dir.glob("*.jsonl"), reverse=True):
            sid = file_path.stem
            with open(file_path, "r", encoding="utf-8") as f:
                first = f.readline()
                if not first:
                    continue
                header = SessionHeader.model_validate(json.loads(first))
                lines = f.readlines()
                entry_count = len(lines)
                # Extract title from first user message
                title = ""
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "message":
                            msg = data.get("message", {})
                            role = msg.get("role", "")
                            content = msg.get("content", "")
                            if role == "user" and content:
                                if isinstance(content, list) and len(content) > 0:
                                    text_parts = [
                                        p.get("text", "")
                                        for p in content
                                        if isinstance(p, dict) and p.get("type") == "text"
                                    ]
                                    content_text = "".join(text_parts)
                                elif isinstance(content, str):
                                    content_text = content
                                else:
                                    content_text = str(content)
                                if content_text:
                                    title = content_text[:30] + ("..." if len(content_text) > 30 else "")
                                    break
                    except (json.JSONDecodeError, AttributeError):
                        continue
            result.append(
                SessionMeta(
                    session_id=sid,
                    created_at=header.timestamp,
                    entry_count=entry_count,
                    title=title,
                )
            )
        return result[:limit]

    async def close(self) -> None:
        pass


def _deserialize_entry(data: dict[str, Any]) -> SessionEntry:
    entry_type = data.get("type")
    if entry_type == "message":
        return MessageEntry.model_validate(data)
    if entry_type == "compaction":
        return CompactionEntry.model_validate(data)
    if entry_type == "model_change":
        return ModelChangeEntry.model_validate(data)
    if entry_type == "thinking_level_change":
        return ThinkingLevelChangeEntry.model_validate(data)
    if entry_type == "custom":
        return CustomEntry.model_validate(data)
    raise ValueError(f"Unknown entry type: {entry_type}")
