"""Companion naming — LLM-generated name + personality at hatch time.

This is the ONLY LLM call in the companion system. Uses agent_core's
ModelProvider + AuthSource so naming reuses the same provider
configuration as the rest of the system. Falls back to a breed-specific
name pool if no provider is configured.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass

from agent_core.companion.bones import CompanionBones
from agent_core.companion.species import BREED_NAMES
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.base import ModelProvider

logger = logging.getLogger(__name__)

# breed → [name fallbacks]
NAME_POOL: dict[str, list[str]] = {
    "orange_tabby": ["橘子", "大橘", "橘胖", "橘糖", "麦芽", "吐司", "蛋黄", "南瓜", "芝士", "布丁"],
    "tuxedo": ["芝麻", "墨水", "奥利奥", "斑斑", "企鹅", "围棋", "熊猫", "墨点", "珍珠"],
    "calico": ["琥珀", "麻薯", "咖喱", "麻衣", "花卷", "豆花", "拿铁", "太妃", "栗子", "玛瑙"],
    "siamese": ["芝麻糊", "小米", "可可", "摩卡", "咖啡", "奶茶", "乌龙", "可可豆", "松露", "黑豆"],
    "black_cat": ["露娜", "影子", "墨墨", "玄月", "芝麻球", "黑糖", "墨鱼", "曜", "暗夜", "星尘"],
    "ragdoll": ["棉花", "糯米", "汤圆", "雪球", "云朵", "奶油", "年糕", "冰激凌", "奶糖", "白巧"],
    "scottish_fold": ["团子", "馒头", "豆包", "丸子", "麻圆", "汤包", "软糖", "果冻", "泡芙", "糯米糍"],
}

QUIRK_CN: dict[str, str] = {
    "night_owl": "夜猫子", "picky_eater": "挑食怪", "chatterbox": "话痨",
    "shy": "社恐", "collector": "收集癖", "hyperactive": "多动症",
    "sleepyhead": "睡神", "glass_heart": "玻璃心", "foodie": "贪吃",
    "clean_freak": "洁癖", "tsundere_extreme": "究极傲娇",
    "philosopher": "哲学家", "comedian": "搞笑猫",
}

EYE_CN: dict[str, str] = {"·": "眯眯眼", "✦": "星光眼", "◉": "大圆眼", "o": "圆眼", "♥": "爱心眼", "☆": "星眼"}

RARITY_CN: dict[str, str] = {
    "common": "普通", "uncommon": "稀有", "rare": "珍稀", "epic": "史诗", "legendary": "传说",
}


@dataclass
class CompanionSoul:
    name: str
    personality: str
    hatched_at: float


def build_naming_prompt(bones: CompanionBones) -> str:
    breed_cn = BREED_NAMES.get(bones.breed, bones.breed)
    rarity_cn = RARITY_CN.get(bones.rarity, bones.rarity)
    eye_cn = EYE_CN.get(bones.eye, bones.eye)
    quirk_cn = QUIRK_CN.get(bones.quirk, bones.quirk)
    shiny_text = "是，全身闪光粒子" if bones.shiny else "否"

    stats = bones.stats
    return f"""你是一只住在终端里的 {breed_cn} 猫精灵的"灵魂生成器"。

这只猫的基因特征是:
- 品种: {breed_cn}
- 稀有度: {rarity_cn} ({bones.rarity}/5星)
- 眼睛: {eye_cn}
- 配饰: {bones.accent}
- 帽子: {bones.hat}
- 性格数值: 好奇{stats.get('CURIOSITY',50)} 社交{stats.get('SOCIAL',50)} 亲昵{stats.get('AFFECTION',50)} 贪玩{stats.get('PLAYFUL',50)} 幸运{stats.get('LUCK',50)}
- 怪癖: {quirk_cn}
- 是否闪亮: {shiny_text}

请为这只猫:
1. 起一个中文名 (2-4字, 食物/自然/可爱系, 不能和人名重名)
2. 写一句 25 字以内的人格描述 (温暖、有趣、体现性格和怪癖)

输出 JSON:
{{"name": "...", "personality": "..."}}

只输出 JSON, 不要解释。"""


# Module-level provider config — injected once at server startup.
# The companion module never imports provider internals directly.
_naming_provider: ModelProvider | None = None
_naming_auth: ProviderAuth | None = None
_naming_model_id: str = "gpt-4.1-mini"


def configure_naming(
    provider: ModelProvider,
    auth: ProviderAuth,
    model_id: str = "gpt-4.1-mini",
) -> None:
    """Inject the LLM provider for companion naming. Called once at startup."""
    global _naming_provider, _naming_auth, _naming_model_id
    _naming_provider = provider
    _naming_auth = auth
    _naming_model_id = model_id


async def hatch_name(bones: CompanionBones) -> CompanionSoul:
    """Generate name + personality via the injected provider.

    Falls back to breed-specific name pool if no provider was configured
    or the LLM call fails.
    """
    import asyncio
    import time as _time

    if _naming_provider is None or _naming_auth is None:
        logger.info("Naming provider not configured, using name pool fallback")
        return _fallback_soul(bones)

    prompt = build_naming_prompt(bones)

    try:
        # Find a compatible model
        models = _naming_provider.list_models()
        model = next((m for m in models if m.id == _naming_model_id), None)
        if model is None:
            model = models[0] if models else None
        if model is None:
            return _fallback_soul(bones)

        messages: list[dict[str, object]] = [
            {"role": "user", "content": prompt},
        ]

        text_parts: list[str] = []
        async for evt in _naming_provider.stream(
            model=model,
            messages=messages,
            tools=[],
            system_prompt="你是一个起名助手。只输出JSON。",
            temperature=0.9,
            max_tokens=100,
            signal=None,
            auth=_naming_auth,
        ):
            if evt.type == "text_delta":
                text_parts.append(evt.text)

        text = "".join(text_parts).strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0].replace("json", "").strip()

        data = json.loads(text)
        return CompanionSoul(
            name=data.get("name", _random_name(bones.breed)),
            personality=data.get("personality", f"一只{BREED_NAMES.get(bones.breed, '猫')}"),
            hatched_at=_time.time(),
        )
    except Exception as exc:
        logger.warning("LLM naming failed: %s, using fallback", exc)
        return _fallback_soul(bones)


def _fallback_soul(bones: CompanionBones) -> CompanionSoul:
    import time as _time
    return CompanionSoul(
        name=_random_name(bones.breed),
        personality=f"一只性格独特的{BREED_NAMES.get(bones.breed, '猫')}",
        hatched_at=_time.time(),
    )


def _random_name(breed: str) -> str:
    pool = NAME_POOL.get(breed, ["咪咪", "小喵"])
    return random.choice(pool)
