# 07 — 互动系统

## 用户主动行为

| 行为 | 触发方式 | 反应 | CD | Combo 窗口 |
|------|---------|------|:--:|:--:|
| /pet | 命令 | 爱心冒泡 + LOVE 帧 | 30s | 5s (→ 连摸) |
| /buddy | 命令 | 打开伴侣面板 | — | — |
| 呼唤名字 | 输入 "咪兔" | EAR_PERK + HEAD_TILT | — | — |
| 快速连续输入 | 1s 内 >5 键 | HEAD_TILT + 惊讶眨眼 | 10s | — |
| 空闲 > 5min | 不操作 | SLEEPING | — | — |
| Ctrl+K 清屏 | 快捷键 | "诶？！" 气泡 | — | — |
| 粘贴 > 500 字 | 粘贴事件 | "好多字！" 气泡 | 5min | — |
| 输入 "喵" / "喵喵" | 文本匹配 | "喵喵喵？" 回应 | 30s | 3 次 → "喵合唱" |

## 咪兔主动行为

| 触发条件 | 动作 | 气泡示例 |
|---------|------|---------|
| 连续工作 > 1h | CONCERNED | "工作一小时了...喝水吧喵" |
| 连续问同类问题 ≥4 次 | HEAD_TILT | "今天第 4 次问天气了，要我记住吗？" |
| 新功能首次使用 | EAR_PERK + 探索 | "哦！新功能！" |
| 用户说 "谢谢" | HAPPY + slow_blink | "不用谢喵~" |
| 脏话/生气 | CONCERNED + 飞机耳 | "冷静冷静...深呼吸喵" |
| "再见"/"晚安" | 不舍 | "晚安！咪兔会在梦里等你的~" |
| 首次生成代码 | 眼睛发亮 | "哇！这是你写的吗？" |
| 编译/测试失败 | CONCERNED + 安慰 | "没关系！bug 谁都会遇到的" |
| 月度纪念日 | EXCITED + 惊喜 | "认识整整一个月了喵！🎉" |
| 午夜晚于 23:00 | SLEEPY | "都这个点了...眼睛睁不开了...zzZ" |
| STREAK 连续 7 天 | 庆祝动画 | "连续 7 天！你太勤奋了！" |

## 连锁互动 (InteractionChain)

### 数据结构

```python
@dataclass
class Step:
    trigger: str           # 触发类型: "pet" | "tool_start" | "tool_end" | ...
    within_ms: int = 0     # 上一步后多久内有效 (0 = 任意)
    required_state: str = ""  # 需要的前置情绪 (可选)
    
@dataclass  
class InteractionChain:
    name: str
    steps: list[Step]
    combo_window_ms: int = 10000   # 整条链的有效窗口
    on_step: list[str] = []        # 每步触发的 reaction
    on_complete: str               # 链完成时的特殊 reaction ID
    on_timeout: str = ""           # 窗口过期时的 reaction
    score_bonus: int = 0           # 完成后 bond score 奖励
```

### 内置 Chain 定义

```python
CHAINS = [
    InteractionChain(
        name="double_pet",
        steps=[
            Step("pet"), 
            Step("pet", within_ms=5000),
        ],
        combo_window_ms=8000,
        on_step=["HAPPY", "PURR"],
        on_complete="HEART_BURST",
        score_bonus=10,
    ),
    
    InteractionChain(
        name="triple_pet",
        steps=[
            Step("pet"),
            Step("pet", within_ms=4000),
            Step("pet", within_ms=3000),
        ],
        combo_window_ms=10000,
        on_step=["HAPPY", "PURR", "KNEAD"],
        on_complete="LOVE_OVERLOAD",  # 特殊帧 + 大量爱心
        score_bonus=25,
    ),
    
    InteractionChain(
        name="coding_streak",
        steps=[
            Step("tool_start"),
            Step("tool_end", within_ms=30000),
            Step("tool_start", within_ms=60000),
            Step("tool_end", within_ms=30000),
        ],
        combo_window_ms=120000,
        on_step=["FOCUSED", "FOCUSED", "IMPRESSED", "PROUD"],
        on_complete="PROUD_BOUNCE",
        score_bonus=15,
    ),
    
    InteractionChain(
        name="night_owl_combo",
        steps=[
            Step("prompt",  required_state="late_night"),
            Step("prompt",  within_ms=60000),
        ],
        combo_window_ms=120000,
        on_step=["SLEEPY", "SLEEPY_RESIGNED"],
        on_complete="NIGHT_BUDDY",
        score_bonus=20,
    ),
    
    InteractionChain(
        name="error_recovery",
        steps=[
            Step("tool_end", required_state="error"),
            Step("tool_start", within_ms=30000),
            Step("tool_end", within_ms=30000),
        ],
        combo_window_ms=60000,
        on_step=["CONCERNED", "FOCUSED", "RELIEVED"],
        on_complete="COMEBACK_CHEER",
        score_bonus=20,
    ),
]
```

### Chain 检测器

```python
class InteractionChainDetector:
    def __init__(self):
        self._active: dict[str, ChainState] = {}
    
    def feed(self, event) -> list[Reaction]:
        reactions = []
        expired = []
        for name, state in self._active.items():
            if time_ms() - state.started_at > state.chain.combo_window_ms:
                expired.append(name)
                if state.chain.on_timeout:
                    reactions.append(Reaction(state.chain.on_timeout))
                continue
            next_step = state.chain.steps[state.step_index]
            if self._matches(event, next_step, state):
                state.step_index += 1
                if state.step_index < len(state.chain.steps):
                    reactions.append(Reaction(state.chain.on_step[state.step_index - 1]))
                else:
                    reactions.append(Reaction(state.chain.on_complete))
                    expired.append(name)
        for name in expired:
            del self._active[name]
        # Start new chains
        for chain in CHAINS:
            if self._matches(event, chain.steps[0], None):
                self._active[chain.name] = ChainState(chain=chain, step_index=1, started_at=time_ms())
                if chain.on_step:
                    reactions.append(Reaction(chain.on_step[0]))
        return reactions
```

## 隐藏互动

不写文档，让用户自己发现：

| # | 触发方式 | 反应 |
|---|---------|------|
| 1 | 输入 "喵" 3 次 | 咪兔 "喵喵喵？" (合唱模式) |
| 2 | 00:00-00:05 发消息 | 咪兔戴睡帽出现 |
| 3 | 只打空格然后删掉，重复 5 次 | "你干嘛呢..." 歪头 |
| 4 | 长按某键 (检测到重复字符 > 20) | 咪兔趴在键盘上 "wwwwwwwww" |
| 5 | 连续 10 次 tool 全部成功 | 撒花 "完美通关！" |
| 6 | 输入 "bug" 10 次 | 咪兔开始追屏幕上的 "bug" |
| 7 | /pet 在 3:00-3:05 AM | "你这么晚还不睡...好，陪你" |
| 8 | 一行只输入 "..." | 咪兔也 "..." (复制你的省略号) |
| 9 | 输入框 100 个字符不含空格 | "一口气打这么多你肺活量真好" |
| 10 | 选择所有文本后删除 | "全没了！你故意的吗！" |

## 互动冷却分组

避免同一类型互动刷屏:

```
Group A (工作): tool_start, tool_end, error → 共享 5s CD
Group B (情感): pet, 呼唤名字, 谢谢 → 共享 30s CD  
Group C (观察): 连续同类问题, 长时间工作 → 共享 60s CD
Group D (闲聊): 喵, ... → 无 CD (娱乐性质)
```
