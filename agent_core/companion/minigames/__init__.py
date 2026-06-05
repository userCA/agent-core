"""Mini-game plugin registry."""

from __future__ import annotations

from agent_core.companion.minigames.base import GameConfig, GameReward, MiniGame

_registry: dict[str, type[MiniGame]] = {}


def register(game_cls: type[MiniGame]) -> type[MiniGame]:
    _registry[game_cls.config.name] = game_cls
    return game_cls


def get_game(name: str) -> type[MiniGame] | None:
    return _registry.get(name)


def list_games() -> list[GameConfig]:
    return [g.config for g in _registry.values()]


# Register built-in games
from agent_core.companion.minigames.fishing.game import FishingGame  # noqa: E402
register(FishingGame)
