# 附录 — 持久化与存储规格

> 目的: 为 companion 的长期数据定义稳定、分层、可迁移的存储规格。

## 为什么需要这份文档

咪兔是长期陪伴系统，真正脆弱的不是一帧动画，而是用户养出来的历史。

如果存储层没有清晰边界，后续最容易发生的问题是:

- 角色数据和展示缓存混在一起
- 本可重建的数据被错误持久化
- 一次字段重命名导致旧用户读档失败
- 不同子系统重复存同一份状态
- 回忆、目标、奖励互相交叉写入，难以维护

所以这份文档的目标是:

1. 明确什么数据该存，什么不该存
2. 把 deterministic bones 和可变 soul 彻底隔离
3. 让存储具备 append-only 和迁移能力
4. 为未来扩展新玩法提供稳定数据底座

## 总体原则

| 原则 | 说明 |
|------|------|
| Bones 不存，Soul 才存 | 可确定性重建的数据不持久化 |
| 单一拥有者 | 每类业务数据只有一个权威写入点 |
| append-only 优先 | 新字段优先新增，避免重写旧数据语义 |
| 快照与日志分离 | 当前状态和历史记录分别存储 |
| 视图不入库 | 前端展示态、临时派生态不做持久化 |
| 可迁移 | 每份持久化对象都应可按版本升级 |

## 分层模型

companion 持久化分为五层:

| 层 | 内容 | 是否持久化 |
|----|------|:--:|
| L1 | Bones / 确定性基因 | 否 |
| L2 | Soul / 长期角色状态 | 是 |
| L3 | Progress / 成长与资源进度 | 是 |
| L4 | History / 回忆、里程碑、日志 | 是 |
| L5 | View Cache / 前端展示缓存 | 否 |

## L1 — Bones

Bones 指所有可以通过 `uid + seed + append-only species definition` 重建的数据。

包括:

- 品种
- 稀有度
- 眼睛
- 耳朵
- 颜色
- 闪亮判定
- 初始帽子 / accent

### 原则

- **不持久化**
- 由 `bones.py` 纯函数重建
- 任何持久化系统不得把 Bones 当主数据源

### 原因

- 避免重复存储
- 避免新旧版本不一致
- 保证 agent-core 升级后老用户仍能被稳定重建

### 唯一例外

若未来允许用户主动改装扮，则:

- “默认配饰”仍属于 Bones
- “用户主动装备状态”属于 Soul / Collection 层

## L2 — Soul

Soul 是一只咪兔在长期陪伴中慢慢形成、不可从 uid 直接重建的数据。

包括:

- 当前 bond score / bond level
- STYLE 判定结果
- 当前可穿戴状态
- 称呼变化
- 高价值偏好
- 回归恢复状态

### 建议结构

```python
@dataclass
class CompanionSoul:
    schema_version: int
    uid: str

    bond_score: float
    bond_level: str
    style: str

    nickname: str = ""
    user_display_name: str = ""
    last_seen_at: float = 0.0
    first_seen_at: float = 0.0

    days_away_state: str = ""
    recovery_bonus_until: float = 0.0

    equipped_items: dict[str, str] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
```

## L3 — Progress

Progress 指所有可增长、可消耗、可结算，但不属于永久历史叙事的数据。

包括:

- 轻资源
- 日目标 / 周目标进度
- 当前房间解锁状态
- 收藏解锁状态
- 小游戏素材数量

### 子模块

#### `EconomyState`

```python
@dataclass
class EconomyState:
    schema_version: int
    snack: int
    spark: int
    memory_shard: int
    ribbon: int

    daily_earned: dict[str, int]
    weekly_earned: dict[str, int]
```

#### `GoalState`

```python
@dataclass
class GoalState:
    schema_version: int
    active_daily_ids: list[str]
    active_weekly_ids: list[str]
    daily_progress: dict[str, int]
    weekly_progress: dict[str, int]
    generated_at: float
    expires_at: float
```

