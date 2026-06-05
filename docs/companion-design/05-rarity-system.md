# 05 — 稀有度系统

## 五级稀有度

```python
RARITY_WEIGHTS = {
    "common":    60,   # 60% — 普通咪兔
    "uncommon":  25,   # 25% — 稀有
    "rare":      10,   # 10% — 珍稀
    "epic":       4,   #  4% — 史诗
    "legendary":  1,   #  1% — 传说
}
```

### 权重算法

```python
def roll_rarity(rng):
    total = sum(RARITY_WEIGHTS.values())  # 100
    roll = rng() * total
    for rarity in RARITIES:
        roll -= RARITY_WEIGHTS[rarity]
        if roll < 0:
            return rarity
    return "common"
```

### 颜色映射

| 稀有度 | 颜色 | hex | 前端使用 |
|--------|------|-----|---------|
| common | 灰色 | `#8e8e93` | `Theme.inactive` |
| uncommon | 绿色 | `#30d158` | `Theme.success` |
| rare | 蓝色 | `#409cff` | `Theme.permission` |
| epic | 紫色 | `#bf5af2` | `Theme.autoAccept` |
| legendary | 金色 | `#ff9f0a` | `Theme.warning` |

## 稀有度→内容解锁矩阵

这是核心驱动表：**稀有度决定了咪兔能看到/解锁什么内容**。

| 内容 | common | uncommon | rare | epic | legendary |
|------|:--:|:--:|:--:|:--:|:--:|
| **眼睛池** | `·` `o` `-` | +`◉` | +`✦` | +`♥` | +`▼` |
| **帽子池** | none | 普通帽 | 大部分 | 全部 | 稀有帽 |
| **配饰池** | none | 普通 3 个 | 大部分 | 全部 | 传说配饰 |
| **动画帧数** | 3 | 3 | 4 | 5 | 6 |
| **特殊帧** | — | — | +1 个品种帧 | +2 个品种帧 | +3 个(含 1 独家) |
| **闪亮概率** | 1% | 1% | 2% | 5% | 100% |
| **名字颜色** | 灰 | 绿 | 蓝 | 紫 | 金 |
| **粒子特效** | — | — | — | `＊` | `＊ ✦ ＊` |
| **气泡 emoji** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **传说配饰** | — | — | — | — | 星光项圈 |
| **独家气泡模板** | 5 | 8 | 12 | 18 | 25+5 独家 |
| **解锁 breed** | 橘猫/奶牛/暹罗/黑猫 | +三花 | +布偶 | +折耳 | 全部 |
| **钓鱼稀有加成** | 0% | +5% | +10% | +20% | +50% |

### 稀有度过滤算法

```python
def filter_pool(pool, rarity):
    """根据稀有度过滤可选内容池"""
    thresholds = {
        "common":    0.0,   # 仅最低档
        "uncommon":  0.3,   # 前 30%
        "rare":      0.6,   # 前 60%
        "epic":      0.85,  # 前 85%
        "legendary": 1.0,   # 全部
    }
    cutoff = int(len(pool) * thresholds[rarity])
    return pool[:max(1, cutoff)]
```

## 闪亮 (Shiny)

### 判定

```python
# roll_companion() 中:
shiny = rng() < 0.01  # 1% 基础概率
if rarity == "legendary":
    shiny = True  # 传说级强制闪亮
if LUCK > 90:
    shiny_prob += 0.02  # 高幸运 +2%
```

### 表现

| 特性 | 普通 | 闪亮 |
|------|------|------|
| 名字渲染 | `rarity_color` | gold（所有稀有度均为金色名） |
| 眼睛颜色 | 默认 | 反色/高亮 |
| 粒子 | 无 | 帧间 5% 概率出现 `＊` 字符 |
| 光晕 | 无 | 精灵外框 1 列轻微变色 |
| 特殊标记 | — | 名字后加 `✦` |

### 闪亮 × 传说 (Shiny Legendary)

概率: 0.01% (1/10000 用户)

特殊表现:
- 名字: 彩虹色渐变（七色循环）
- 粒子: `＊ ✦ ＊` 三粒子同时
- 独家动画帧: "彩虹翻滚"——6 种眼睛字符循环
- 气泡: 自动带 `✨` emoji 后缀
- 名字在排行榜/展示中显示为 "彩虹传说"

## 不可变约束

与 buddy 系统一致：数组 **append-only**，永不删除/插入/调序。

```python
# species.py 规则:
# ✅ EYES.append("★")     — 追加
# ❌ EYES.insert(2, "★")  — 插入，破坏所有已有用户的 index
# ❌ EYES[3] = "★"        — 调换，破坏
# ❌ del EYES[2]          — 删除，破坏
# 唯一例外: 用 "_deprecated_" 占位替换废弃项
```

如果需要做大规模重构 → 增加 SALT 版本号（`mitu-2026-companion-v2`），
旧 SALT 的用户保持不变。
