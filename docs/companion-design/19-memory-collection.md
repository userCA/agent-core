# 19 — 回忆与收藏系统

## 目标

为咪兔建立一套能长期沉淀陪伴痕迹的回忆与收藏系统。

这套系统要解决的不是"如何存更多数据"，而是:

1. 如何让用户感到咪兔真的记得自己
2. 如何把抽象互动变成可回看的东西
3. 如何让成长不只存在于 bond 数字里
4. 如何让终端风格也能承载收藏与纪念感
5. 如何让用户愿意长期回来，不是为了任务，而是为了共同历史

## 核心原则

| 原则 | 说明 |
|------|------|
| 记忆重感受，不重日志 | 回忆要像被记住的片段，不是行为流水账 |
| 收藏重意义，不重数量 | 宁可少而珍贵，也不要堆满低价值条目 |
| 角色先于系统 | 用户感受到的是"咪兔记得了"，不是"数据库新增一行" |
| 可回看、可陈列、可分享 | 记忆不是埋着存，要能看、能摆、能纪念 |
| 终端极简也能有仪式感 | 用标题、符号、排序和留白来制造珍贵感 |
| 允许不完整 | 有些回忆是碎片，有些收藏是不成套的，这正是关系的味道 |

## 系统定位

咪兔的长期留存，不应该只靠:

- 每日目标
- 轻资源
- 数值成长

真正能让用户记住一只陪伴角色的，是这些内容:

- 第一次见面
- 某次深夜一起调 bug
- 连续一周都在
- 某天它突然开始叫你一个新称呼
- 某个角落里的小灯，是你们一起解锁的

所以回忆与收藏系统的作用是:

```text
把发生过的事
  → 提炼成可记住的片段
  → 摆放成一个陪伴空间
  → 让用户觉得"它和我真的有历史"
```

## 四层沉淀结构

咪兔的长期沉淀分四层:

### 1. 回忆卡

最基础的记忆单位。

特点:

- 一条一件事
- 有标题
- 有一句回顾
- 有触发时间

### 2. 时间线

把回忆卡按时间或成长阶段串起来。

特点:

- 强调共同经历
- 能看到关系如何慢慢变化

### 3. 收藏页

把回忆以外的长期资产摆出来。

包含:

- 装饰
- 房间部件
- 图鉴
- 特殊称呼
- 成长照片 / ASCII 相册

### 4. 纪念物

最高价值的长期奖励。

包含:

- 周年纪念卡
- SOULMATE 名片
- 品种专属老友印记
- 一次性稀有回忆页

## 回忆卡系统

## 回忆卡是什么

回忆卡不是原始日志，而是"从日志里提炼出来的一条值得记住的关系片段"。

推荐结构:

```text
[回忆]
标题: 第一次深夜一起调试
时间: Day 12
一句话: "那天你很困，但还是陪我到最后。"
```

## 回忆卡来源

### A. milestone 回忆

