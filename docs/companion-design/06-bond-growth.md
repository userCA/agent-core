# 06 — 亲密度与成长系统

## 双轨模型

```
BOND (纵向) — 解锁内容深度，所有猫同轨
STYLE (横向) — 行为风格分化，由用户行为模式决定

        SOULMATE  ────────────────
       /  |  \  \               ↑
  CLOSE   |   \  \              │
   |      |    \  \       TECH_PARTNER
FRIEND    |     \  \    COMPANION
   |      |      \  \   MUSE
ACQUAINT  |       \  \  LIBRARIAN
   |      |        \  \  BALANCED
STRANGER  |         \  \
          └──────────┘──┘── → STYLE 分化
          (ACQUAINTANCE 时判定, 之后锁定)
```

## BOND 等级

| 等级 | Score 范围 | 解锁 | 估算达成时间 |
|------|-----------|------|------------|
| STRANGER | 0-9 | 基础 idle, 低概率气泡 | 首次 |
| ACQUAINTANCE | 10-49 | emoji 气泡, 名字回应, 小游戏(钓鱼) | ~3 天 |
| FRIEND | 50-199 | 慢眨眼, 蹭屏幕, 踩奶, 种猫草 | ~2 周 |
| CLOSE | 200-999 | 翻肚皮, 主动贴贴, 拼图 | ~1.5 月 |
| SOULMATE | 1000+ | 隐藏动画, 纪念气泡, 换装, 回忆功能 | ~4 月 |

### Score 计算公式

```python
score = (
    total_prompts   * 1   +   # 每次提问
    total_sessions  * 10  +   # 每次新 session
    days_span       * 2   +   # 从首次见面算起的天数
    pet_count       * 5   +   # 每次 /pet
    fish_fed        * 3   +   # 每次喂鱼
    tool_successes  * 0.5 +   # 每次成功的工具调用
    milestones_hit  * 15      # 每个解锁的里程碑
)
```

### Bond 事件得分

| 事件 | 得分 | 附注 |
|------|:--:|------|
| 一次 prompt | +1 | — |
| 新 session | +10 | 距上次 > 1h 才算新 session |
| 过一天 | +2 | UTC+8 零点自动加 |
| /pet | +5 | 30s CD |
| 喂一次鱼 | +3 | — |
| 钓到 rare+ 鱼 | +8 | — |
| 解锁里程碑 | +15 | 见 §10 |
| 连续 7 天登录 | +50 | 一次性，解锁后不重复 |
| 连续 30 天登录 | +200 | 一次性 |

## STYLE 分支

ACQUAINTANCE 等级到达时，基于过去所有交互统计判定 STYLE（此后锁定）。

### 五类 STYLE

| STYLE | 判定条件 | 解锁 |
|-------|---------|------|
| TECH_PARTNER | tool 调用占比 > 60% | 键盘趴帧, "别写了看我看我"气泡, 终端主题配饰 |
| COMPANION | 纯对话占比 > 70% | 翻肚皮频率×2, "再来聊一会"气泡, 围巾配饰 |
| MUSE | 长文本输入占比 > 50% (>200字/次) | 灵感气泡, "嗯？接着写呀"鼓励, 羽毛笔配饰 |
| LIBRARIAN | 搜索/查资料类 tool 占比 > 50% | 圆框眼镜配饰, "这本书我看过"气泡 |
| BALANCED | 以上均不满足 | 均衡内容池, 无偏向 |

### 判定算法

```python
def determine_style(observer):
    total = observer.prompt_count + observer.tool_count
    if total < 20:
        return BALANCED  # 交互太少，不判定

    tool_ratio = observer.tool_count / total
    chat_ratio = observer.prompt_count / total
    long_input_ratio = observer.long_prompts / max(observer.prompt_count, 1)
    search_ratio = observer.search_tools / max(observer.tool_count, 1)

    if tool_ratio > 0.6:
        return TECH_PARTNER
    if chat_ratio > 0.7:
        return COMPANION
    if long_input_ratio > 0.5:
        return MUSE
    if search_ratio > 0.5:
        return LIBRARIAN
    return BALANCED
```

### STYLE 气泡内容差异

| STYLE | 鼓励气泡 | 成就气泡 |
|-------|---------|---------|
| TECH_PARTNER | "又一个 bug 被你干掉了！" | "你今天写了 500 行代码！" |
| COMPANION | "和你聊天好开心喵~" | "我们的第 100 次对话！" |
| MUSE | "这段写得真好..." | "你已经写了 10000 字了！" |
| LIBRARIAN | "这条信息很有用呢" | "查阅了 50 份资料！" |
| BALANCED | "今天也是充实的一天喵" | "又一个 milestone！" |

## 冷落/衰退系统

### 设计原则

- 咪兔不会"变心"——bond level 永不降级
- 但离开太久会有情绪反应——让用户感到"它在想我"
- 回归后快速恢复到正常状态——不给愧疚感

### 离开天数→状态表

| 离开天数 | 咪兔状态 | 首次回归反应 | 恢复方式 |
|---------|---------|------------|---------|
| 1 | 正常 | "早啊！" | 无 |
| 2-3 | 轻微想念 | "两天没见了...还好吗？" | 1 次对话即恢复 |
| 4-6 | 闹别扭 | "（背对着你）...知道回来了？" | /pet 或 3 次对话 |
| 7-13 | 冷战 | "哼。（但尾巴尖偷偷看你）" | 连续 2 天登录 |
| 14-30 | 伤心 | "我以为你不要我了..." | 连续 3 天登录 + 特别气泡 |
| 30+ | 重逢 | "你是...？啊！是你！" (假装不认识→认出) | 连续 5 天登录，播放重逢动画 |

### 衰退数值

```python
def compute_decay(days_away, bond_score):
    if days_away < 1:     return 0       # 没事
    if days_away < 3:     return 0       # 轻微想念但不扣分
    if days_away < 7:     return 0       # 闹别扭但不扣分
    if days_away < 14:    return -20     # 轻微衰减
    if days_away < 30:    return -50     # 中等衰减
    return -100                           # 大幅衰减 
    # bond 不会降级, 但 score 衰减意味着升级需要更多时间
```

### 恢复加速

回归后 7 天内 score 获得 ×1.5 倍率——"补偿机制"让用户快速回到之前的亲密感。

## SOULMATE 后内容

达到 SOULMATE (score ≥ 1000) 后解锁:

| 内容 | 说明 |
|------|------|
| 老友模式 | 气泡模板更随意自然，去掉正式模板限制 |
| 回忆功能 | `buddy.memories` 面板 → 展示 milestone 时间线 |
| 星光项圈 | SOULMATE 专属配饰，金色粒子 |
| 每周惊喜 | 每周一自动推送 "上周互动亮点" 气泡 |
| 自定义触发 | 可教咪兔 1-2 个触发词→指定反应 (如 "加油"→撒花) |
| 双倍记忆 | 伴侣记忆条目上限 200→400 |
| 名片 | 可分享的 "我和咪兔" 统计数据卡 |

### SOULMATE 维持

到达 SOULMATE 后，每天 score += 1 (自动)，保持 level 不需要持续活跃。
连续 30 天不登录不会降级，只是冷落反应更强烈。
