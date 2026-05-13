"""SteeringQueue / FollowUpQueue — internal pending-message buffers."""

from __future__ import annotations

from typing import Any, Literal

QueueMode = Literal["all", "one-at-a-time"]


class PendingMessageQueue:
    def __init__(self, mode: QueueMode = "one-at-a-time") -> None:
        self.mode: QueueMode = mode
        self._items: list[Any] = []

    def enqueue(self, message: Any) -> None:
        self._items.append(message)

    def has_items(self) -> bool:
        return bool(self._items)

    def drain(self) -> list[Any]:
        if not self._items:
            return []
        if self.mode == "all":
            drained = list(self._items)
            self._items.clear()
            return drained
        return [self._items.pop(0)]

    def clear(self) -> None:
        self._items.clear()
