# 附录 — SSE 事件协议

> 目的: 为 companion 的前后端通信建立稳定、可扩展、可版本化的事件协议。

## 为什么需要这份文档

如果没有明确的 SSE schema，前端很容易逐渐开始:

- 猜测字段含义
- 依赖某次临时返回
- 在组件里写隐式业务判断
- 因字段变化而发生回归

这会直接破坏 [14-frontend-backend-boundary.md](../14-frontend-backend-boundary.md) 中定义的职责边界。

所以本附录的目标是:

1. 固定 companion 事件协议
2. 保证前端只渲染，不推断业务
3. 允许后端逐步扩展字段而不破坏旧前端
4. 为调试、回放、录制和测试提供稳定数据面

## 设计原则

| 原则 | 说明 |
|------|------|
| 后端单一真相源 | emotion、goal、reward、memory 等内容均由 backend 决定 |
| 事件最小完备 | 一条事件要足够前端渲染，但不夹带无关内部状态 |
| append-only 扩展 | 新功能优先新增字段，不重定义旧字段 |
| 类型先于实现 | 先定义 event type 和 payload，再写前后端代码 |
| 弱耦合渲染 | 前端根据 `type` 和稳定 payload 渲染，不依赖隐式上下文 |
| 可追踪 | 每条事件都应带时间、版本、事件 ID，便于日志和回放 |

## 传输格式

使用标准 SSE:

```text
event: companion
data: {"v":1,"id":"evt_123","type":"emotion.update", ...}
```

约定:

- `event` 使用统一通道名，例如 `companion`
- 具体语义由 JSON 中的 `type` 决定
- 每条 `data` 必须是单个 JSON object
- 不传递多段拼接 JSON

## 顶层信封

所有 companion SSE 事件都使用统一信封:

```json
{
  "v": 1,
  "id": "evt_20260605_001",
  "ts": 1780657000.123,
  "type": "emotion.update",
  "uid": "user_123",
  "session_id": "sess_abc",
  "payload": {}
}
```

## 顶层字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `v` | integer | 是 | 协议版本，当前固定为 `1` |
| `id` | string | 是 | 事件唯一 ID，便于去重和追踪 |
| `ts` | number | 是 | 服务器生成时间戳，unix seconds |
| `type` | string | 是 | 事件类型，如 `emotion.update` |
| `uid` | string | 是 | 用户 ID |
| `session_id` | string | 否 | 当前会话 ID，无会话时可省略 |
| `payload` | object | 是 | 事件主体 |

## 版本策略

### `v`

- `v` 代表信封协议版本
- 仅在顶层结构发生破坏性变化时升级
- 当前所有 payload 细分扩展，优先在 `payload` 内 append-only 完成

### 兼容要求

- `v=1` 的前端必须忽略未知字段
- 后端在 `v=1` 下不得改变已有字段语义
- 新 event type 可以新增，不影响旧前端

## 事件分类

companion SSE 暂分为 8 类:

| 类别 | 前缀 | 用途 |
|------|------|------|
| 情绪状态 | `emotion.*` | 更新当前情绪与前端 mood |
| 精灵渲染 | `sprite.*` | 更新形态、动画、视觉覆盖 |
| 气泡文本 | `bubble.*` | 角色说话、提示、纪念文案 |
| 面板数据 | `panel.*` | `buddy`、`goal`、`memory` 等面板数据 |
| 奖励结算 | `reward.*` | 资源、解锁、轻结算 |
| 目标进度 | `goal.*` | 日目标/周目标更新 |
| 回忆收藏 | `memory.*` | 回忆新增、收藏解锁、纪念卡 |
| 系统状态 | `system.*` | 初始化、重连、快照、错误 |

## 1. `emotion.update`

用于更新 companion 当前情绪。

```json
{
  "v": 1,
  "id": "evt_1",
  "ts": 1780657000.123,
  "type": "emotion.update",
  "uid": "user_123",
  "session_id": "sess_abc",
  "payload": {
    "emotion": "HAPPY",
    "frontend_mood": "happy",
    "eye_override": "♥",
    "intensity": 0.72,
    "source": "tool_success"
  }
}
```

### 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `emotion` | string | 是 | 后端 EmotionFSM 状态，如 `HAPPY` |
| `frontend_mood` | string | 是 | 前端渲染用 mood |
| `eye_override` | string/null | 否 | 眼睛覆盖字符，无则 `null` |
| `intensity` | number | 否 | 0-1，前端仅用于动画强度，不参与业务判断 |
| `source` | string | 否 | 触发来源，便于调试 |

### 约束

