# 11 — 命名系统

## 命名时机

咪兔首次 hatch 时（用户首次登录/首次打开 companion 面板），由 LLM 生成 `name` 和
`personality` 摘要。

这是**唯一的 LLM 调用**——其余所有米兔行为均为规则+模板驱动。

## LLM Prompt

```python
MITU_NAMING_PROMPT = """你是一只住在网页 / App 里的终端风格 {breed_cn} 猫精灵的"灵魂生成器"。

这只猫的基因特征是:
- 品种: {breed_cn}
- 稀有度: {rarity_cn} ({rarity}/5星)
- 眼睛: {eye_cn}
- 耳朵: {ear_cn}
- 配饰: {accent_cn}
- 性格数值: 好奇{cur} 社交{soc} 亲昵{aff} 贪玩{play} 幸运{luck}
- 怪癖: {quirk_cn}
- 是否闪亮: {shiny}

请为这只猫:
1. 起一个中文名 (2-4字, 食物/自然/可爱系, 不能和人名重名)
2. 写一句 20 字以内的人格描述 (温暖、有趣、体现性格)

输出 JSON:
{{"name": "...", "personality": "..."}}

只输出 JSON, 不要解释。"""
```

## 品种名池（LLM 参考/降级 fallback）

当 LLM 不可用时，从以下名池降级随机选择：

| 品种 | 名池 |
|------|------|
| 橘猫 | 橘子, 大橘, 橘胖, 橘糖, 麦芽, 吐司, 蛋黄, 南瓜, 芝士, 布丁 |
| 奶牛 | 芝麻, 墨水, 奥利奥, 斑斑, 企鹅, 奶牛, 围棋, 熊猫, 墨点, 珍珠 |
| 三花 | 琥珀, 麻薯, 咖喱, 麻衣, 花卷, 豆花, 拿铁, 太妃, 栗子, 玛瑙 |
| 暹罗 | 芝麻糊, 小米, 可可, 摩卡, 咖啡, 奶茶, 乌龙, 可可豆, 松露, 黑豆 |
| 黑猫 | 露娜, 影子, 墨墨, 玄月, 芝麻球, 黑糖, 墨鱼, 曜, 暗夜, 星尘 |
| 布偶 | 棉花, 糯米, 汤圆, 雪球, 云朵, 奶油, 年糕, 冰激凌, 奶糖, 白巧 |
| 折耳 | 团子, 馒头, 豆包, 丸子, 麻圆, 汤包, 软糖, 果冻, 泡芙, 糯米糍 |

## 命名约束

- 不与用户配置中的 `name` / `username` 重名
- 不与已存在的其他咪兔名重复（同一服务器范围内，概率极低）
- 不包含敏感词（用 `_SKIP_WORDS` 黑名单过滤）
- 闪烁 × 传说 → 名字带 `✦` 后缀（由前端渲染，不存进 soul）

## Soul 存储

```python
@dataclass
class CompanionSoul:
    name: str              # "橘子糖"
    personality: str       # "一只佛系贪吃的橘猫，最大的爱好是睡觉和等零食"
    hatched_at: float      # unix timestamp of first hatch
    
# 存储在用户配置中:
# config.companion = StoredCompanion(name="橘子糖", personality="...", hatched_at=...)
# Bones 每次从 hash 重算，Soul 持久化
```
