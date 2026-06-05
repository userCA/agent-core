"""Fishing mini-game — 5-phase state machine."""

from __future__ import annotations

from typing import Any, Callable

from agent_core.companion.minigames.base import GameConfig, GameReward, GameTrigger, MiniGame
from agent_core.companion.minigames.fishing.fish_table import roll_fish, roll_fish_table


class FishingGame(MiniGame):
    config = GameConfig(
        name="fishing",
        display_name="钓鱼",
        icon="🎣",
        triggers=[GameTrigger.STREAMING, GameTrigger.MANUAL],
        max_duration_s=90,
        cooldown_s=30,
    )

    def start(self, rng: Callable[[], float], params: dict[str, Any]) -> dict[str, Any]:
        bonus = params.get("rarity_bonus", 0)
        return {
            "phase": "waiting",
            "pond": roll_fish_table(rng, bonus),
            "bobber_position": int(rng() * 80 + 10),
            "bite_timer": rng() * 6.0 + 2.0,
            "fish_on_hook": None,
            "reel_tension": 0.0,
            "catches": [],
            "timer": 0.0,
            "_rng": rng,
        }

    def tick(self, state: dict[str, Any], action: dict[str, Any] | None) -> dict[str, Any]:
        state["timer"] += 0.1
        rng = state["_rng"]

        match state["phase"]:
            case "waiting":
                if state["timer"] >= state["bite_timer"]:
                    state["phase"] = "biting"
                    state["fish_on_hook"] = roll_fish(state["pond"], rng)
                    state["bite_window"] = rng() * 0.9 + 0.6

            case "biting":
                if action and action.get("type") == "reel":
                    if state["timer"] <= state["bite_timer"] + state["bite_window"]:
                        state["phase"] = "reeling"
                        state["reel_tension"] = 0.3
                    else:
                        state["phase"] = "missed"
                        state["fish_on_hook"] = None

            case "reeling":
                if action and action.get("type") == "pull":
                    state["reel_tension"] = min(1.0, state["reel_tension"] + 0.05)
                else:
                    state["reel_tension"] = max(0.0, state["reel_tension"] - 0.02)

                if state["reel_tension"] >= 1.0:
                    state["phase"] = "caught"
                    state["catches"].append(state["fish_on_hook"])
                elif state["reel_tension"] <= 0.0:
                    state["phase"] = "missed"
                    state["fish_on_hook"] = None

            case "missed":
                if state["timer"] >= state["bite_timer"] + 3.0:
                    state["phase"] = "waiting"
                    state["bite_timer"] = state["timer"] + rng() * 4.5 + 1.5

            case "caught":
                if state["timer"] >= state["bite_timer"] + 2.0:
                    state["phase"] = "waiting"
                    state["bite_timer"] = state["timer"] + rng() * 4.5 + 1.5
                    state["fish_on_hook"] = None

        return state

    def is_finished(self, state: dict[str, Any]) -> bool:
        return state["timer"] >= self.config.max_duration_s

    def collect_reward(self, state: dict[str, Any]) -> GameReward:
        catches = state.get("catches", [])
        total_food = sum(f.food_value for f in catches)
        rarest = max((f.rarity_rank for f in catches), default=0)
        return GameReward(
            food_value=total_food,
            bond_boost=1.0 + rarest * 0.25,
            items=[f.name for f in catches],
            exp=total_food * (1 + rarest),
        )