- 前端不得根据 `source` 自行推导 mood
- `frontend_mood` 是渲染唯一依据

## 2. `sprite.update`

用于更新精灵渲染上下文。

```json
{
  "v": 1,
  "id": "evt_2",
  "ts": 1780657001.123,
  "type": "sprite.update",
  "uid": "user_123",
  "payload": {
    "breed": "ragdoll",
    "bond_stage": "FRIEND",
    "rarity": "epic",
    "shiny": false,
    "frame_set": "adult",
    "animation": "slow_blink",
    "accessories": {
      "hat": "none",
      "accent": "blue_scarf",
      "badge": ""
    }
  }
}
```

### 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `breed` | string | 是 | 品种名，必须与后端定义一致 |
| `bond_stage` | string | 是 | `STRANGER`/`FRIEND` 等 |
| `rarity` | string | 是 | 稀有度 |
| `shiny` | boolean | 是 | 是否闪亮 |
| `frame_set` | string | 是 | `kitten`/`adult`/`soulmate` |
| `animation` | string | 否 | 当前建议动画名 |
| `accessories` | object | 否 | 当前装饰 |

## 3. `bubble.show`

用于显示一条气泡。

```json
{
  "v": 1,
  "id": "evt_3",
  "ts": 1780657002.123,
  "type": "bubble.show",
  "uid": "user_123",
  "payload": {
    "text": "这次修好了喵。",
    "style": "normal",
    "priority": 40,
    "ttl_ms": 4500,
    "category": "reaction",
    "replace": true
  }
}
```

### 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `text` | string | 是 | 气泡文案 |
| `style` | string | 否 | `normal`/`hint`/`milestone`/`hidden` |
| `priority` | integer | 是 | 优先级，数值越大越高 |
| `ttl_ms` | integer | 是 | 自动消失时间 |
| `category` | string | 否 | `reaction`/`hint`/`milestone`/`weekly` |
| `replace` | boolean | 否 | 是否替换当前气泡 |

## 4. `reward.grant`

用于结算轻奖励。

```json
{
  "v": 1,
  "id": "evt_4",
  "ts": 1780657003.123,
  "type": "reward.grant",
  "uid": "user_123",
  "payload": {
    "bundle": {
      "snack": 0,
      "spark": 1,
      "memory_shard": 0,
      "ribbon": 0,
      "bond_delta": 1
    },
    "unlocks": [],
    "memories": [],
    "display_text": "[获得] spark +1"
  }
}
```

### 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `bundle` | object | 是 | 奖励数值集合 |
| `unlocks` | string[] | 否 | 本次解锁项 ID |
| `memories` | string[] | 否 | 本次新增回忆 ID |
| `display_text` | string | 否 | 推荐渲染文案 |

## 5. `goal.snapshot`

用于发送当前目标快照，供 `goal` 面板展示。

```json
{
  "v": 1,
  "id": "evt_5",
  "ts": 1780657004.123,
  "type": "goal.snapshot",
  "uid": "user_123",
  "payload": {
    "daily": [
      {
        "id": "daily_tool_3",
        "text": "成功调用工具 3 次",
        "progress": 2,
        "target": 3,
        "completed": false
      }
    ],
    "weekly": [
      {
        "id": "weekly_evening_3",
        "text": "在 3 个不同时间段见到咪兔",
        "progress": 1,
        "target": 3,
        "completed": false
      }
    ],
    "reward_text": "snack +1, spark +1"
  }
}
```

## 6. `goal.progress`

用于更新单个目标的进度变化。

```json
{
  "v": 1,
  "id": "evt_6",
  "ts": 1780657005.123,
  "type": "goal.progress",
  "uid": "user_123",
  "payload": {
    "scope": "daily",
    "goal_id": "daily_pet_2",
    "progress": 2,
    "target": 2,
    "completed": true,
    "soft_text": "今天也有把我放进日程里喵。"
  }
}
```

## 7. `memory.added`

用于通知新增回忆。

```json
{
  "v": 1,
  "id": "evt_7",
  "ts": 1780657006.123,
  "type": "memory.added",
  "uid": "user_123",
  "payload": {
    "memory_id": "mem_night_debug_001",
    "title": "第一次深夜一起调试",
    "summary": "那天你很困，但还是没有先走。",
    "category": "mood",
    "featured": true
  }
}
```

## 8. `memory.snapshot`

用于发送回忆列表、精选条目、相册页摘要。

