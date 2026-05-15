"""Human-in-the-loop primitives for turn-level pause/resume."""

from __future__ import annotations

import asyncio
from typing import Any


class RequiresHumanInput(Exception):
    """Raised by a tool when it needs additional human input to proceed.

    Attributes:
        prompt: The message/question shown to the user.
        input_schema: JSON-schema-like dict describing expected input fields.
    """

    def __init__(self, prompt: str, input_schema: dict[str, Any]) -> None:
        self.prompt = prompt
        self.input_schema = input_schema
        super().__init__(prompt)


class HumanInputGate:
    """Synchronisation primitive that lets the agent loop pause for human input.

    Usage:
        gate = HumanInputGate()
        # In the loop:
        future = gate.require_input(tool_call_id)
        yield HumanInputRequired(...)
        values = await future          # <-- loop pauses here

        # From another task / HTTP handler:
        gate.provide_input(tool_call_id, {"address": "..."})
        # <-- future resolves, loop resumes
    """

    def __init__(self) -> None:
        self._futures: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def require_input(self, tool_call_id: str) -> asyncio.Future[dict[str, Any]]:
        """Create and return a Future that the loop can await."""
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._futures[tool_call_id] = future
        return future

    def provide_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        """Resolve the pending future for *tool_call_id*.

        Returns True if a pending future was resolved, False otherwise.
        """
        future = self._futures.pop(tool_call_id, None)
        if future is None:
            return False
        if future.done():
            return False
        future.set_result(values)
        return True

    def is_waiting(self, tool_call_id: str) -> bool:
        """Return True if we are currently awaiting input for *tool_call_id*."""
        future = self._futures.get(tool_call_id)
        return future is not None and not future.done()

    def cancel_all(self) -> None:
        """Cancel every outstanding future (e.g. on abort)."""
        for future in list(self._futures.values()):
            if not future.done():
                future.cancel()
        self._futures.clear()
