"""MiniGame Protocol — pure logic, no IO, shared between frontend and backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class GameTrigger(Enum):
    STREAMING = "streaming"
    IDLE = "idle"
    MANUAL = "manual"


@dataclass
class GameConfig:
    name: str
    display_name: str
    icon: str
    triggers: list[GameTrigger]
    max_duration_s: int = 120
    cooldown_s: int = 60
    unlock_bond: int = 0


@dataclass
class GameReward:
    food_value: int
    bond_boost: float = 1.0
    items: list[str] | None = None
    exp: int = 0

    def __post_init__(self) -> None:
        if self.items is None:
            self.items = []


class MiniGame(ABC):
    """Mini-game plugin — pure logic shared between frontend (runs game locally)
    and backend (replays to verify)."""

    config: GameConfig

    @abstractmethod
    def start(self, rng: Callable[[], float], params: dict[str, Any]) -> dict[str, Any]:
        """Initialize a round with seeded rng, return initial state."""
        ...

    @abstractmethod
    def tick(self, state: dict[str, Any], action: dict[str, Any] | None) -> dict[str, Any]:
        """Advance one frame. action=None means no user input."""
        ...

    @abstractmethod
    def is_finished(self, state: dict[str, Any]) -> bool:
        """Check if the game round is over."""
        ...

    @abstractmethod
    def collect_reward(self, state: dict[str, Any]) -> GameReward:
        """Compute the reward from final state."""
        ...
