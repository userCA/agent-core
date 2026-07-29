"""Debug replay recorder — persists per-run event summaries as JSON files.

When ``ENABLE_RUN_REPLAY=1``, the recorder subscribes to agent events and
writes a compact JSON summary after each run.  This allows post-mortem
analysis without a cloud panel:

    debug_runs/
        scene-1778689865802/
            run-a1b2c3d4e5f6.json
            run-f6e5d4c3b2a1.json

Each file contains:
- ``session_id``, ``run_id``, ``started_at``, ``ended_at``
- Ordered list of events with type and key fields (no full token streams)
- Usage summary (tokens, tool calls, stop reason)

Usage::

    from scene.http_sse.replay import RunReplayRecorder

    recorder = RunReplayRecorder(session_id="scene-123")
    assistant.on_event(recorder.handle_event)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)

_log = logging.getLogger(__name__)


def replay_enabled() -> bool:
    return os.environ.get("ENABLE_RUN_REPLAY", "0") == "1"


class RunReplayRecorder:
    """Collects agent events during a run and writes a JSON replay file."""

    def __init__(
        self,
        *,
        session_id: str,
        base_dir: str = "debug_runs",
    ) -> None:
        self._session_id = session_id
        self._base_dir = Path(base_dir)
        self._run_id: str = ""
        self._started_at: float = 0.0
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._turn_count: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._stop_reasons: list[str] = []

    def handle_event(self, evt: AgentEvent) -> None:
        """Subscribe to agent events. Call via ``assistant.on_event(...)``."""
        if isinstance(evt, AgentStart):
            self._run_id = evt.run_id or f"run-{int(time.time() * 1000)}"
            self._started_at = time.time()
            self._append("agent_start", run_id=self._run_id)

        elif isinstance(evt, TurnStart):
            self._turn_count += 1
            self._append("turn_start", turn=self._turn_count)

        elif isinstance(evt, ToolExecutionStart):
            self._append(
                "tool_start",
                tool=evt.tool_name,
                call_id=evt.tool_call_id,
            )

        elif isinstance(evt, ToolExecutionEnd):
            entry = {
                "tool": evt.tool_name,
                "call_id": evt.tool_call_id,
                "is_error": evt.is_error,
            }
            self._append("tool_end", **entry)
            self._tool_calls.append(entry)

        elif isinstance(evt, TurnEnd):
            msg = evt.message
            usage = getattr(msg, "usage", None)
            stop = getattr(msg, "stop_reason", "")
            entry: dict[str, Any] = {"turn": self._turn_count, "stop": stop}
            if usage:
                entry["in_tokens"] = getattr(usage, "input_tokens", 0)
                entry["out_tokens"] = getattr(usage, "output_tokens", 0)
                self._total_input_tokens += entry["in_tokens"]
                self._total_output_tokens += entry["out_tokens"]
            if stop:
                self._stop_reasons.append(stop)
            self._append("turn_end", **entry)

        elif isinstance(evt, AgentEnd):
            self._append("agent_end")
            self._flush()

    def _append(self, event_type: str, **fields: Any) -> None:
        self._events.append({
            "t": round(time.time() - self._started_at, 3) if self._started_at else 0.0,
            "type": event_type,
            **fields,
        })

    def _flush(self) -> None:
        if not self._run_id:
            return

        out_dir = self._base_dir / self._session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self._run_id}.json"

        ended_at = time.time()
        replay = {
            "session_id": self._session_id,
            "run_id": self._run_id,
            "started_at": datetime.fromtimestamp(
                self._started_at, tz=timezone.utc
            ).isoformat(),
            "ended_at": datetime.fromtimestamp(
                ended_at, tz=timezone.utc
            ).isoformat(),
            "elapsed_ms": round((ended_at - self._started_at) * 1000, 1),
            "turns": self._turn_count,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "stop_reasons": self._stop_reasons,
            "tool_calls": self._tool_calls,
            "events": self._events,
        }

        try:
            out_path.write_text(
                json.dumps(replay, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            _log.info("Run replay written to %s", out_path)
        except Exception:
            _log.warning("Failed to write run replay to %s", out_path, exc_info=True)

        # Reset for next run (recorder is reused per session)
        self._run_id = ""
        self._started_at = 0.0
        self._events = []
        self._tool_calls = []
        self._turn_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._stop_reasons = []
