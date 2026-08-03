"""Real agent execution for skill evolution validation."""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_core.core.events import AgentEnd, ToolExecutionEnd, TurnEnd
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolRegistry

from .types import TestCase


_log = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    """Outcome of a single validation harness run."""

    success: bool
    score: float
    response_text: str = ""
    error: str = ""
    tool_error_count: int = 0
    stop_reason: str = "stop"
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "score": self.score,
            "response_text": self.response_text,
            "error": self.error,
            "tool_error_count": self.tool_error_count,
            "stop_reason": self.stop_reason,
            "duration_ms": self.duration_ms,
            **self.metadata,
        }


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    text = re.sub(r"\s+", "", text.lower())
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def text_overlap(a: str, b: str) -> float:
    """Character n-gram overlap (works for Chinese and English)."""
    ga = _char_ngrams(a)
    gb = _char_ngrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga)


def score_agent_run(result: AgentRunResult | dict[str, Any], test_case: TestCase) -> float:
    """Map agent run outcome + test case expectations to 0.0–1.0."""
    if isinstance(result, AgentRunResult):
        data = result.to_dict()
        base_score = result.score
    else:
        data = result
        base_score = float(data.get("score", 1.0 if data.get("success") else 0.0))

    criteria = test_case.success_criteria
    if callable(criteria):
        try:
            return 1.0 if criteria(data) else 0.0
        except Exception:
            return 0.0

    if not data.get("success"):
        return 0.0

    score = base_score
    response = str(data.get("response_text") or "")
    expected = (test_case.expected_behavior or "").strip()
    if expected and expected.lower() not in ("should work", "no error", "complete without tool errors"):
        overlap = text_overlap(response, expected)
        score = min(1.0, max(score * 0.5, overlap))

    if isinstance(criteria, str) and criteria != "no_error":
        if criteria.lower() in response.lower():
            score = min(1.0, score + 0.1)

    return max(0.0, min(1.0, score))


class ValidationHarnessRunner:
    """Run one-turn agent execution with ephemeral skill content (no disk writes)."""

    def __init__(
        self,
        *,
        skill_name: str,
        provider: ModelProvider,
        auth_source: AuthSource | None = None,
        model: Model | None = None,
        max_turns: int = 3,
        timeout_sec: float = 60.0,
    ) -> None:
        self.skill_name = skill_name
        self.provider = provider
        self.auth_source = auth_source or AuthSource.static(api_key="")
        self.model = model or provider.list_models()[0]
        self.max_turns = max_turns
        self.timeout_sec = timeout_sec

    def _build_system_prompt(self, skill_content: str) -> str:
        body = _strip_frontmatter(skill_content)
        skill_block = (
            f'<skill name="{self.skill_name}" location="validation">\n'
            f"{body}\n"
            f"</skill>"
        )
        return (
            "You are validating whether the following skill rules help answer the user query. "
            "Follow the skill rules precisely. Be concise.\n\n"
            f"{skill_block}"
        )

    @staticmethod
    def _extract_response_text(messages: list[Any]) -> str:
        parts: list[str] = []
        for msg in reversed(messages):
            if getattr(msg, "role", None) != "assistant":
                continue
            for block in getattr(msg, "content", []) or []:
                if hasattr(block, "text"):
                    parts.append(str(block.text))
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            if parts:
                break
        return "\n".join(parts).strip()

    async def run(self, skill_content: str, input_query: str) -> AgentRunResult:
        """Execute a single validation query against the given skill markdown."""
        import asyncio

        system_prompt = self._build_system_prompt(skill_content)
        tool_errors = 0
        stop_reason = "stop"
        error_msg = ""
        turn_end: TurnEnd | None = None
        started = time.monotonic()

        harness = AgentHarness(
            provider=self.provider,
            auth_source=self.auth_source,
            store=InMemoryStore(),
            session_id=f"skill-validation-{uuid.uuid4().hex[:8]}",
            initial_state=AgentState(
                system_prompt=system_prompt,
                model=self.model,
                tools=[],
            ),
            tool_registry=ToolRegistry(),
            max_turns=self.max_turns,
            extensions=[],
        )

        async def _on_event(evt: Any) -> None:
            nonlocal tool_errors, turn_end
            if isinstance(evt, ToolExecutionEnd) and evt.is_error:
                tool_errors += 1
            if isinstance(evt, TurnEnd):
                turn_end = evt

        harness.subscribe(_on_event)
        await harness.start()
        try:
            await asyncio.wait_for(harness.prompt(input_query), timeout=self.timeout_sec)
        except asyncio.TimeoutError:
            return AgentRunResult(
                success=False,
                score=0.0,
                error="validation timeout",
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except Exception as exc:
            _log.exception("Validation harness run failed")
            return AgentRunResult(
                success=False,
                score=0.0,
                error=str(exc),
                duration_ms=(time.monotonic() - started) * 1000,
            )
        finally:
            await harness.dispose()

        response_text = self._extract_response_text(harness.state.messages)
        if turn_end is not None:
            msg = turn_end.message
            if getattr(msg, "error_message", None):
                error_msg = str(msg.error_message)
            stop_reason = str(getattr(msg, "stop_reason", "stop"))

        if harness.state.error_message:
            error_msg = error_msg or str(harness.state.error_message)

        success = (
            not error_msg
            and stop_reason not in ("error", "aborted")
            and tool_errors == 0
        )

        duration_ms = (time.monotonic() - started) * 1000
        return AgentRunResult(
            success=success,
            score=1.0 if success else 0.0,
            response_text=response_text,
            error=error_msg,
            tool_error_count=tool_errors,
            stop_reason=stop_reason,
            duration_ms=duration_ms,
        )

    async def __call__(self, skill_content: str, input_query: str) -> dict[str, Any]:
        result = await self.run(skill_content, input_query)
        return result.to_dict()
