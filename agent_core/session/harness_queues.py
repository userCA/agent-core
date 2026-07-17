"""Queue operations for AgentHarness."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import QueueUpdate
from agent_core.core.queue import QueueMode
from agent_core.core.state import AgentHarnessPhase

if TYPE_CHECKING:
    from agent_core.session.harness import AgentHarness


class HarnessQueuesMixin:
    """Mixin: steer / follow_up / next_turn queues."""

    async def steer(self: AgentHarness, message: Any) -> None:
        if self.phase == AgentHarnessPhase.IDLE:
            raise AgentHarnessError(
                "invalid_state", "steer() requires an active turn; use next_turn() while idle",
            )
        self._steering.enqueue(message)
        await self._emit_queue_update()

    async def follow_up(self: AgentHarness, message: Any) -> None:
        if self.phase == AgentHarnessPhase.IDLE:
            raise AgentHarnessError(
                "invalid_state", "follow_up() requires an active turn; use next_turn() while idle",
            )
        self._follow_up.enqueue(message)
        await self._emit_queue_update()

    async def next_turn(self: AgentHarness, message: Any) -> None:
        self._next_turn.enqueue(message)
        await self._emit_queue_update()

    def clear_all_queues(self: AgentHarness) -> None:
        self._steering.clear()
        self._follow_up.clear()

    @property
    def steering_mode(self: AgentHarness) -> QueueMode:
        return self._steering.mode

    @steering_mode.setter
    def steering_mode(self: AgentHarness, mode: QueueMode) -> None:
        self._steering.mode = mode

    @property
    def followup_mode(self: AgentHarness) -> QueueMode:
        return self._follow_up.mode

    @followup_mode.setter
    def followup_mode(self: AgentHarness, mode: QueueMode) -> None:
        self._follow_up.mode = mode

    def has_queued_messages(self: AgentHarness) -> bool:
        return (
            self._steering.has_items()
            or self._follow_up.has_items()
            or self._next_turn.has_items()
        )

    async def _emit_queue_update(self: AgentHarness) -> None:
        await self._notify_listeners(QueueUpdate(
            steer_count=self._steering.item_count,
            follow_up_count=self._follow_up.item_count,
            next_turn_count=self._next_turn.item_count,
        ))

    async def drain_steering(self: AgentHarness) -> list[Any]:
        return self._steering.drain()

    async def drain_follow_up(self: AgentHarness) -> list[Any]:
        return self._follow_up.drain()

    def _drain_next_turn(self: AgentHarness) -> list[Any]:
        return self._next_turn.drain()
