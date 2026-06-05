# 08 — 情绪状态机

## 状态节点

```
                    ┌──────────┐
         pet/成功 ──→│ EXCITED  │←── combo完成
         / 惊喜     │ (峰值)   │
        /           └────┬─────┘
       /                 │ 自然衰减 (快)
      ▼                  ▼
┌──────────┐  pet/正面  ┌──────────┐  idle 30s  ┌──────────┐
│  HAPPY   │←──────────│ NEUTRAL  │──────────→│  SLEEPY  │
│ (愉悦)   │──────────→│ (默认)   │←──────────│ (困倦)   │
└────┬─────┘ 自然衰减   └───┬──┬──┘  长时间无交互 └──────────┘
     │        (慢)          │  │
     │                      │  │ 错误/失败/脏话
     │          tool失败 ┌──┘  └──────────┐
     │          ┌───────┘                 │
     ▼          ▼                         ▼
┌──────────┐ 叠加: 连续失败 ──→  ┌──────────┐
│ ANNOYED  │                      │ WORRIED  │
│ (不满)   │                      │ (担心)   │
└────┬─────┘                      └────┬─────┘
     │ pet/恢复                        │ pet/安抚
     └──────────────┬──────────────────┘
                    ▼
              ┌──────────┐
              │ NEUTRAL  │
              └──────────┘
```

## 状态定义

| 状态 | 动画默认 | 气泡概率 | 眼睛覆盖 | 描述 |
|------|---------|:--:|---------|------|
| NEUTRAL | REST | 0.05 | 默认 eye | 正常工作/休息 |
| HAPPY | HAPPY | 0.10 | 默认+偶尔 `♥` | 愉悦中 |
| EXCITED | HAPPY(加速) | 0.15 | `✦` 或 `♥` | 峰值情绪, 持续时间短 |
| SLEEPY | SLEEPING | 0.02 | `-` | 困了, 动作变慢 |
| WORRIED | CONCERNED | 0.08 | `◉` | 担心用户/错误 |
| ANNOYED | CONCERNED | 0.12 | `▼` | 不满, 但很快就消气 |

## 转换规则表

行=当前状态, 列=输入事件, 值=目标状态。

| curr ↓ \ event → | pet | tool成功 | tool失败 | 用户脏话 | idle 30s | idle 5min | 连续3失败 |
|-------------------|-----|---------|---------|---------|---------|----------|----------|
| NEUTRAL | HAPPY | NEUTRAL | WORRIED | ANNOYED | SLEEPY | SLEEPY | WORRIED |
| HAPPY | EXCITED | HAPPY | NEUTRAL | ANNOYED | NEUTRAL | SLEEPY | WORRIED |
| EXCITED | EXCITED | HAPPY | NEUTRAL | ANNOYED | HAPPY | SLEEPY | NEUTRAL |
| SLEEPY | HAPPY | NEUTRAL | WORRIED | NEUTRAL | SLEEPY | SLEEPY | WORRIED |
| WORRIED | HAPPY | HAPPY | WORRIED | ANNOYED | NEUTRAL | SLEEPY | ANNOYED |
| ANNOYED | NEUTRAL | NEUTRAL | ANNOYED | ANNOYED | NEUTRAL | SLEEPY | ANNOYED |

## 衰减率

无事件时，情绪自然向 NEUTRAL 衰减：

| 从 | 衰减到 NEUTRAL 耗时 | tick 变化/步 |
|----|-------------------|-------------|
| EXCITED | 15s (30 tick) | mood -= 3.3/tick |
| HAPPY | 60s (120 tick) | mood -= 0.8/tick |
| WORRIED | 90s (180 tick) | mood -= 0.55/tick |
| ANNOYED | 45s (90 tick) | mood -= 1.1/tick |
| SLEEPY | 不自动衰减 (需事件唤醒) | — |

## 情绪叠加

同一事件连续触发时，情绪叠加但不线性：

```
第1次失败: NEUTRAL → WORRIED (mood = 30)
第2次失败: WORRIED → WORRIED (mood = 15, 加深)
第3次失败: WORRIED → ANNOYED (mood = 0, 生气了!)
第4次失败: ANNOYED → ANNOYED (mood = 0, 持续生气)
第5次失败: ANNOYED → ANNOYED + 触发 "你要不要休息一下喵" 气泡
```

## 情绪→表情映射

```python
EMOTION_FACE_OVERRIDE = {
    NEUTRAL:  None,          # 使用 bones.eye
    HAPPY:    "♥",          # 强制爱心眼
    EXCITED:  "✦",          # 星光眼
    SLEEPY:   "-",          # 闭眼
    WORRIED:  "◉",          # 大眼紧张
    ANNOYED:  "▼",          # 三角眼
}
```

## 实现接口

```python
class EmotionFSM:
    def __init__(self, bones: CompanionBones):
        self.state = "NEUTRAL"
        self.mood = 50.0          # 0-100, 0=最低, 100=最好, 50=中性
        self.decay_counter = 0
        self.streak = defaultdict(int)  # 同一事件连续计数
    
    def process(self, event: AgentEvent) -> list[Reaction]:
        transition = TRANSITION_TABLE[self.state][event.type]
        if transition:
            self.state = transition
            old_mood = self.mood
            self.mood = self._apply_mood_change(event)
            return self._generate_reactions(old_mood)
        return []
    
    def tick(self) -> list[Reaction]:
        self.mood = self._decay(self.mood)
        if self._should_transition():
            return self._generate_reactions()
        return []
```
