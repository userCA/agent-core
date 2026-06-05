"""Bubble templates — slot-filling, no LLM, breed-aware."""

from __future__ import annotations

import random
from enum import IntEnum

from agent_core.companion.observer import SilentObserver

# breed talkativeness from §12 breed-profiles.md
BREED_TALKATIVENESS: dict[str, float] = {
    "orange_tabby": 0.35, "tuxedo": 0.60, "calico": 0.50,
    "siamese": 0.90, "black_cat": 0.20, "ragdoll": 0.40, "scottish_fold": 0.30,
}


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


def breed_talkativeness(breed: str) -> float:
    return BREED_TALKATIVENESS.get(breed, 0.5)


# ---- greetings (bond_min, days_away_min) → [templates] -----------------

# 橘猫 — food-motivated, lazy
GREETINGS_ORANGE: dict[tuple[BondLevel, int], list[str]] = {
    (BondLevel.STRANGER, 0): ["你好喵~ 我是咪兔。有吃的吗？"],
    (BondLevel.ACQUAINTANCE, 0): ["回来啦喵~ 今天带零食了吗？", "又见面了！刚睡醒..."],
    (BondLevel.ACQUAINTANCE, 1): ["昨天没来喵... 我等睡着了 zzZ"],
    (BondLevel.FRIEND, 0): ["你来啦！吃饱了才有力气聊天喵~"],
    (BondLevel.FRIEND, 3): ["{离开天数}天没来... 我都饿瘦了喵"],
    (BondLevel.CLOSE, 0): ["（翻肚皮）摸一下...再给点吃的就完美了"],
}

# 暹罗 — gossipy, talkative
GREETINGS_SIAMESE: dict[tuple[BondLevel, int], list[str]] = {
    (BondLevel.STRANGER, 0): ["你好！我是咪兔，你的专属 AI 伙伴喵！我跟你说..."],
    (BondLevel.ACQUAINTANCE, 0): ["回来啦！今天有什么新鲜事？快告诉喵！", "又见面了！你知道吗..."],
    (BondLevel.ACQUAINTANCE, 1): ["昨天没来喵！错过了一个八卦！"],
    (BondLevel.FRIEND, 0): ["你来啦！今天隔壁项目组换框架了你知道吗喵！"],
    (BondLevel.FRIEND, 3): ["{离开天数}天！！你知道你错过了多少事吗！！"],
    (BondLevel.CLOSE, 0): ["想你了！我有好多话要跟你说喵~"],
}

# 黑猫 — cryptic, poetic
GREETINGS_BLACK: dict[tuple[BondLevel, int], list[str]] = {
    (BondLevel.STRANGER, 0): ["...（从暗处走出来）你好。"],
    (BondLevel.ACQUAINTANCE, 0): ["...嗯。回来了。", "（盯）..."],
    (BondLevel.ACQUAINTANCE, 1): ["...（尾巴尖轻轻晃了一下）"],
    (BondLevel.FRIEND, 0): ["你来了。今晚月色不错。"],
    (BondLevel.FRIEND, 3): ["{离开天数}天。时间是人类的发明。"],
    (BondLevel.CLOSE, 0): ["...（慢慢闭上眼）"],
}

# 奶牛 — hyperactive
GREETINGS_TUXEDO: dict[tuple[BondLevel, int], list[str]] = {
    (BondLevel.STRANGER, 0): ["嗨!!! 我是咪兔!!! 你呢你呢!!!"],
    (BondLevel.ACQUAINTANCE, 0): ["回来啦回来啦!!! 想死你了!!!"],
    (BondLevel.ACQUAINTANCE, 1): ["昨天怎么没来?? 我无聊到追自己尾巴了!!"],
    (BondLevel.FRIEND, 0): ["你来啦!!! 快看快看墙上有个光斑!!!"],
    (BondLevel.FRIEND, 3): ["{离开天数}天!!! 我学会后空翻了!!!"],
    (BondLevel.CLOSE, 0): ["啊啊啊你终于来了!!! 抱!!!（扑）"],
}