```json
{
  "v": 1,
  "id": "evt_8",
  "ts": 1780657007.123,
  "type": "memory.snapshot",
  "uid": "user_123",
  "payload": {
    "items": [
      {
        "id": "mem_first_meeting",
        "title": "第一次见面",
        "summary": "你问了一个很普通的问题，但我记住了。",
        "category": "milestone",
        "bond_level": "STRANGER",
        "triggered_at": 1780000000.0
      }
    ],
    "featured_ids": ["mem_first_meeting"],
    "album_pages": ["album_friend_blink"],
    "next_cursor": ""
  }
}
```

## 9. `collection.unlocked`

用于通知收藏或装饰解锁。

```json
{
  "v": 1,
  "id": "evt_9",
  "ts": 1780657008.123,
  "type": "collection.unlocked",
  "uid": "user_123",
  "payload": {
    "item_id": "room_lamp_small",
    "name": "小灯",
    "category": "room",
    "rarity": "common",
    "source_memory_id": "mem_night_debug_001"
  }
}
```

## 10. `panel.snapshot`

用于统一返回面板渲染数据。

```json
{
  "v": 1,
  "id": "evt_10",
  "ts": 1780657009.123,
  "type": "panel.snapshot",
  "uid": "user_123",
  "payload": {
    "panel": "buddy",
    "data": {
      "emotion": "HAPPY",
      "bond": "FRIEND",
      "mood_dots": "..o..",
      "energy_dots": ".ooo.",
      "need_text": "想被摸摸"
    }
  }
}
```

### 说明

- `panel.snapshot` 是通用兜底事件
- 专用面板事件可逐步演进，但前端必须支持这一通用格式

## 11. `system.snapshot`

用于初始化或重连后的全量状态同步。

```json
{
  "v": 1,
  "id": "evt_11",
  "ts": 1780657010.123,
  "type": "system.snapshot",
  "uid": "user_123",
  "payload": {
    "emotion": {
      "emotion": "NEUTRAL",
      "frontend_mood": "calm",
      "eye_override": null
    },
    "sprite": {
      "breed": "tuxedo",
      "bond_stage": "ACQUAINTANCE",
      "frame_set": "adult"
    },
    "resources": {
      "snack": 2,
      "spark": 5,
      "memory_shard": 1,
      "ribbon": 0
    }
  }
}
```

## 事件命名规则

事件命名使用:

```text
<domain>.<action>
```

示例:

- `emotion.update`
- `bubble.show`
- `reward.grant`
- `memory.added`
- `system.snapshot`

禁止:

- `companionMood`
- `newBubbleEvent`
- `doUpdate`

原因:

- 不利于扩展
- 不利于分层
- 不利于测试和日志聚合

## 可选字段策略

### 允许新增

- `payload` 内新增可选字段
- 新增新的 `type`
- 新增调试字段，如 `source`

### 禁止变更

- 已有字段改名
- 已有字段改变语义
- 同名字段类型变更

## 前端消费规则

前端收到事件后:

1. 先按 `type` 分发
2. 再按稳定字段渲染
3. 忽略未知字段
4. 不基于缺省猜业务状态

明确禁止:

- 没收到 `emotion.update` 时自己推断 mood
- 依据 `reward.grant` 自行增减 bond 等级
- 看到 `memory.added` 后猜测是否要切换 panel

## 去重与顺序

### 去重

- 以前端本地缓存 `id` 做幂等去重
- 网络重放不得导致重复结算

### 顺序

推荐同一逻辑链条下的事件顺序:

```text
emotion.update
→ bubble.show
→ reward.grant
→ memory.added
```

但前端必须容忍乱序或延迟到达。

## 错误与降级

### 解析失败

- 丢弃单条无效事件
- 不中断 SSE 连接
- 记录日志

### 字段缺失

- 缺失必填字段: 丢弃该事件
- 缺失可选字段: 使用安全默认值

## TypeScript 参考类型

```ts
type CompanionEnvelope<T = unknown> = {
  v: 1;
  id: string;
  ts: number;
  type: string;
  uid: string;
  session_id?: string;
  payload: T;
};

type EmotionUpdatePayload = {
  emotion: string;
  frontend_mood: string;
  eye_override?: string | null;
  intensity?: number;
  source?: string;
};
```

## 测试建议

为保证可维护性，建议至少覆盖:

- `type` 分发测试
- 旧前端忽略未知字段测试
- `reward.grant` 幂等测试
- `system.snapshot` 初始化渲染测试
- `memory.added` 与 `goal.progress` 的乱序容忍测试

## 最终约束

这份 schema 的最终目标只有一句话:

```text
前端看协议渲染，
后端看规则决策，
中间靠稳定事件解耦。
```

只要这个边界不被打破，咪兔系统才能在持续扩展时保持隔离性、可扩展性和可维护性。