来自 [10-milestone-system.md](file:///Users/yuanbaishu/pythonProject/agent-core/docs/companion-design/10-milestone-system.md)。

例如:

- 第一次见面
- 第一次工具调用
- 第 100 次提问
- 达到 SOULMATE

特点:

- 明确
- 一次性
- 高稳定性

### B. 情境回忆

来自时间、状态、连续行为和陪伴氛围。

例如:

- 第一次深夜相遇
- 第一次在 worried 时安抚成功
- 某次连续失败后终于修复
- 连续 3 天午间回来看看它

特点:

- 更生活化
- 更有情绪味道

### C. 关系回忆

来自 bond、称呼、亲密互动变化。

例如:

- 第一次主动蹭屏幕
- 第一次允许揉肚子
- 第一次用新称呼叫你
- 第一次在你离开后表达想念

特点:

- 和品种、bond、STYLE 强绑定
- 感知最强

### D. 收藏回忆

来自解锁某个物件、相册页、主题样式。

例如:

- 第一个小窝
- 房间里第一盏灯
- 第一条围巾
- 第一张成长相册页

特点:

- 连接回忆与收藏
- 方便可视化陈列

## 回忆卡字段

```python
@dataclass
class MemoryCard:
    id: str
    category: str          # milestone / mood / bond / room / hidden
    title: str
    summary: str
    triggered_at: float
    bond_level: str
    emotion_tag: str = ""
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    visual_key: str = ""   # 关联相册/装饰/ASCII 快照
```

## 回忆卡文案规范

回忆卡不能像成就系统文案，也不能像系统日志。

### 推荐风格

- 短
- 准
- 带一点咪兔视角
- 像翻旧纸片时看见的一句注释

### 示例

好:

- "那天你第一次摸我，我装作很镇定。"
- "你连续修了三次 bug，我在旁边看着都紧张。"
- "那天很晚了，但你没有先走。"

不要:

- "完成成就: 第一次执行 /pet"
- "用户于 2026-06-05 13:45 触发互动事件"

## 时间线系统

时间线回答的是:

```text
我们是怎么从第一次见面，慢慢变成现在这样的？
```

## 时间线视图

推荐有三种视图:

### 1. 最近发生

默认视图。

展示最近 5-10 条值得看的回忆。

适合:

- 快速回顾
- 页面里轻阅读

### 2. 成长阶段

按 bond 阶段组织:

- STRANGER
- ACQUAINTANCE
- FRIEND
- CLOSE
- SOULMATE

适合:

- 看关系变化
- 和形象演化对齐

### 3. 主题筛选

按主题查看:

- 一起工作
- 一起熬夜
- 被摸摸
- 收到礼物
- 隐藏彩蛋

适合:

- 品味某一类共同经历
- 做纪念卡选材

## 推荐展示

```text
┌─ Memories ─────────────────┐
│ * 第一次见面               │
│ * 第一次深夜一起调试       │
│ * 它第一次主动蹭屏幕       │
│ * 房间里亮起第一盏灯       │
└────────────────────────────┘
```

## 回忆页系统

回忆卡是点，回忆页是面。

当多条相关回忆聚合后，可以生成一页完整的纪念页。

## 回忆页类型

### A. 周回顾页

来源:

- 本周目标
- 周总结
- 工作/陪伴统计

示例:

```text
[Week 03]
- 一起修好了 4 次 bug
- 深夜见面 2 次
- 它被摸了 7 次
一句话: "这周过得很满，也很靠近。"
```

### B. 成长回顾页

在 bond 升级时生成。

示例:

- STRANGER -> ACQUAINTANCE
- FRIEND -> CLOSE

内容:

- 代表性回忆 2-3 条
- 当前称呼
- 外观变化

### C. 特殊事件页

例如:

- 一周年
- SOULMATE 达成
- 长时间离别后的重逢

特点:

- 更完整
- 更适合做纪念卡或分享

## 成长相册系统

成长相册回答的是:

```text
它不是只有一套精灵，它是慢慢长大的。
```

## 相册来源

### A. ASCII 快照

直接使用当前精灵状态生成一张文本快照。

优点:

- 成本低
- 最符合终端风视觉
- 能和真实当时状态强绑定

### B. milestone 配图

在 milestone 触发时截取当前 ASCII 形象或放大渲染。

### C. 生图照片

来自 [13-visual-evolution-media.md](file:///Users/yuanbaishu/pythonProject/agent-core/docs/companion-design/13-visual-evolution-media.md) 的按需生图或成长照片。

## 相册页结构

```text
[album]
- STRANGER: 小猫时期
- ACQUAINTANCE: 第一次叫出名字
- FRIEND: 第一次慢眨眼
- CLOSE: 有了自己的小窝
- SOULMATE: 星光项圈
```

## 相册设计原则

- 每个 bond 阶段至少有 1 页可纪念
- 相册页数量不宜爆炸
- 一页必须有视觉锚点
- 标题要比数值更重要

## 图鉴系统

图鉴不是怪物图鉴，而是"你和这只咪兔一起发现过什么"。

## 图鉴内容

### A. 品种图鉴

记录这只咪兔所属品种的特性与专属内容。

包括:

- 品种简介
- 专属动作
- 专属口头禅
- 已触发过的 breed exclusive bubble

### B. 行为图鉴

记录你已经见过的互动表现。

例如:

- slow blink
- zoomies
- concerned stare
- belly up

### C. 彩蛋图鉴

记录已经发现的隐藏互动。

例如:

- 深夜摸摸
- 省略号合唱
- bug 追逐

### D. 收藏图鉴

记录已解锁装饰和房间部件。

例如:

- 小灯
- 小窝
- 围巾
- 项圈吊牌

## 图鉴设计原则

- 图鉴只展示"已发现"的内容
- 未发现内容最多给模糊轮廓，不给完整剧透
- 图鉴是回味，不是任务清单

示例:

```text
[collection]
room: 小灯 / 小窝
wearing: 蓝围巾
easter eggs: 3 discovered
```

## 纪念卡系统

纪念卡是咪兔收藏系统中最适合被分享和截图的内容。

## 纪念卡来源

### A. 一周纪念卡

条件:

- 完成一周目标
- 或触发本周代表性回忆

### B. milestone 纪念卡

条件:

- 100 问
- 一周年
- SOULMATE
- 传说鱼

### C. 主题纪念卡

条件:

- 深夜搭子
- 开发搭子
- 安静陪伴
- 图书馆搭子

## 纪念卡内容

```text
┌─ Mitu Card ────────────────┐
│ title: 深夜搭子            │
│ bond: FRIEND               │
│ days: 12                   │
│ line: "你很晚了还在，我也在"│
└────────────────────────────┘
```

## 纪念卡原则

- 一张卡只强调一个主题
- 强调一句话胜过强调很多数据
- 适合截图分享，但不强迫用户分享

## 收藏陈列系统

收藏系统不是背包，而是咪兔的小房间和它随身的东西。

## 陈列对象

### 1. 可穿戴

- 围巾
- 项圈
- 吊牌
- 品种专属装饰

### 2. 房间部件

- 小灯
- 小窝
- 牌匾
- 边角线框

### 3. 特殊标记

- 星点
- 名字下划线
- SOULMATE 光点
- 节日边框

## 陈列原则

- 收藏要和常驻层、`buddy.room`、`collection` 互通
- 不是只在列表里拥有，而要在页面角落真实出现
- 房间陈列比资源库存更重要

## 收藏解锁节奏

| 类型 | 解锁来源 | 节奏 |
|------|---------|------|
| 基础装饰 | `spark` / `ribbon` | 慢慢来 |
| 纪念装饰 | 里程碑 / 周目标 | 有情境 |
| 稀有装饰 | 隐藏互动 / 高 bond | 稀有 |
| 老友装饰 | SOULMATE 后 | 长线奖励 |

## 收藏与回忆的关系

不是所有收藏都要附带回忆，但高价值收藏最好有一条来源说明。

例如:

```text
小灯
来源: "你第一次陪我熬到这么晚。"
```

这会让收藏不只是物件，而是被赋予关系意义。

## 收藏排序规则

推荐排序优先级:

1. 当前穿戴 / 当前陈列
2. 最新解锁
3. 最稀有
4. 最有纪念意义

而不是简单按获得时间堆列表。

## 收藏容量与筛选

为了避免后期信息过载:

- 回忆卡默认只展示精选
- 普通回忆可以折叠
- 收藏项默认只显示已陈列和稀有项
- 老旧、重复、低价值条目可合并为合集

例如:

- "普通喂食日常 x12"
- "午间来看我 x7"

这些不需要变成 12 张独立卡片。

## 精选机制

系统应自动维护一组"值得被翻看的回忆"。

## 精选规则

优先保留:

- milestone 类
- 品种专属类
- 深夜 / 回归 / 重逢类
- bond 升级相关
- 稀有隐藏互动

降低权重:

- 重复日常
- 同质化普通互动

## 收藏与 UI 的对应

根据 [17-terminal-ui-ux.md](file:///Users/yuanbaishu/pythonProject/agent-core/docs/companion-design/17-terminal-ui-ux.md):

- `memory` 负责看回忆时间线
- `album` 负责看成长相册
- `collection` 负责看装饰和房间
- `buddy.room` 负责看当前陈列效果

要求:

- 同一信息不要在多个面板里重复堆叠
- 每个入口只回答一个核心问题

## 资源与回忆的关系

根据 [16-economy-and-rewards.md](file:///Users/yuanbaishu/pythonProject/agent-core/docs/companion-design/16-economy-and-rewards.md):

- `memory_shard` 负责把碎片拼成页
- `ribbon` 更偏装饰和纪念物
- `spark` 更偏房间和氛围成长

映射建议:

| 资源 | 主要作用 |
|------|---------|
| `memory_shard` | 回忆页、纪念卡、相册页 |
| `ribbon` | 可穿戴和纪念装饰 |
| `spark` | 房间线稿、角落氛围 |

## 实现建议

```python
@dataclass
class CollectionItem:
    id: str
    category: str          # wearable / room / badge / album
    name: str
    rarity: str
    unlocked_at: float
    source_memory_id: str = ""
    equipped: bool = False
    placed: bool = False


@dataclass
class MemoryShelf:
    cards: list[MemoryCard]
    featured_ids: list[str]
    album_pages: list[str]
    collection_ids: list[str]


class MemoryEngine:
    def add_card(self, event, observer, companion_state) -> MemoryCard | None:
        ...

    def build_week_page(self, week_state) -> dict:
        ...

    def build_bond_page(self, bond_level, cards) -> dict:
        ...

    def pick_featured_cards(self, cards) -> list[str]:
        ...
```

## 存储建议

```python
@dataclass
class MemoryState:
    cards: list[MemoryCard]
    album_pages: list[str]
    discovered_easter_eggs: list[str]
    unlocked_collection_items: list[str]
    featured_memory_ids: list[str]
```

## 推荐实现顺序

### P0

1. milestone -> 回忆卡
2. `memory` 最近回忆列表
3. `memory_shard` -> 回忆页
4. 周回顾页

### P1

1. bond 升级回顾页
2. `album` 成长相册
3. `collection` 装饰陈列列表
4. 精选回忆机制

### P2

1. 纪念卡
2. 房间陈列来源说明
3. 稀有主题合集
4. 可分享的 SOULMATE 名片

## 最终体验

当用户打开 `memory` 或 `collection` 时，不该看到一个系统后台。

用户应该看到的是:

- "原来我们已经一起经历了这么多。"
- "这些东西不是奖励列表，而是我们一起留下来的。"
- "这只咪兔不是今天才可爱，它是被我陪着慢慢长成现在这样的。"

这就是咪兔回忆与收藏系统真正要做到的事。
