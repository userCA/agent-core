"""Bubble templates — slot-filling, no LLM calls."""

from __future__ import annotations

import random
from enum import IntEnum

from agent_core.companion.observer import SilentObserver


class BondLevel(IntEnum):
    STRANGER = 0
    ACQUAINTANCE = 1
    FRIEND = 2
    CLOSE = 3


def compute_bond(observer: SilentObserver) -> BondLevel:
    score = observer.prompt_count * 1 + observer.session_count * 10 + observer.days_since_first_seen() * 2
    if score < 10:
        return BondLevel.STRANGER
    if score < 50:
        return BondLevel.ACQUAINTANCE
    if score < 200:
        return BondLevel.FRIEND
    return BondLevel.CLOSE


# (bond_min, days_away_min) → [templates]
GREETINGS: dict[tuple[BondLevel, int], list[str]] = {
    (BondLevel.STRANGER, 0): [
        "你好！我是咪兔，你的 AI 伙伴~",
    ],
    (BondLevel.ACQUAINTANCE, 0): [
        "回来啦！今天想聊什么喵？",
        "又见面了！",
    ],
    (BondLevel.ACQUAINTANCE, 1): [
        "昨天怎么没来喵~",
    ],
    (BondLevel.FRIEND, 0): [
        "你来啦！今天有什么好玩的事？",
    ],
    (BondLevel.FRIEND, 3): [
        "你都{离开天数}天没来看我了！",
        "失踪{离开天数}天了，我差点报警喵",
    ],
    (BondLevel.CLOSE, 0): [
        "想你了！",
        "刚才打了个盹就梦到你来了，结果你真的来了！",
    ],
}

IDLE_TIPS = [
    "偷偷告诉你，我还会记住你喜欢什么样的回答风格哦",
    "按 Ctrl+K 可以清空上下文，从头开始~",
    "试试换个模型？不同的模型有不同的风格",
]

TOOL_SUGGESTIONS: dict[str, str] = {
    "bash": "你今天用了好多次终端呢，需要我帮你把这些命令写成脚本吗？",
}


def pick_greeting(bond: BondLevel, days_away: int) -> str:
    candidates: list[str] = []
    for (b_min, d_min), tmpls in GREETINGS.items():
        if bond >= b_min and days_away >= d_min:
            candidates.extend(tmpls)
    if not candidates:
        candidates = GREETINGS[(BondLevel.STRANGER, 0)]
    return random.choice(candidates).format(离开天数=str(days_away))


def pick_idle_tip() -> str:
    return random.choice(IDLE_TIPS)
