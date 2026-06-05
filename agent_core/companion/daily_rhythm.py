"""Daily rhythm — 7-period cycle affecting energy, mood, animation pool."""

from __future__ import annotations

import time

# 7 periods (user local time)
PERIODS: dict[str, tuple[int, int]] = {
    "MORNING":     (6, 9),
    "FORENOON":    (9, 12),
    "NOON":        (12, 14),
    "AFTERNOON":   (14, 18),
    "EVENING":     (18, 20),
    "NIGHT":       (20, 23),
    "LATE_NIGHT":  (23, 6),
}

# Per-period multipliers
PERIOD_PARAMS: dict[str, dict[str, float]] = {
    "MORNING":    {"energy": 0.7, "mood_cap": 80, "bubble_mult": 0.5,  "zzz_min": 15},
    "FORENOON":   {"energy": 1.0, "mood_cap": 100, "bubble_mult": 1.0, "zzz_min": 30},
    "NOON":       {"energy": 0.6, "mood_cap": 70, "bubble_mult": 0.4,  "zzz_min": 10},
    "AFTERNOON":  {"energy": 1.0, "mood_cap": 100, "bubble_mult": 1.0,  "zzz_min": 30},
    "EVENING":    {"energy": 1.3, "mood_cap": 100, "bubble_mult": 1.5,  "zzz_min": 60},
    "NIGHT":      {"energy": 0.9, "mood_cap": 90, "bubble_mult": 0.8,  "zzz_min": 20},
    "LATE_NIGHT": {"energy": 0.4, "mood_cap": 60, "bubble_mult": 0.2,  "zzz_min": 5},
}

# Quirk overrides
QUIRK_OVERRIDES: dict[str, dict[str, dict[str, float]]] = {
    "night_owl": {
        "MORNING":     {"energy": 0.4},
        "FORENOON":    {"energy": 0.5},
        "NOON":        {"energy": 0.4},
        "EVENING":     {"energy": 1.0},
        "NIGHT":       {"energy": 1.3},
        "LATE_NIGHT":  {"energy": 1.0},
    },
    "sleepyhead": {
        "__all__": {"zzz_min": 0.5},  # halve all zzz thresholds
    },
}

# Period → frontend mood (for idle long enough to trigger sleep)
PERIOD_IDLE_MOOD: dict[str, str] = {
    "MORNING":    "awake",
    "FORENOON":   "awake",
    "NOON":       "sleeping",
    "AFTERNOON":  "awake",
    "EVENING":    "awake",
    "NIGHT":      "awake",
    "LATE_NIGHT": "sleeping",
}


def get_period(hour: int | None = None) -> str:
    """Return current period name based on local hour."""
    if hour is None:
        hour = time.localtime().tm_hour
    for name, (start, end) in PERIODS.items():
        if end > start:
            if start <= hour < end:
                return name
        else:  # overnight range (e.g. 23-6)
            if hour >= start or hour < end:
                return name
    return "FORENOON"


def energy_multiplier(quirk: str = "") -> float:
    """Current energy multiplier considering period + quirk."""
    period = get_period()
    base = PERIOD_PARAMS.get(period, {}).get("energy", 1.0)

    if quirk in QUIRK_OVERRIDES:
        override = QUIRK_OVERRIDES[quirk].get(period, {})
        if "energy" in override:
            return override["energy"]
        all_override = QUIRK_OVERRIDES[quirk].get("__all__", {})
        if "energy" in all_override:
            return base * all_override["energy"]

    return base


def zzz_threshold_minutes(quirk: str = "") -> float:
    """Minutes of idle before SLEEPY mood triggers."""
    period = get_period()
    base = PERIOD_PARAMS.get(period, {}).get("zzz_min", 30)

    if quirk == "sleepyhead":
        return base * 0.5
    if quirk == "night_owl":
        night_params = QUIRK_OVERRIDES.get("night_owl", {}).get(period, {})
        if "energy" in night_params and night_params["energy"] >= 1.0:
            return base * 2  # night owl is MORE awake at night

    return base


def bubble_frequency_multiplier(quirk: str = "") -> float:
    """Adjust bubble frequency by time of day."""
    period = get_period()
    return PERIOD_PARAMS.get(period, {}).get("bubble_mult", 1.0)


def current_params(quirk: str = "") -> dict[str, float]:
    """All current period params, with quirk applied."""
    period = get_period()
    params = dict(PERIOD_PARAMS.get(period, PERIOD_PARAMS["FORENOON"]))

    if quirk in QUIRK_OVERRIDES:
        override = QUIRK_OVERRIDES[quirk].get(period, {})
        params.update(override)
        all_override = QUIRK_OVERRIDES[quirk].get("__all__", {})
        for k, v in all_override.items():
            if k in params:
                params[k] *= v

    return params