#### `CollectionState`

```python
@dataclass
class CollectionState:
    schema_version: int
    unlocked_item_ids: list[str]
    placed_room_item_ids: list[str]
    equipped_wearable_ids: list[str]
```

### 原则

- Progress 是当前进度，不是完整历史
- 能被历史反推的冗余字段应避免重复存

## L4 — History

History 指陪伴系统最重要的长期沉淀。

包括:

- milestone
- memory cards
- 周回顾页
- bond 升级回顾页
- 稀有事件记录

### 4.1 Milestone

来自 [10-milestone-system.md](../10-milestone-system.md)。

```python
@dataclass
class Milestone:
    schema_version: int
    id: str
    category: str
    triggered_at: float
    context: dict
```

### 4.2 MemoryCard

来自 [19-memory-collection.md](../19-memory-collection.md)。

```python
@dataclass
class MemoryCard:
    schema_version: int
    id: str
    category: str
    title: str
    summary: str
    triggered_at: float
    bond_level: str
    emotion_tag: str = ""
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    visual_key: str = ""
```

### 4.3 Summary Pages

```python
@dataclass
class SummaryPage:
    schema_version: int
    id: str
    page_type: str        # week / bond / anniversary / comeback
    title: str
    generated_at: float
    memory_ids: list[str]
    payload: dict
```

### 原则

- History 一经写入，默认不可覆盖
- 修正文案时允许“补丁式升级”，不允许无痕改写触发事实

## L5 — View Cache

View Cache 指只为了前端渲染方便存在的状态。

包括:

- 当前前端面板是否展开
- 最后一次 bubble 的渲染剩余时间
- 本地播放到第几帧
- 当前 tab
- 组件内部 loading

### 原则

- **不持久化**
- 仅保存在前端 store 或运行时内存

## 单一拥有者规则

每类数据必须只有一个权威拥有者。

| 数据 | 权威拥有者 |
|------|-----------|
| Bones | `bones.py` 重建逻辑 |
| Bond / Style | `bond_growth` / `observer` |
| Emotion | `EmotionFSM` 运行时，不落盘为长期主状态 |
| Goals | `GoalEngine` |
| Rewards / Economy | `RewardEngine` |
| Milestones | `MilestoneTracker` |
| Memory cards | `MemoryEngine` |
| Collection | `CollectionState` |

明确禁止:

- 前端写 bond level
- 多个模块同时写 memory cards
- 由 UI 直接改动收藏装备结果

## Key 设计建议

推荐使用逻辑分区 key，避免所有数据堆进一个大 JSON。

示例:

```text
companion:soul:{uid}
companion:economy:{uid}
companion:goals:{uid}
companion:collection:{uid}
companion:milestone:{uid}:{milestone_id}
companion:memory:{uid}:{memory_id}
companion:summary:{uid}:{page_id}
```

### 好处

- 易于按模块迁移
- 易于局部失效和修复
- 易于测试单模块
- 减少无关字段的耦合读取

## 快照与历史分离

### 快照类

适合覆盖写:

- `soul`
- `economy`
- `goals`
- `collection`

### 历史类

适合 append-only 写:

- `milestone:*`
- `memory:*`
- `summary:*`

### 原因

- 快照类体现“当前状态”
- 历史类体现“已经发生过的事”

把两者分开，维护成本会显著下降。

## schema_version 策略

所有持久化对象必须带 `schema_version`。

### 原则

- 新增字段: 版本可不立刻升级，若兼容可选字段即可
- 语义变化或结构变化: 必须升级版本
- 升级逻辑必须放在 backend 读取路径，前端不参与迁移

### 示例

```python
def load_soul(raw: dict) -> CompanionSoul:
    version = raw.get("schema_version", 1)
    if version == 1:
        raw = migrate_soul_v1_to_v2(raw)
        version = 2
    return CompanionSoul(**raw)
```

## append-only 约束