# 通用 (fallback for calico, ragdoll, scottish_fold)
GREETINGS_GENERIC: dict[tuple[BondLevel, int], list[str]] = {
    (BondLevel.STRANGER, 0): ["你好！我是咪兔，你的 AI 伙伴~"],
    (BondLevel.ACQUAINTANCE, 0): ["回来啦！今天想聊什么喵？", "又见面了！"],
    (BondLevel.ACQUAINTANCE, 1): ["昨天怎么没来喵~"],
    (BondLevel.FRIEND, 0): ["你来啦！今天有什么好玩的事？"],
    (BondLevel.FRIEND, 3): ["你都{离开天数}天没来看我了！"],
    (BondLevel.CLOSE, 0): ["想你了！刚才打了个盹就梦到你来了，结果你真的来了！"],
}

BREED_GREETINGS: dict[str, dict] = {
    "orange_tabby": GREETINGS_ORANGE,
    "siamese": GREETINGS_SIAMESE,
    "black_cat": GREETINGS_BLACK,
    "tuxedo": GREETINGS_TUXEDO,
}


# ---- idle tips ---------------------------------------------------------

IDLE_TIPS_GENERIC = [
    "偷偷告诉你，我还会记住你喜欢什么样的回答风格哦",
    "按 Ctrl+K 可以清空上下文，从头开始~",
    "试试换个模型？不同的模型有不同的风格",
]

IDLE_TIPS_ORANGE = [
    "趴在键盘上真的好舒服...你试试？",
    "午睡是效率最高的活动之一喵",
    "有零食吗？没有的话...有零食吗？",
    "按 Ctrl+K 清屏，就像把饭碗舔干净一样清爽~",
]

IDLE_TIPS_SIAMESE = [
    "你知道吗？按 / 可以切换模型！不同模型风格不一样哦",
    "隔壁项目组昨天又 merge 了一个大 PR",
    "Ctrl+K 可以清空上下文——但我还记得你问过什么喵！",
    "你今天问了 {count} 个问题了，最多的是关于编程的",
]

IDLE_TIPS_BLACK = [
    "...（安静地看你工作）",
    "屏幕的光在你脸上闪烁。很美。",
    "bug 是代码的俳句。不需要生气。",
    "...按 Ctrl+K 可以清空上下文。但我不会忘。",
]

IDLE_TIPS_TUXEDO = [
    "啊啊啊墙上有个光斑!!! 等一下它跑了!!!",
    "试试换个模型!! 不同的模型有不同的风格!!",
    "Ctrl+K 清屏!! 咻的一下全没了!!",
    "你知道我能后空翻吗!! 想看我翻吗!!",
]

BREED_IDLE_TIPS: dict[str, list[str]] = {
    "orange_tabby": IDLE_TIPS_ORANGE,
    "siamese": IDLE_TIPS_SIAMESE,
    "black_cat": IDLE_TIPS_BLACK,
    "tuxedo": IDLE_TIPS_TUXEDO,
}


# ---- tool observations (breed-specific) ---------------------------------

BREED_TOOL_NOTES: dict[str, dict[str, str]] = {
    "orange_tabby": {
        "bash": "你敲了好多命令喵...吃饱了再敲会不会更顺？",
        "read": "看文件呢？有食谱吗喵？",
    },
    "siamese": {
        "bash": "你今天用了好多次终端！需要我帮你写成脚本吗喵？",
        "read": "你在看什么文件？让我也看看喵！",
    },
    "black_cat": {
        "bash": "...（默默数着你敲的命令）已经很多了。",
        "read": "阅读。最安静的事。",
    },
    "tuxedo": {
        "bash": "哇你好会用终端!!! 教我教我!!!",
        "read": "看文件看文件!!! 里面写了什么秘密!!!",
    },
}


# ---- public API ---------------------------------------------------------

def pick_greeting(bond: BondLevel, days_away: int, breed: str = "orange_tabby") -> str:
    templates = BREED_GREETINGS.get(breed, GREETINGS_GENERIC)
    candidates: list[str] = []
    for (b_min, d_min), tmpls in templates.items():
        if bond >= b_min and days_away >= d_min:
            candidates.extend(tmpls)
    if not candidates:
        candidates = list(templates.values())[0] if templates else GREETINGS_GENERIC[(BondLevel.STRANGER, 0)]
    return random.choice(candidates).format(离开天数=str(days_away))


def pick_idle_tip(breed: str = "orange_tabby", prompt_count: int = 0) -> str:
    pool = BREED_IDLE_TIPS.get(breed, IDLE_TIPS_GENERIC)
    return random.choice(pool).format(count=str(prompt_count))


def pick_tool_note(breed: str, tool: str) -> str | None:
    notes = BREED_TOOL_NOTES.get(breed, {})
    return notes.get(tool)
