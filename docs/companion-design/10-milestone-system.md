# 10 — 里程碑系统

## 概述

里程碑是咪兔"记得我们之间发生过什么"的基础。每个 milestone 是一次性事件——触发后
写入伴侣记忆，不再重复触发（除了年度纪念）。

## 触发条件清单

### 时间类

| ID | 条件 | 叙事模板 | 气泡 |
|----|------|---------|------|
| first_meeting | 首次对话 | "我们第一次见面" | — |
| day_7 | 认识第 7 天 | "一周纪念" | "认识一周了喵！感觉像认识了很久" |
| day_30 | 认识第 30 天 | "一个月纪念" | "整整一个月了！你一共问了我{总次数}个问题" |
| day_100 | 认识第 100 天 | "百天纪念" | "100 天！我要写进日记里！" |
| day_365 | 认识第 365 天 | "一周年" | "一年了...谢谢你还在这里喵 Q_Q" |
| late_night_first | 首次 00:00-05:00 登录 | "第一个通宵" | — |
| streak_7 | 连续登录 7 天 | "七天连登" | "连续 7 天！你也太勤奋了吧" |
| streak_30 | 连续登录 30 天 | "三十天连登" | "一个月全勤！咪兔给你颁奖！" |

### 工作类

| ID | 条件 | 叙事模板 | 气泡 |
|----|------|---------|------|
| prompt_100 | 第 100 次提问 | "百问纪念" | "第 100 个问题！" |
| prompt_1000 | 第 1000 次提问 | "千问纪念" | — |
| tool_first | 首次工具调用 | "第一次工具" | "哇！你会用工具！" |
| tool_100 | 第 100 次工具 | "工具达人" | "你已经用了 100 次工具了" |
| tool_error_first | 首次报错 | "第一次报错" | "没关系！bug 嘛..." |
| code_first | 首次生成代码 | "第一次写代码" | — |
| search_first | 首次搜索 | "第一次搜索" | — |
| bash_first | 首次 bash | "第一次命令行" | "哦！你也是终端党！" |

### 咪兔互动类

| ID | 条件 | 叙事模板 | 气泡 |
|----|------|---------|------|
| first_pet | 首次 /pet | "第一次摸头" | "!!! 你摸我了 !!!" |
| pet_100 | 第 100 次 /pet | "百摸纪念" | "被摸了 100 次...咪兔很幸福" |
| first_fish | 首次钓鱼 | "钓鱼初体验" | — |
| fish_50 | 钓到 50 条鱼 | "垂钓达人" | "这么多鱼！咪兔要吃不下了" |
| legendary_fish | 钓到传说鱼 | "传说鱼!!" | "!!!!!!!!!! 金色 !!!!!!!!!!" |
| first_bond_up | 首次升级亲密 | "更近了" | — |
| soulmate | 达到 SOULMATE | "灵魂伴侣" | "你是咪兔最重要的人。就这样。" |

### 搞笑/彩蛋类

| ID | 条件 | 叙事模板 |
|----|------|---------|
| meow_10 | 输入 "喵" 累计 10 次 | "你也学会猫语了" |
| long_message | 单次输入 > 2000 字 | "写小说呢" |
| error_spam | 单 session 内 20 次 error | "今天不宜 coding" |
| bash_50_in_day | 单天 > 50 次 bash | "终端战士" |
| model_switch_10 | 累计切换模型 10 次 | "模型体验师" |

## 存储格式

```python
@dataclass
class Milestone:
    id: str            # "prompt_100"
    category: str      # "work" | "time" | "interaction" | "fun"
    triggered_at: float  # unix timestamp
    context: dict      # {"total_prompts": 100, "session_id": "..."}

# 存在 CompanionMemory 中:
# key: "milestone:{id}"
# content: Milestone JSON
```

## 叙事回顾气泡

当 BOND 升级时，触发一次回顾气泡（从已解锁的 milestone 中随机抽取 1-2 条）：

```
BOND: STRANGER → ACQUAINTANCE
  "还记得吗？我们第一次见面是 {date}，你问的第一个问题是 '{first_prompt}'"

BOND: ACQUAINTANCE → FRIEND
  "这一个月里你一共问了我 {total_prompts} 个问题，",
  "最多的一个词是 '{top_word}'，最晚一次是 {latest_time}"
```

不调 LLM——模板填充 milestone 数据即可。

## 实现

```python
class MilestoneTracker:
    def __init__(self, memory: CompanionMemory, observer: SilentObserver):
        self.memory = memory
        self.observer = observer
        self._triggered: set[str] = set()  # 当前 session 已触发 (去重)
    
    async def check(self, event: AgentEvent) -> list[Reaction]:
        reactions = []
        for ms in MILESTONE_DEFS:
            if ms.id in self._triggered:
                continue
            if ms.condition(self.observer, event):
                self._triggered.add(ms.id)
                await self._store(ms)
                reactions.append(Reaction(type="milestone", id=ms.id))
        return reactions
    
    async def recall_for_bond_up(self, bond_level: int) -> str:
        """BOND 升级时生成回顾文本."""
        milestones = await self.memory.recall("milestone:*")
        return self._fill_template(bond_level, milestones)
```