### 对 species / bones

- roll 序列 append-only
- 权重定义 append-only
- 不修改旧含义

### 对 history

- 新回忆、新 milestone 只追加
- 不删除旧事件
- 若需要隐藏或废弃，使用 `flags.archived = true`

## 删除策略

陪伴系统的数据原则上不做硬删除。

### 允许软删除 / 归档

- 测试数据
- 被错误生成的低价值展示页
- 重复合集页

### 方式

```python
flags = {
    "archived": True,
    "hidden_from_default_view": True
}
```

### 禁止

- 直接删除 milestone 历史
- 直接抹掉用户已达成的纪念数据

## 衍生字段规则

某些字段适合存，某些只适合运行时派生。

### 应存

- `bond_score`
- `style`
- `unlocked_item_ids`
- `featured_memory_ids`

### 不应存

- `frontend_mood`
- 当前 idle frame index
- `mood_dots`
- 当前面板内容拼装文本

原因:

- 这些都可由当前状态即时派生
- 存了只会增加一致性风险

## 幂等写入

为保证可维护性，以下写入必须幂等:

- milestone 写入
- reward 结算写入
- memory.added 写入
- goal completion 写入

### 方法

- 以事件 ID 或逻辑唯一 ID 去重
- 先查是否已存在，再决定是否写入

示例:

```python
def store_milestone(ms: Milestone):
    key = f"companion:milestone:{uid}:{ms.id}"
    if store.exists(key):
        return
    store.put(key, ms)
```

## 事务边界

一次高层业务动作，可能涉及多个子模块。

例如一次“目标完成”可能触发:

- `GoalState` 更新
- `EconomyState` 更新
- `MemoryCard` 新增
- `SummaryPage` 待更新

### 原则

- 先写快照状态
- 再写 append-only 历史
- 若不能全事务，至少保证重复执行不破坏结果

推荐顺序:

```text
1. update progress snapshot
2. update economy snapshot
3. append memory / milestone
4. emit SSE
```

## 最小持久化单元

为了降低耦合，推荐最小持久化单元按“模块”而不是“整只猫大对象”组织。

不要:

```json
{
  "everything": {
    "bones": {},
    "emotion": {},
    "goals": {},
    "memory": {},
    "ui": {}
  }
}
```

要:

```text
soul
economy
goals
collection
milestone:*
memory:*
summary:*
```

## 测试建议

应至少覆盖:

- 旧 schema 迁移测试
- 重复 milestone 幂等测试
- 回忆 append-only 测试
- Bones 重建与持久化解耦测试
- snapshot 与 history 分层测试

## 恢复与修复策略

如果某个模块数据损坏，优先按层级恢复。

### 可重建层

- Bones: 直接重建

### 可回退层

- Economy / Goals / Collection: 从最近快照恢复

### 不可丢层

- Milestones / Memory cards / Summary pages

对不可丢层的策略:

- 多做只追加写
- 多做备份
- 少做覆盖

## 与现有文档的关系

| 文档 | 本附录负责的补位 |
|------|----------------|
| `README.md` | 补上整体架构中的存储契约 |
| `14-frontend-backend-boundary.md` | 进一步把“唯一数据源”落实到存储层 |
| `10-milestone-system.md` | 固定 milestone 的存储位置与 append-only 规则 |
| `16-economy-and-rewards.md` | 固定 economy snapshot 的结构和归属 |
| `18-goals-and-anti-fatigue.md` | 固定 goals snapshot 与过期结算边界 |
| `19-memory-collection.md` | 固定 memory / collection 的持久化模型 |

## 最终约束

这份存储规格最终要守住三件事:

1. 用户历史不能因为扩展新玩法而被破坏
2. 前端展示变化不能反向污染后端真实状态
3. 子系统可以独立演进，而不是共享一坨难维护的大对象

只要这三件事成立，咪兔的整体隔离性、可扩展性和可维护性才是真正可靠的。
