# 04 — 性格系统

## 三维性格模型

每只咪兔在三条轴上有一个锚点（0-100，由 `roll_companion()` 确定性生成）：

```
              CURIOSITY (好奇→探索倾向)
                   ↑
                   |
         SOCIAL ←--+--→ 话唠程度
    (安静→社交倾向)  |
                   ↓
              AFFECTION
           (傲娇→粘人程度)
```

| 轴 | 低值 (0-33) | 中值 (34-66) | 高值 (67-100) |
|----|-----------|------------|------------|
| CURIOSITY | 安静、不主动探索 | 正常好奇 | 什么都想碰、频繁戳屏幕 |
| SOCIAL | 沉默、气泡少 | 正常社交 | 话唠、气泡频繁、字数多 |
| AFFECTION | 傲娇、升温慢 | 正常亲昵 | 粘人、快速升温、主动贴 |

### 行为影响公式

```
bubble_trigger_chance_base = SOCIAL * 0.006 + mood * 0.003
   范围: 0.0 ~ 0.9 (每 tick 检查概率)

bubble_text_length = int(8 + SOCIAL * 0.3 + bond_level * 5)
   范围: 8 ~ 63 字符

affection_gain_multiplier = AFFECTION * 0.015 + 0.15
   范围: 0.15x ~ 1.65x (亲密度事件得分乘数)

explore_animation_weight = CURIOSITY * 0.01
   范围: 0.0 ~ 1.0 (空闲动作池中"探索"类占比)

pet_response_delay = max(100, 3000 - SOCIAL * 30)  # ms
   沉默的猫 /pet 反应慢，话唠猫秒回
```

### 性格→说话风格

| 性格组合 | 常温语气 | 开心时 | 担心时 |
|---------|---------|--------|--------|
| HIGH AFFECTION + HIGH SOCIAL | "你来啦！喵一直等你哦~" | "哇！！最喜欢了！！" | "呜呜别走..." |
| LOW AFFECTION + LOW SOCIAL | "...嗯。" | "还不错。" | "（盯）...没事。" |
| HIGH CURIOSITY + HIGH SOCIAL | "这是什么！那个呢！" | "太好玩了喵！" | "不会坏掉吧..." |
| HIGH AFFECTION + LOW SOCIAL | （蹭过来，不说话） | （翻肚皮，呼噜） | （轻轻碰手） |
| LOW AFFECTION + HIGH CURIOSITY | "哼，只是好奇才问的" | "这次算你厉害..." | "你不会搞砸吧？" |

## 怪癖系统 (Quirk)

每个咪兔 roll 1 个怪癖（确定性，来自 `bones.quirk`）。怪癖**修饰**性格和行为的某些数值。

### 怪癖表

| 名 | 描述 | 效果 | 品种加权 |
|----|------|------|---------|
| night_owl | 夜猫子 | energy_night *= 1.5, energy_day *= 0.5 | 黑猫×2 |
| picky_eater | 挑食怪 | 喂食效果随机 0.5x-2x (uniform) | 暹罗×2 |
| chatterbox | 话痨 | bubble_prob *= 2, bubble_len_max //= 2 | 暹罗×3 |
| shy | 社恐 | bubble_prob *= 0.2 for bond≤1, 正常 for bond≥2 | 折耳×3, 黑猫×2 |
| collector | 收集癖 | 每次 tool_end: 10% 概率存 tool_name, 100 条时解锁成就 | — |
| hyperactive | 多动症 | idle 序列速度 *= 2, 每 3 tick 换姿势 | 奶牛×2 |
| sleepyhead | 睡神 | 空闲 2min 即 SLEEPING, awake_delay *= 3 | 橘猫×3 |
| glass_heart | 玻璃心 | tool_fail → mood -= 30 (正常 -10) | 布偶×2 |
| foodie | 贪吃 | 喂食效果 *= 1.5, 主动索食概率 += 15% | 橘猫×4 |
| clean_freak | 洁癖 | 遇 error/bug → 触发 WASH_FACE 动作 | 三花×2 |
| tsundere_extreme | 究极傲娇 | AFFECTION 显示值 *= 0.5 (实际不变) | 三花×3 |
| philosopher | 哲学家 | 夜间气泡变得深沉/莫名其妙 | 黑猫×3 |
| comedian | 搞笑猫 | 气泡 30% 概率替换为猫笑话/双关语 | 奶牛×3 |

### Quirk 生成算法

```python
def roll_quirk(rng, breed):
    weighted = []
    for q in QUIRKS:
        weight = q.base_weight * breed.bonus.get(q.name, 1.0)
        weighted.extend([q] * int(weight * 10))
    return pick(rng, weighted)
```

## 属性↔行为映射速查

| 属性 | 影响的目标 | 公式 |
|------|-----------|------|
| CURIOSITY | 探索动画频率 | `idle_explore_ratio = cur / 100` |
| CURIOSITY | 新功能气泡 | `prob = (cur - 30) / 70` |
| SOCIAL | 气泡基础概率 | `prob_per_tick = cur * 0.006` |
| SOCIAL | 气泡字数上限 | `max_len = 8 + cur * 0.3` |
| AFFECTION | 亲密度增速 | `multiplier = cur * 0.015 + 0.15` |
| AFFECTION | attention 衰减率 | `decay = 1.0 - cur * 0.005` |
| PLAYFUL | 空闲动画速度 | `speed = cur > 70 ? 0.8 : cur < 30 ? 1.3 : 1.0` |
| PLAYFUL | 玩类动作占比 | `play_ratio = cur / 100` |
| LUCK | 钓鱼稀有率 | `rare_bonus = cur / 200` (最大 +50%) |
| LUCK | shiny 概率 | `multiplier = 1.0 + cur / 200` |

## 属性自身不变但表现可变

关键设计: `bones.stats` 是静态基因，只决定**变化速率**。动态状态
(mood/energy/attention) 是每 tick 变化的，其变化速率受 stats 影响。

```
mood 恢复速度 = base + AFFECTION * 0.3 + bond * 2
energy 消耗速度 = base - CURIOSITY * 0.2 (高好奇 → 精力消耗快, 但恢复也快)
attention 衰减 = base - AFFECTION * 0.4 (高亲昵 → 注意力衰退慢)
```
