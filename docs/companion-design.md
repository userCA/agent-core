# 咪兔伴侣系统设计

> **详细设定集**: 见 [`companion-design/`](./companion-design/) — 14 份文档覆盖视觉/动画/性格/情绪/成长/互动/品种角色卡等完整规格。
> 本文档是代码实现的**主依据**，定义数据结构、算法、Phase 计划。

## 背景

当前咪兔只是登录页的静态 ASCII 装饰，登录后即消失。参考 Claude Code buddy 的设计，将咪兔升级为用户专属伴侣：每个 uid 拥有确定性生成的独特咪兔，伴随整个 agent 生命周期。

## Buddy 参考设计

buddy 的核心机制：

| 层 | 机制 | 位置 |
|---|------|------|
| 确定性骨骼 | `hash(userId) + seeded PRNG` → 物种/稀有度/眼睛/帽子/闪亮/属性 | `companion.ts:roll()` |
| 骨骼/灵魂分离 | Bones 每次从 hash 重算（不可伪造），Soul 由 LLM 生成后持久化 | `types.ts:CompanionBones/CompanionSoul` |
| 多帧动画 | 每种物种 3 帧 idle fidget，500ms tick 驱动 | `sprites.ts:BODIES` |
| 气泡 | 空闲 10s 出现气泡，pet 触发爱心 | `CompanionSprite.tsx` |
| 稀有度 | common(60%)→legendary(1%)，5 级加权随机 | `types.ts:RARITY_WEIGHTS` |

## 总体架构

```
agent_core/
├── companion/                  # 伴侣系统核心 (新增)
│   ├── __init__.py             # 公开 API: CompanionConfig, roll_companion()
│   ├── bones.py                # 确定性生成 (seeded PRNG + hash uid)
│   ├── species.py              # 物种/稀有度/属性/眼睛/配饰枚举定义
│   ├── sprites.py              # ASCII 精灵图数据，多帧动画帧
│   └── reactions.py            # 气泡/情绪响应规则引擎
│
├── extensions/
│   └── companion.py            # CompanionExtension (Phase 3, 实现 Extension Protocol)
│
scene/http_sse/static/src/
├── components/
│   └── companion/              # 前端伴侣组件 (Phase 1-2)
│       ├── CompanionSprite.tsx  # 精灵渲染 + 多帧动画
│       ├── CompanionBubble.tsx  # 气泡组件
│       ├── LoginCompanion.tsx   # 登录页专用伴侣
│       └── HeaderCompanion.tsx  # 聊天页 Header 伴侣 (替代静态 logo)
│
├── stores/
│   └── companion-store.ts      # 伴侣状态管理 (Zustand)
│
└── api/
    └── companion.ts            # 后端伴侣 API 调用
```

## Phase 1: 登录页增强 (前端 only)

### 1.1 多帧咪兔动画

```ts
// sprites.ts — 咪兔专用精灵
const MITU_SPRITES: Record<MituMood, string[][]> = {
  sleeping: [
    // frame 0: 安静趴睡
    [
      '  /\\_/\\  ',
      ' ( -.- ) ',
      ' ( z  z )',
      '  \\____/  ',
    ],
    // frame 1: 耳朵轻颤
    [
      '  /\\~/\\  ',
      ' ( -.- ) ',
      ' ( z  z )',
      '  \\____/  ',
    ],
    // frame 2: 身体微动
    [
      '  /\\_/\\  ',
      ' ( -.o ) ',
      ' ( z   z)',
      '  \\____/  ',
    ],
  ],
  awake: [
    [
      '  /\\_/\\  ',
      ' ( o.o ) ',
      ' (  ><  )',
      '  \\____/  ',
    ],
    // ...
  ],
  happy: [ /* ... */ ],
  working: [ /* ... */ ],
}
```

渲染循环 500ms tick，播 idle sequence: `[0,0,0,0,1,0,0,0,2,0,0,0]`

### 1.2 输入响应

| 用户行为 | 咪兔状态 |
|---------|---------|
| uid 输入框聚焦 | 睡 → 睁一只眼 (frame 过渡) |
| uid 输入有内容 | 完全睁眼，耳朵竖起 |
| uid 输入为空 | 继续睡觉 |
| 新用户提示出现 | 咪兔歪头 (好奇帧) |
| 回归用户提示出现 | 咪兔开心帧 |
| 点击登录 (loading) | 咪兔期待帧 |
| 登录成功 | 咪兔欢快帧 → 页面过渡 |

### 1.3 zzz 增强

当前 zzz 只在睡觉时播放。改为：

- **睡觉状态 (无输入)**：z z Z 持续飘出
- **输入中**：zzz 渐隐消失
- **空闲 > 5s**：zzz 渐显恢复

## Phase 2: 用户专属咪兔

### 2.1 确定性生成

```python
# agent_core/companion/bones.py

@dataclass
class CompanionBones:
    uid: str
    breed: str = "orange_tabby"   # 7 品种之一
    rarity: str = "common"
    eye: str = "·"
    ear: str = "cat"
    accent: str = "none"
    hat: str = "none"             # 帽子 (稀有度门控)
    quirk: str = "night_owl"      # 怪癖 (品种加权)
    shiny: bool = False
    color: str = "warm_gray"
    stats: dict[str, int] = field(default_factory=dict)
    # stats keys: CURIOSITY, SOCIAL, AFFECTION, PLAYFUL, LUCK

def roll_companion(uid: str) -> CompanionBones:
    rng = _mulberry32(_hash_uid(uid))
    rarity = _roll_rarity(rng)
    # 原始 roll (顺序不变, 保持已有用户稳定)
    eye = _pick(rng, EYES)
    ear = _pick(rng, EARS)
    accent = "none" if rarity == "common" else _pick(rng, ACCENTS)
    shiny = rng() < 0.01 or rarity == "legendary"
    color = _pick(rng, COLOR_PALETTES)
    stats = _roll_stats(rng, rarity)
    # 新增字段 (追加在原始 roll 之后)
    breed = _roll_breed(rng, rarity)   # 稀有度门控 + 品种权重
    hat = _roll_hat(rng, rarity)       # 稀有度门控
    quirk = _roll_quirk(rng, breed)    # 品种加权
    return CompanionBones(
        uid=uid, breed=breed, rarity=rarity,
        eye=eye, ear=ear, accent=accent, hat=hat,
        quirk=quirk, shiny=shiny, color=color, stats=stats,
    )
```

### 2.2 稀有度系统

```python
# agent_core/companion/species.py

RARITY_WEIGHTS = {
    "common":    60,   # 普通咪兔
    "uncommon":  25,   # 稀有咪兔
    "rare":      10,   # 珍稀咪兔
    "epic":       4,   # 史诗咪兔
    "legendary":  1,   # 传说咪兔
}

RARITY_COLORS = {
    "common":    "#8e8e93",  # 灰
    "uncommon":  "#30d158",  # 绿
    "rare":      "#409cff",  # 蓝
    "epic":      "#bf5af2",  # 紫
    "legendary": "#ff9f0a",  # 金
}

EYES  = ["·", "✦", "◉", "o", "♥", "☆"]
EARS  = ["cat", "rabbit", "mix"]   # 猫耳 / 兔耳 / 混合耳
ACCENTS = ["bow", "scarf", "glasses", "none", "crown", "bell"]
HATS = ["none", "crown", "tophat", "propeller", "halo", "wizard", "beanie", "tinyduck"]
COLOR_PALETTES = ["warm_gray", "cool_gray", "cream", "charcoal", "snow"]

# 7 品种, 带稀有度门控 — 见 companion-design/02-visual-design.md
BREED_WEIGHTS = {
    "orange_tabby": 30, "tuxedo": 20, "calico": 15,
    "siamese": 15, "black_cat": 10, "ragdoll": 8, "scottish_fold": 2,
}

# 13 怪癖, 带品种加权 — 见 companion-design/04-personality-system.md
QUIRKS = ["night_owl", "picky_eater", "chatterbox", "shy", "collector",
          "hyperactive", "sleepyhead", "glass_heart", "foodie",
          "clean_freak", "tsundere_extreme", "philosopher", "comedian"]

# 5 维性格属性 — 决定行为速率而非绝对值
STAT_NAMES = ["CURIOSITY", "SOCIAL", "AFFECTION", "PLAYFUL", "LUCK"]
```

#### 确定性选择的不可变约束

`_pick(rng, arr)` 通过 `arr[index]` 取值。hash 是稳定的，PRNG 序列也是稳定的 → 同一个 uid 对同一个 arr 永远命中同一个 index。

这意味着 **arr 的顺序决定所有用户的伴侣外观**。如果在列表中间插入或删除，index 全局偏移，所有老用户的外观都变了——等于把他们已经 "拥有" 的伴侣抢走。

**规则：**

| 操作 | 允许 | 做法 |
|------|------|------|
| 追加新项 | ✅ | `EYES.append("★")` — 只有 hash 命中新 index 的新/未分配用户受影响 |
| 废弃旧项 | ❌ | 不删除，替换占位: `EYES[3] = "_deprecated_"` |
| 中间插入 | ❌ | 永远不要 |
| 调序 | ❌ | 永远不要 |

这个约束在当前设计中**已经生效**。如果后续觉得靠 review 太弱，可以用 `tuple` 代替 `list` 从类型层面禁止写操作，追加时替换整个 tuple。

#### 前端 JS 版确定性生成

前端需要本地计算 bones 而不调 API，所以需要 JS 版的 hash + PRNG。与 Python 端共用完全相同的算法和 SALT，保证同一 uid 两端计算一致：

```ts
// scene/.../utils/companion-bones.ts

const SALT = "mitu-2026-companion";

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(rng: () => number, arr: readonly T[]): T {
  return arr[Math.floor(rng() * arr.length)];
}

export function rollCompanion(uid: string): CompanionBones {
  const rng = mulberry32(hashString(uid + SALT));
  const rarity = rollRarity(rng);
  const eye    = pick(rng, EYES);
  const ear    = pick(rng, EARS);
  const accent = rarity === "common" ? "none" : pick(rng, ACCENTS);
  const shiny  = rng() < 0.01 || rarity === "legendary";
  const color  = pick(rng, COLOR_PALETTES);
  const stats  = rollStats(rng, rarity);
  // 新增字段 (追加在原始 roll 之后, 保持 PRNG 序列)
  const breed  = rollBreed(rng, rarity);
  const hat    = rollHat(rng, rarity);
  const quirk  = rollQuirk(rng, breed);
  return {
    uid, breed, rarity,
    eye, ear, accent, hat, quirk,
    shiny, color, stats,
  };
}
```

枚举常量（`EYES`/`EARS`/`ACCENTS`/`COLOR_PALETTES`/`RARITY_WEIGHTS`）从后端 `species.py` 以 JSON 文件共享到前端构建流程。```

### 2.3 登录页揭示动画

1. 用户输入 uid
2. 前端本地计算 `roll_companion(uid)` → 得到 bones
3. 点击登录时播放揭示动画：
   - 画面震动
   - 稀有度星光闪烁（金色=传说，紫色=史诗...）
   - 新用户：显示 "这是你的专属咪兔！稀有度：★★★"
   - 回归用户：显示 "你的 咪兔 一直在等你！"

### 2.4 后端 API

```
GET /api/companion/{uid}
  → { bones: CompanionBones, hatched_at: str }

POST /api/companion/{uid}/hatch
  → 首次创建 companion 记录 (存储 soul)
```

Bones 始终从前端本地计算（不调 API），Soul 首次 hatch 后从后端获取。

## Phase 3: CompanionExtension (纳入 agent_core)

### 3.1 Extension 协议集成

**已确认的实际协议**（`agent_core/extensions/base.py:26` 和 `agent_core/memory/extension.py:23`）：

```python
# Extension Protocol — 4 个钩子
class Extension(Protocol):
    name: str
    async def on_event(self, ctx, evt: AgentEvent) -> None: ...
    async def on_before_agent_start(self, ctx, prompt, system_prompt) -> dict | None: ...
    async def on_before_tool_call(self, ctx, tool_call) -> dict | None: ...
    async def on_after_tool_call(self, ctx, tool_call, result, is_error) -> dict | None: ...

# MemoryExtension.on_event — 在 TurnEnd 时调用 store.remember()
# MemoryExtension 没有 add_on_remember 钩子，但也不需要——
# 伴侣的 on_event 收到同一个 TurnEnd，直接在 TurnEnd 分支里做气泡/空闲检测即可。
```

气泡/空闲检测不需要独立定时器。MemoryExtension 在 `TurnEnd` 时写入记忆，伴侣也在自己的 `TurnEnd` handler 里做空闲检测——同一个事件驱动两个扩展，零耦合。

```python
# agent_core/extensions/companion.py

from agent_core.core.events import (
    AgentEvent, TurnStart, TurnEnd, AgentEnd,
    ToolExecutionStart, ToolExecutionEnd,
)

class CompanionExtension:
    name = "companion"

    def __init__(self, bones: CompanionBones, memory_store: MemoryStore,
                 send_event: Callable[[CompanionEvent | CompanionBubbleEvent], None]):
        self.bones = bones
        self._memory = CompanionMemory(memory_store)
        self._observer = SilentObserver(self._memory)
        self._guide = GuideNPC(self._memory, self._observer)
        self._send = send_event
        self._mood = "idle"
        self._last_bubble_at: float = 0

    async def on_event(self, ctx: ExtensionContext, evt: AgentEvent) -> None:
        uid = self.bones.uid
        match evt:
            case TurnStart():
                self._mood = "listening"
                self._send(CompanionEvent("ear_perk", uid))
                await self._observer.on_prompt(uid, ctx.metadata.get("prompt", ""))

            case ToolExecutionStart(tool_name=name):
                self._mood = "working"
                self._send(CompanionEvent("busy", uid))
                await self._observer.on_tool_start(uid, name)

            case ToolExecutionEnd(is_error=True):
                self._mood = "concerned"
                self._send(CompanionBubbleEvent(uid,
                    Bubble("error_comfort", ttl_ms=8000)))

            case TurnEnd() | AgentEnd():
                self._mood = "happy"
                self._send(CompanionEvent("happy", uid))
                await self._observer.on_turn_end(uid)
                # ---- 气泡 + 空闲检测：与 MemoryExtension.remember() 同频 ----
                await self._check_bubble_and_idle(uid)

    async def _check_bubble_and_idle(self, uid: str) -> None:
        """TurnEnd 触发：检测空闲 + 决定是否弹气泡."""
        now = time.time()
        gap = now - self._observer.last_active_at
        if gap > 300:  # > 5 分钟空闲
            await self._observer.on_idle_return(uid, gap)
            self._mood = "sleeping"
            self._send(CompanionEvent("sleeping", uid))
        self._observer.last_active_at = now

        if now - self._last_bubble_at < 30:
            return
        bubble = await self._guide.decide_bubble(uid)
        if bubble:
            self._last_bubble_at = now
            self._send(CompanionBubbleEvent(uid, bubble))

    async def on_before_agent_start(self, ctx, prompt, system_prompt) -> None:
        await self._observer.on_session_start(ctx.session_id)
        return None
```

**类型定义补全**（设计中引用但未定义的类型）：

```python
@dataclass
class CompanionEvent:
    type: str     # "ear_perk" | "busy" | "happy" | "sleeping" | "concerned"
    uid: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class Bubble:
    text: str
    ttl_ms: int = 8000
    priority: str = "normal"  # "greeting" | "onboarding" | "suggestion" | "help" | "care" | "normal" | "low"

@dataclass
class CompanionBubbleEvent:
    uid: str
    bubble: Bubble
    type: str = "companion_bubble"
```

### 3.2 事件流

```
AgentEvent                     CompanionExtension.on_event()
────────────────────────────────────────────────────────────
TurnStart            ──►  情绪="listening" → 耳朵竖起
ToolExecutionStart   ──►  情绪="working"   → 忙碌 + observer 记录
ToolExecutionEnd     ──►  is_error? 安慰气泡 : noop
TurnEnd / AgentEnd   ──►  情绪="happy" + turn_end 记录
                            │
                            └── _check_bubble_and_idle()
                                  ├── gap > 5min → idle return → 打盹
                                  └── GuideNPC.decide_bubble() → SSE push

注意：MemoryExtension 也在 TurnEnd 时调用 store.remember()。
伴侣和记忆扩展被同一个事件驱动，无需显式耦合。
```

### 3.3 前端 SSE 推送

在现有 SSE 流上扩展一个 companion channel：

```json
// SSE event: companion
{
  "type": "companion",
  "uid": "alice",
  "event": "bubble",
  "data": {
    "text": "正在帮你搜索知识库...",
    "ttl_ms": 8000
  }
}
```

### 3.4 聊天页 Header 咪兔

将 `Header.tsx` 中的静态 logo 替换为 `HeaderCompanion`：

```tsx
// 替代当前的静态 <pre className="logo-art">
<HeaderCompanion uid={uid} />
```

- 空闲时轻微 fidget 动画
- streaming 时显示 "忙碌中" 表情
- 可点击互动 (/pet 触发爱心)

## 文件清单

### 新建

| 文件 | Phase | 说明 |
|------|-------|------|
| `agent_core/companion/__init__.py` | 2 | 公开 API + roll_companion |
| `agent_core/companion/bones.py` | 2 | 确定性生成引擎 |
| `agent_core/companion/species.py` | 2 | 枚举/权重/属性定义 |
| `agent_core/companion/sprites.py` | 1 | ASCII 精灵帧数据 |
| `agent_core/companion/memory.py` | 4 | CompanionMemory |
| `agent_core/companion/observer.py` | 4 | SilentObserver |
| `agent_core/companion/guide.py` | 4 | GuideNPC + 辅助函数 |
| `agent_core/companion/templates.py` | 4 | 气泡模板引擎 |
| `agent_core/companion/topic_extractor.py` | 4 | extract_topic_hint |
| `agent_core/companion/minigames/__init__.py` | 5 | MiniGame registry |
| `agent_core/companion/minigames/base.py` | 5 | MiniGame Protocol |
| `agent_core/companion/minigames/fishing/game.py` | 5 | 钓鱼游戏逻辑 |
| `agent_core/companion/minigames/fishing/fish_table.py` | 5 | 鱼类定义 |
| `agent_core/companion/minigames/fishing/rewards.py` | 5 | FeedingSystem |
| `agent_core/extensions/companion.py` | 3 | CompanionExtension |
| `scene/.../components/companion/CompanionSprite.tsx` | 1 | 精灵渲染引擎 |
| `scene/.../components/companion/CompanionBubble.tsx` | 3 | 气泡组件 |
| `scene/.../components/companion/LoginCompanion.tsx` | 1 | 登录页伴侣 |
| `scene/.../components/companion/HeaderCompanion.tsx` | 3 | 聊天页伴侣 |
| `scene/.../components/companion/minigames/MiniGameHost.tsx` | 5 | 小游戏宿主 |
| `scene/.../components/companion/minigames/FishingGame.tsx` | 5 | 钓鱼前端 |
| `scene/.../utils/companion-bones.ts` | 2 | 前端 JS 版 rollCompanion |
| `scene/.../stores/companion-store.ts` | 1 | 伴侣状态 (Zustand) |
| `scene/.../api/minigame_api.py` | 5 | 小游戏 HTTP API |
| `tests/companion/test_bones.py` | 2 | 确定性生成测试 |
| `tests/companion/test_sprites.py` | 1 | 精灵渲染测试 |
| `docs/companion-design.md` | — | 本文档 |

### 修改

| 文件 | Phase | 改动 |
|------|-------|------|
| `LoginPage.tsx` | 1 | 接入 LoginCompanion，替换静态咪兔 |
| `LoginPage.css` | 1 | 新增伴侣样式 |
| `Header.tsx` | 3 | 静态 logo → HeaderCompanion |
| `App.tsx` | 1 | 初始化 companion-store |
| `chat_assistant.py` | 3 | 创建时注册 CompanionExtension |
| `pyproject.toml` | 2 | 无新依赖 |

## Phase 4: 伴侣记忆 & 引路 NPC (后端驱动)

### 设计原则

前端只负责渲染精灵和气泡，**所有智能逻辑在 CompanionExtension 中完成**。前端负担增量接近零。

### 4.1 伴侣独立记忆

咪兔拥有自己独立的 `MemoryStore` 实例，与用户的 agent 记忆完全分离：

```
用户记忆 (MemoryExtension):
  user_id=alice → recall("编程偏好") → "喜欢用 Python"

伴侣记忆 (CompanionMemory):
  user_id=alice → recall("user_facts") → {
    "称呼": "小明",
    "常问话题": ["天气", "股票"],
    "最后活跃": "2026-06-04T20:30:00",
    "这次聊了多久": "45分钟",
    "今天问了几次": 12,
  }
```

```python
# agent_core/companion/memory.py

class CompanionMemory:
    """咪兔自己的记忆 — 观察用户，不参与 agent 推理."""

    def __init__(self, store: MemoryStore):
        self.store = store

    async def observe(self, uid: str, event: CompanionObservation) -> None:
        """记录咪兔观察到的事实."""
        await self.store.remember(
            user_id=uid,
            key=f"companion:{event.type}",
            content=event.payload,
        )

    async def recall_user_facts(self, uid: str) -> dict:
        """回忆关于用户的事实."""
        records = await self.store.recall(uid, "user_facts", limit=20)
        return _parse_facts(records)

    async def recall_conversation_summary(self, uid: str) -> str | None:
        """回忆最近对话的摘要."""
        records = await self.store.recall(uid, "conversation", limit=3)
        return records[0].content if records else None
```

### 4.2 观察者 — 咪兔看到什么

CompanionExtension 静默观察 agent 事件流，不打断推理，只记录结构化事实到伴侣记忆。

```python
# agent_core/companion/observer.py

@dataclass
class CompanionObservation:
    type: str            # "user_prompt" | "tool_use" | "turn_end" | "idle_return"
    timestamp: float
    summary: str
    metadata: dict

class SilentObserver:
    """静默观察 — 不打断 agent，只往伴侣记忆里写."""

    def __init__(self, memory: CompanionMemory):
        self.memory = memory
        self._first_seen_at: float | None = None
        self._session_count = 0
        self._prompt_count = 0
        self._tool_use_count = 0
        self.last_active_at: float = 0     # 由 _check_bubble_and_idle 更新

    # ---- 供 GuideNPC / compute_bond 查询 ----

    def session_duration(self) -> float:
        return time.time() - (self.last_active_at or time.time())

    def days_since_first_seen(self) -> int:
        if not self._first_seen_at:
            return 0
        return int((time.time() - self._first_seen_at) / 86400)

    @property
    def prompt_count(self) -> int: return self._prompt_count

    @property
    def session_count(self) -> int: return self._session_count

    # ---- Extension 事件回调 ----

    async def on_session_start(self, uid: str) -> None:
        if self._first_seen_at is None:
            self._first_seen_at = time.time()
        self._session_count += 1
        self.last_active_at = time.time()

    async def on_prompt(self, uid: str, prompt: str) -> None:
        self._prompt_count += 1
        topic = extract_topic_hint(prompt)
        if topic:  # 质量校验失败时跳过
            await self.memory.observe(uid, CompanionObservation(
                type="user_prompt",
                timestamp=time.time(),
                summary=topic,
                metadata={"len": len(prompt)},
            ))

    async def on_tool_start(self, uid: str, tool: str) -> None:
        self._tool_use_count += 1

    async def on_turn_end(self, uid: str) -> None:
        # turn_end 本身不产生 observation，气泡/空闲逻辑在
        # CompanionExtension._check_bubble_and_idle 中处理
        pass

    async def on_idle_return(self, uid: str, away_seconds: float) -> None:
        await self.memory.observe(uid, CompanionObservation(
            type="idle_return",
            timestamp=time.time(),
            summary=f"离开 {away_seconds:.0f}s 后回来",
            metadata={"away_s": away_seconds},
        ))
```

#### `extract_topic_hint()` — 规则提取，不调 LLM

```python
# agent_core/companion/topic_extractor.py

import re

# 短黑名单：匹配到这些词则跳过本次 observer 存储
_SKIP_WORDS = {"杀", "死", "炸", "黑", "破解", "攻击", "自杀", "赌博"}

def extract_topic_hint(prompt: str) -> str | None:
    """从用户输入提取 4-12 字意图摘要。质量校验失败返回 None."""
    # 规则 1: 取前 18 个非空字符作为候选
    cleaned = prompt.strip().replace("\n", " ")[:18]

    # 规则 2: 质量校验——含敏感词直接放弃
    for w in _SKIP_WORDS:
        if w in cleaned:
            return None

    # 规则 3: 太短不存
    if len(cleaned) < 4:
        return None

    # 规则 4: 截断到 12 字
    return cleaned[:12]
```

#### GuideNPC 辅助函数

```python
# agent_core/companion/guide.py

def _repeated_tool_in_row(observer: SilentObserver, tool: str, count: int) -> bool:
    """检查 observer 最近 N 次 tool_use 是否全是同一工具.
    简化实现：内存维护一个 deque(maxlen=count) 记录最近工具名."""
    ...

def _user_said_continue(observer: SilentObserver) -> bool:
    """最近一次 prompt 是否为上下文续接信号.
    简化实现：匹配正则 /^(继续|刚才|上次|接着|然后呢|go on)/i"""
    ...

def _days_ago(timestamp: float) -> int:
    """计算距今多少天."""
    return int((time.time() - timestamp) / 86400)
```

### 4.3 引路 NPC — 咪兔会说什么

基于观察到的记忆，咪兔在合适时机主动推送气泡。时机由后端规则引擎判断：

```python
# agent_core/companion/guide.py

class GuideNPC:
    """引路 NPC — 基于记忆生成引导性气泡."""

    def __init__(self, memory: CompanionMemory, observer: SilentObserver):
        self.memory = memory
        self.observer = observer

    async def decide_bubble(self, uid: str) -> Bubble | None:
        """判断当前是否需要弹气泡，以及气泡内容."""

        facts = await self.memory.recall_user_facts(uid)

        # === 回归欢迎 ===
        last_active = facts.get("最后活跃")
        if last_active and _days_ago(last_active) >= 1:
            return Bubble(
                text=f"你 {_days_ago(last_active)} 天没来了喵~ 上次我们在聊 {facts.get('上次话题')}",
                ttl_ms=12_000,
                priority="greeting",
            )

        # === 新用户引导 ===
        if facts.get("总提问次数", 0) <= 2:
            return Bubble(
                text="提示：按 / 可以切换模型，试试问我「帮我写一个脚本」吧！",
                ttl_ms=15_000,
                priority="onboarding",
            )

        # === 模式识别 ===
        if _repeated_tool_in_row(observer, "bash", count=3):
            return Bubble(
                text="你今天用了好多次终端呢，需要我帮你把这些命令写成脚本吗？",
                ttl_ms=10_000,
                priority="suggestion",
            )

        # === 上下文断裂检测 ===
        if _user_said_continue(observer):
            return Bubble(
                text="刚才说到哪儿了？看看我记的笔记——" + await self.memory.recall_conversation_summary(uid),
                ttl_ms=15_000,
                priority="help",
            )

        # === 系统状态提醒 ===
        if observer.session_duration() > 3600:
            return Bubble(
                text="你已经连续聊了 1 小时，要不要休息一下？咪兔也有点困了...",
                ttl_ms=10_000,
                priority="care",
            )

        # === 随机小贴士 (低概率，避免骚扰) ===
        if random.random() < 0.05:  # 5% 概率
            return Bubble(
                text=random.choice([
                    "偷偷告诉你，我还会记住你喜欢什么样的回答风格哦",
                    "你上次问的那个问题，后来解决了吗？",
                    "按 Ctrl+K 可以清空上下文，从头开始~",
                ]),
                ttl_ms=8_000,
                priority="low",
            )

        return None  # 不弹气泡
```

### 4.4 亲密度系统

咪兔与用户的关系随时间升温。亲密度影响气泡频率和内容：

```python
class BondLevel(IntEnum):
    STRANGER  = 0   # 首次见面 — 正式、引导式
    ACQUAINTANCE = 1 # 聊过几次 — 开始用"喵"
    FRIEND    = 2   # 熟悉 — 会开玩笑
    CLOSE     = 3   # 亲密 — 气泡更频繁、更随意

def compute_bond(observer: SilentObserver) -> BondLevel:
    """亲密度 = 总提问次数 + session 次数 + 时间跨度."""
    total_prompts = observer._prompt_count
    total_sessions = observer._session_count
    days_span = observer.days_since_first_seen()

    score = total_prompts * 1 + total_sessions * 10 + days_span * 2

    if score < 10:    return BondLevel.STRANGER
    if score < 50:    return BondLevel.ACQUAINTANCE
    if score < 200:   return BondLevel.FRIEND
    return BondLevel.CLOSE
```

不同亲密度下咪兔的说话方式：

| 亲密度 | 语气示例 |
|--------|---------|
| STRANGER | "你好！我是咪兔，你的 AI 伙伴。试试问我任何问题~" |
| ACQUAINTANCE | "回来啦！今天想聊什么喵？" |
| FRIEND | "哦你又来问我天气了！今天是想出门还是纯粹好奇🤔" |
| CLOSE | "第 47 次查天气！你是不是在策划什么秘密行动，嗯？" |

### 4.4.1 从记忆到熟悉感 — 咪兔怎么"越来越懂你"

单纯靠计数器（提问次数、天数）只能驱动亲密度等级，但**用户感知不到 "它记住了什么"**。真正的熟悉感来自咪兔在正确时机说出了一件只有"熟悉的人"才知道的事。

不需要 LLM。伴侣记忆存的是结构化小事实，气泡由规则 + 模板生成：

```
伴侣记忆存储                      咪兔在什么时候说出来
─────────────────────────────────────────────────────
user_facts:
  称呼: "小明"              →  回归登录时: "小明！三天没见了！"
  上次话题: "Python bug"     →  用户说 "继续" 时: "上次的 Python bug，你说要试试 pdb"
  常问话题: ["天气","股票"]   →  再次问天气时: "今天第四次了，我都能背出北京的天气了"
  偏爱模型: "sonnet"        →  切换模型时: "还是 sonnet 对吧？上次你说 haiku 太急"
  备注: "喜欢简洁回答"       →  回答过长时: "要不要我像上次一样精简一下？"

habit:
  活跃时段: "morning"       →  下午上线: "咦你今天下午才来，早上睡过头了？"
  每次开头: "查天气"        →  登录即推送: "北京今天 28 度，不用问了，直接告诉你"

session:
  本轮已提问: 12 次         →  12 次后: "你今天问了 12 个问题了，不累吗？"
  上一轮中断话题: "..."     →  新 session 开始时提供上下文恢复
```

模板引擎极简 —— 事实槽位 + 模板，不调 LLM：

```python
# agent_core/companion/templates.py

GREETING_TEMPLATES = {
    # (bond_min, max_days_away) → [模板列表]
    (BondLevel.STRANGER, 0): [
        "你好！我是咪兔，你的 AI 伙伴~",
    ],
    (BondLevel.ACQUAINTANCE, 1): [
        "回来啦{称呼}！昨天怎么没来喵~",
    ],
    (BondLevel.FRIEND, 3): [
        "{称呼}！！你都{离开天数}天没来看我了！",
        "失踪{离开天数}天的{称呼}终于出现了！我差点报警喵",
    ],
    (BondLevel.CLOSE, 1): [
        "{称呼}{称呼}{称呼}！想你了！",
        "刚才打了个盹就梦到你来了，结果你真的来了！",
    ],
}

def pick_greeting(facts: dict, bond: BondLevel, days_away: int) -> str:
    """基于记忆事实 + 亲密度 + 离开天数 选欢迎语."""
    templates = [
        t for (b, d), ts in GREETING_TEMPLATES.items()
        if b <= bond and d <= days_away
    ]
    template = random.choice(templates[-1])  # 选最匹配的那档
    return template.format(
        称呼=facts.get("称呼", ""),
        离开天数=days_away,
    )
```

**核心思路**：伴侣记忆存槽位值，模板填槽位，规则选模板。零 LLM 调用，每次气泡都有 "它是真的记得" 的感觉。

### 4.5 伴侣微代理

咪兔不需要独立的定时循环。它的 "思考" 由 `TurnEnd` 事件触发——与 MemoryExtension 写入记忆同频：

```
TurnEnd
    │
    ▼
companion._check_bubble_and_idle(uid)
    │
    ├── gap > 5min → idle return → 打盹表情 + SSE push
    ├── Observer 更新 last_active_at
    └── GuideNPC.decide_bubble() → 如有气泡 → SSE push
```

空闲期记忆不写、气泡不弹，自然避免了骚扰。

### 4.6 前端的最小变化

Phase 4 前端几乎不需要新增代码：

- `CompanionBubble.tsx` — 从 SSE 接收 bubble event，渲染气泡，ttl 后自动消失（Phase 3 已有）
- `CompanionSprite.tsx` — 新增 `bondLevel` → 微调表情/眨眼频率（可选）
- 其余逻辑全在后端

```tsx
// CompanionBubble.tsx — 极简实现
function CompanionBubble({ text, ttlMs, onDone }: Props) {
  useEffect(() => {
    const t = setTimeout(onDone, ttlMs);
    return () => clearTimeout(t);
  }, [ttlMs]);

  return (
    <div className="companion-bubble" role="status" aria-live="polite">
      <span className="companion-bubble-text">{text}</span>
    </div>
  );
}
```

前端新增加载不到 30 行代码。核心复杂度全部在后端的 `Observer + GuideNPC + CompanionMemory` 三位一体结构中。

### 4.7 与 agent 记忆的关系

```
┌─────────────────────────────────────────────────┐
│                  agent 记忆                       │
│  user_id=alice → recall("编程") → "偏好 Python"  │
│  用途: 增强 agent 推理, 提供上下文                 │
│  存储: Mem0 / OpenViking / InMemory               │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│                伴侣记忆 (独立)                     │
│  user_id=alice → recall("user_facts") → {         │
│    "称呼": "小明",                                │
│    "总提问": 47,                                  │
│    "最后活跃": "2026-06-04",                      │
│  }                                                │
│  用途: 驱动气泡 / 引导 / 亲密度                     │
│  存储: MemoryStore (复用已有的 mem0/openviking,       │
│        单用户几 KB)                                   │
└─────────────────────────────────────────────────┘
```

关键区别：agent 记忆用于**增强 LLM 推理**（需要语义检索），伴侣记忆用于**驱动交互行为**（结构化数据 + 计数器 + 简单规则）。

## Phase 5: 伴侣互动小游戏系统 (可扩展)

### 设计动机

模型回答需要时间（尤其是长推理 / 多工具调用）。这段时间用户只能盯着 streaming 文字，体验空白。如果可以在等待时和咪兔互动 —— 比如钓鱼给它吃 —— 等待时间就变成了乐趣。

### 5.1 扩展点架构

小游戏系统采用 **插件模式**：每个小游戏是一个自包含模块，通过统一接口挂载到伴侣系统。新增游戏不需要改动核心代码。

```
agent_core/companion/
├── minigames/                     # 小游戏插件目录
│   ├── __init__.py                # MiniGame Protocol + registry
│   ├── base.py                    # MiniGame 抽象基类
│   ├── fishing/                   # 钓鱼游戏
│   │   ├── __init__.py
│   │   ├── game.py                # 游戏逻辑 (纯 Python, 可前后端共享)
│   │   ├── fish_table.py          # 鱼类/稀有度表
│   │   └── rewards.py             # 奖励计算 (食物值 → 亲密度加速)
│   └── _template/                 # 新游戏模板
│       └── __init__.py
│
scene/.../components/companion/minigames/
├── MiniGameHost.tsx               # 小游戏宿主容器 (调度哪个游戏激活)
├── FishingGame.tsx                # 钓鱼前端渲染
└── _template.tsx                  # 新游戏前端模板
```

### 5.2 MiniGame Protocol

每个小游戏实现这个接口即可接入：

```python
# agent_core/companion/minigames/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

class GameTrigger(Enum):
    STREAMING  = "streaming"   # 模型生成中
    IDLE       = "idle"        # 空闲超过阈值
    MANUAL     = "manual"      # 用户主动点击

@dataclass
class GameConfig:
    name: str                          # "fishing"
    display_name: str                  # "钓鱼"
    icon: str                          # "🎣"
    triggers: list[GameTrigger]        # 在哪些时机激活
    max_duration_s: int = 120          # 单局最长时长
    cooldown_s: int = 60               # 两局间隔
    unlock_bond: int = 0               # 亲密度门槛 (0 = 无需门槛)

@dataclass
class GameReward:
    """一局结束后产出的奖励."""
    food_value: int          # 食物值 (喂给咪兔)
    bond_boost: float        # 亲密度加速倍数 (1.0 = 正常)
    items: list[str]         # 特殊道具名
    exp: int                 # 经验值

class MiniGame(ABC):
    """小游戏插件接口 — 纯逻辑，不含 IO，前后端同一份代码运行."""

    config: GameConfig

    @abstractmethod
    def start(self, rng: Callable[[], float], params: dict) -> dict:
        """用 seeded rng 初始化一局, 返回初始状态."""
        ...

    @abstractmethod
    def tick(self, state: dict, action: dict | None) -> dict:
        """每帧推进。action=None 表示无用户操作, state 中包含连续时间."""
        ...

    @abstractmethod
    def is_finished(self, state: dict) -> bool:
        """游戏是否结束."""
        ...

    @abstractmethod
    def collect_reward(self, state: dict) -> GameReward:
        """结算奖励."""
        ...
```

### 5.3 钓鱼游戏实现

```python
# agent_core/companion/minigames/fishing/game.py

class FishingGame(MiniGame):
    config = GameConfig(
        name="fishing",
        display_name="钓鱼",
        icon="🎣",
        triggers=[GameTrigger.STREAMING, GameTrigger.MANUAL],
        max_duration_s=90,
        cooldown_s=30,
    )

    def start(self, rng: Callable[[], float], params: dict) -> dict:
        """用 seeded rng 生成鱼塘."""
        rarity_bonus = params.get("rarity_bonus", 0)  # 由后端 /config 下发
        return {
            "phase": "waiting",
            "pond": self._generate_pond(rng, rarity_bonus),
            "bobber_position": int(rng() * 80 + 10),
            "bite_timer": rng() * 6.0 + 2.0,
            "fish_on_hook": None,
            "reel_tension": 0.0,
            "catches": [],
            "timer": 0.0,
            "_rng": rng,  # 后续 tick 中 _roll_fish 等需要用到
        }

    def tick(self, state: dict, action: dict | None) -> dict:
        state["timer"] += 0.1  # 100ms per tick
        rng = state["_rng"]

        match state["phase"]:
            case "waiting":
                if state["timer"] >= state["bite_timer"]:
                    state["phase"] = "biting"
                    state["fish_on_hook"] = self._roll_fish(state["pond"], rng)
                    state["bite_window"] = rng() * 0.9 + 0.6  # 0.6-1.5s

            case "biting":
                if action and action.get("type") == "reel":
                    if state["timer"] <= state["bite_timer"] + state["bite_window"]:
                        state["phase"] = "reeling"
                        state["reel_tension"] = 0.3
                    else:
                        state["phase"] = "missed"
                        state["fish_on_hook"] = None

            case "reeling":
                # 玩家持续点击/按住来收线
                if action and action.get("type") == "pull":
                    state["reel_tension"] = min(1.0, state["reel_tension"] + 0.05)
                else:
                    state["reel_tension"] = max(0.0, state["reel_tension"] - 0.02)

                if state["reel_tension"] >= 1.0:
                    state["phase"] = "caught"
                    state["catches"].append(state["fish_on_hook"])
                elif state["reel_tension"] <= 0.0:
                    state["phase"] = "missed"
                    state["fish_on_hook"] = None

            case "missed":
                if state["timer"] >= state["bite_timer"] + 3.0:
                    state["phase"] = "waiting"
                    state["bite_timer"] = state["timer"] + rng() * 4.5 + 1.5

            case "caught":
                if state["timer"] >= state["bite_timer"] + 2.0:
                    state["phase"] = "waiting"
                    state["bite_timer"] = state["timer"] + rng() * 4.5 + 1.5
                    state["fish_on_hook"] = None

        return state

    def is_finished(self, state: dict) -> bool:
        return state["timer"] >= self.config.max_duration_s

    def collect_reward(self, state: dict) -> GameReward:
        total_food = sum(f.food_value for f in state["catches"])
        rarest = max((f.rarity_rank for f in state["catches"]), default=0)
        return GameReward(
            food_value=total_food,
            bond_boost=1.0 + rarest * 0.25,   # 稀有鱼加倍
            items=[f.name for f in state["catches"]],
            exp=total_food * (1 + rarest),
        )

    def _generate_pond(self, rng, bonus: int) -> list["FishDef"]:
        return _roll_fish_table(rng, bonus)

    def _roll_fish(self, pond: list["FishDef"], rng) -> "FishDef":
        roll = rng()
        cumulative = 0
        total = sum(f.appear_weight for f in pond)
        for f in pond:
            cumulative += f.appear_weight / total
            if roll <= cumulative:
                return f
        return pond[-1]
```

### 5.4 鱼类表

```python
# agent_core/companion/minigames/fishing/fish_table.py

@dataclass
class FishDef:
    name: str
    emoji: str
    rarity: str          # common | uncommon | rare | epic | legendary
    rarity_rank: int     # 0-4
    food_value: int      # 喂给咪兔的食物值
    appear_weight: int   # 出现权重
    sprite: str          # 单行 ASCII (钓鱼时显示在浮标旁)

FISH_TABLE: list[FishDef] = [
    # 普通 — 80% 概率池
    FishDef("小虾米",   "🦐", "common",    0,  5,  40, "~ <><"),
    FishDef("鲫鱼",     "🐟", "common",    0,  8,  30, "<><"),
    FishDef("小螃蟹",   "🦀", "common",    0,  6,  20, "~ v.v ~"),

    # 罕见 — 15% 概率池
    FishDef("鲤鱼",     "🐠", "uncommon",  1, 15,  40, "><>"),
    FishDef("鱿鱼",     "🦑", "uncommon",  1, 18,  30, "~<O>~"),
    FishDef("金鱼",     "🔶", "uncommon",  1, 12,  25, "~<><~"),

    # 稀有 — 4% 概率池
    FishDef("三文鱼",   "🐡", "rare",      2, 30,  35, "><<<>"),
    FishDef("灯笼鱼",   "🎃", "rare",      2, 35,  25, "~<O>~"),

    # 史诗 — 0.8% 概率池
    FishDef("电鳗",     "⚡", "epic",      3, 60,  40, "~zzZ~"),
    FishDef("锦鲤",     "🎏", "epic",      3, 50,  35, "><<<>>"),

    # 传说 — 0.2% 概率池
    FishDef("金龙鱼",   "🐉", "legendary", 4, 100, 50, "~<O>~"),
    FishDef("美人鱼",   "🧜", "legendary", 4, 120, 30, "><O><"),
]
```

### 5.5 喂食 → 成长

钓鱼产出 → 喂给咪兔 → 加速亲密度成长：

```python
# agent_core/companion/minigames/fishing/rewards.py

class FeedingSystem:
    """咪兔吃了鱼会怎样."""

    def feed(self, reward: GameReward, companion: CompanionBones,
             bond: BondLevel, observer: SilentObserver) -> FeedingResult:

        # 食物值 → 经验值转换
        exp_gain = reward.food_value * reward.bond_boost

        # 亲密度加速：钓鱼获得的 exp 直接加成
        bond_progress = exp_gain * 0.5

        # 咪兔反应
        if reward.food_value >= 100:
            reaction = "im_so_full"      # 咪兔撑到翻肚皮
            bubble = "嗝... 太饱了喵... 但是超好吃！"
        elif reward.food_value >= 50:
            reaction = "yummy"
            bubble = "好吃！再来一条！"
        elif reward.food_value >= 10:
            reaction = "happy_eat"
            bubble = "啊~ 谢谢你！"
        else:
            reaction = "nibble"
            bubble = "虽然少但还是很开心~"

        # 特殊道具
        if "金龙鱼" in reward.items:
            bond_progress *= 2.0
            bubble = "!!!! 金色的鱼 !! 你是钓鱼天才吗 !!"

        if "美人鱼" in reward.items:
            # 传说级: 直接跳过一级亲密度
            bond_progress = 999
            bubble = "..........美人鱼？! 你...你是认真的吗？"

        return FeedingResult(
            reaction=reaction,
            bubble=bubble,
            bond_progress=bond_progress,
            items=reward.items,
        )
```

### 5.6 激活时机

```
模型 streaming 中
    ├── streaming < 3s  → 不显示
    ├── streaming 3-15s → 显示小图标 "🎣 钓鱼等一会儿"
    └── streaming > 15s → 自动展开钓鱼面板

用户主动点击
    └── Header 咪兔旁边的 "🎣" 按钮 (随时可玩)
```

```tsx
// MiniGameHost.tsx
function MiniGameHost({ uid, isStreaming, streamingDuration }: Props) {
  const [activeGame, setActiveGame] = useState<string | null>(null);

  useEffect(() => {
    if (isStreaming && streamingDuration > 15 && !activeGame) {
      setActiveGame(pickAvailableGame(registry));
    }
    if (!isStreaming && activeGame) {
      const t = setTimeout(() => setActiveGame(null), 10_000);
      return () => clearTimeout(t);
    }
  }, [isStreaming, streamingDuration]);

  if (!activeGame) return null;
  return <ActiveGameComponent game={activeGame} uid={uid}
    onDone={() => setActiveGame(null)} />;
}
```

### 5.7 前后端游戏通信 (种子 + 重放)

游戏逻辑全在前端本地运行，后端只做两件事：下发带签名的随机种子、结算时重放验证并发放奖励。零网络延迟，零后端状态管理。

```
前端(FishingGame.tsx)                     后端
      │                                      │
      │── GET /api/minigame/config ─────────► │
      │◄── { fish_table, 种子, 签名 }        │ 种子 = HMAC(uid + game + time, secret)
      │                                      │ 签名防篡改
      │   本地初始化 PRNG(种子)                │ (后端无状态，不维护实例)
      │   跑完整钓鱼循环                        │
      │   所有随机由本地 PRNG 产出              │
      │                                      │
      │── POST /api/minigame/feed ──────────► │
      │   { 种子, 签名, 操作序列, 结果 }       │ 重放验证:
      │                                      │   PRNG(种子) 重跑一遍
      │◄── { valid, reaction, bubble,        │   → 确认结果与提交一致
      │       bond_progress, items } ──────── │   → 发放奖励
```

**种子生成**（后端，每次游戏开始前调用一次）：

```python
import hmac, hashlib, json, time

MINIGAME_SECRET = os.environ["MINIGAME_SECRET"]  # 服务端密钥，不暴露

@router.get("/api/minigame/config")
async def get_game_config(uid: str, game: str = "fishing"):
    seed_input = f"{uid}:{game}:{int(time.time())}"
    seed = int(hashlib.sha256(seed_input.encode()).hexdigest()[:16], 16)
    signature = hmac.new(
        MINIGAME_SECRET.encode(),
        f"{uid}:{game}:{seed}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]

    return {
        "game": game,
        "seed": seed,           # 前端用这个初始化本地 PRNG
        "signature": signature, # 结算时回传，后端验证
        "params": _game_params(game),  # fish_table / 难度 / 时长
    }
```

**前端本地游戏循环**（使用后端下发的种子）：

```ts
// MiniGameHost.tsx — 游戏宿主
async function startGame(uid: string, game: string) {
  const res = await fetch(`/api/minigame/config?uid=${uid}&game=${game}`);
  const { seed, signature, params } = await res.json();

  const rng = mulberry32(seed);  // 与 bones 相同的 PRNG
  const state = FishingGame.start(rng, params);
  const actions: GameAction[] = [];

  // 本地跑完整游戏循环 (setInterval 100ms)
  const timer = setInterval(() => {
    const action = pendingAction;  // 用户操作或 null
    const nextState = FishingGame.tick(state, action);
    if (action) actions.push(action);
    render(nextState);

    if (FishingGame.isFinished(nextState)) {
      clearInterval(timer);
      submitAndFeed(uid, game, seed, signature, actions, nextState);
    }
    state = nextState;
  }, 100);
}

async function submitAndFeed(
  uid: string, game: string, seed: number, signature: string,
  actions: GameAction[], finalState: GameState,
) {
  const result = FishingGame.collectReward(finalState);
  const res = await fetch("/api/minigame/feed", {
    method: "POST",
    body: JSON.stringify({ uid, game, seed, signature, actions, result }),
  });
  const { valid, reaction, bubble, bond_progress, items } = await res.json();
  if (!valid) { /* 重试或放弃 */ }
  showReaction(reaction, bubble);
}
```

**后端重放验证**（结算时）：

```python
@router.post("/api/minigame/feed")
async def feed_companion(data: dict):
    uid, game, seed, signature = data["uid"], data["game"], data["seed"], data["signature"]
    actions, claimed_result = data["actions"], data["result"]

    # 1. 验签 — 防篡改 seed
    expected_sig = hmac.new(
        MINIGAME_SECRET.encode(),
        f"{uid}:{game}:{seed}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(403, "签名无效")

    # 2. 重放 — 用同一种子重跑，确认结果一致
    game_cls = get_game(game)
    rng = mulberry32(seed)
    state = game_cls.start(rng, _game_params(game))
    for action in actions:
        state = game_cls.tick(state, action)
    replayed = game_cls.collect_reward(state)

    if replayed != claimed_result:
        raise HTTPException(400, "结果验证失败")

    # 3. 发放奖励
    bones = roll_companion(uid)
    feeding = FeedingSystem().feed(replayed, bones, ...)
    return {"valid": True, "reaction": feeding.reaction, "bubble": feeding.bubble,
            "bond_progress": feeding.bond_progress, "items": feeding.items}
```

**为什么这个方案隔离性好**：

- fish_table、稀有度加成、难度参数全部在后端 `/config` 下发，前端不硬编码任何业务规则
- 新增游戏类型只需加一个 `_game_params(game)` 分支
- 后端不持有任何游戏实例，无内存泄漏，重启不影响进行中的游戏
- 种子签名保证前端不能伪造运气（roll 100 次挑最好的提交）

**为什么对所有类型游戏都适用**：

| 游戏 | 种子决定 | 操作序列 |
|------|---------|---------|
| 🎣 钓鱼 | 鱼塘组成、咬钩时机、鱼品种 | `[{t:1.2, a:"reel"}, {t:1.5, a:"pull"}, ...]` |
| 🌱 种猫草 | 发芽速度、稀有变异概率 | `[{t:0, a:"plant"}, {t:3600, a:"water"}, ...]` |
| 🧩 拼图 | 初始布局 | `[{move: [3,7]}, {move: [1,4]}, ...]` |
| 💤 哄睡 | 入睡难度、轻拍节奏 | `[{t:0.5, a:"tap"}, {t:2.1, a:"tap"}, ...]` |

不兼容的类型（多人在线、依赖外部实时数据、纯反应速度类）不在当前设计范围。

### 5.8 前端渲染 (轻量)

钓鱼游戏前端只需要一个 200 行的简单组件：

```
┌──────────────────────────────────┐
│  🎣 钓鱼中...    模型还在思考...  │
│                                  │
│    ~~~~  ~~~~  ~~~~  ~~~~        │  ← 水面波纹
│          ○                       │  ← 浮标 (晃动动画)
│    ~~~~  ~~~~  ~~~~  ~~~~        │
│         /|\                      │  ← 鱼影 (bite 时出现)
│    ~~~~  ~~~~  ~~~~  ~~~~        │
│                                  │
│  [  收线!  ]  ← 鱼咬钩时出现按钮   │
│                                  │
│  已钓到: 🦐 🐟 🐠                │  ← 战利品栏
│  剩余时间: 45s                    │
└──────────────────────────────────┘
```

纯 CSS 动画（水面波纹、浮标晃动）+ 少量 JS（咬钩计时、收线交互）。不需要 canvas，不需要额外依赖。

### 5.9 扩展点 — 如何新增小游戏

在 `minigames/` 下新建目录，实现 `MiniGame` 接口，注册到 registry：

```python
# agent_core/companion/minigames/__init__.py

_registry: dict[str, type[MiniGame]] = {}

def register(game_cls: type[MiniGame]) -> type[MiniGame]:
    _registry[game_cls.config.name] = game_cls
    return game_cls

def get_game(name: str) -> type[MiniGame] | None:
    return _registry.get(name)

def list_games(bond_level: int) -> list[GameConfig]:
    return [
        g.config for g in _registry.values()
        if g.config.unlock_bond <= bond_level
    ]

# 注册内置游戏
from agent_core.companion.minigames.fishing import FishingGame
register(FishingGame)
```

新增游戏只需：

1. 在 `minigames/<name>/` 下实现 `MiniGame` 子类
2. 前端创建一个对应的渲染组件
3. 调用 `register(MyGame)` 注册

其他可扩展的小游戏创意：

| 游戏 | 触发时机 | 简单描述 |
|------|---------|---------|
| 🎣 钓鱼 | streaming 中 | 等模型回答时钓鱼喂咪兔 |
| 🌱 种猫草 | idle 状态 | 种猫薄荷，长好了咪兔会很开心 |
| 🧩 拼图 | 主动点击 | 用咪兔的 ASCII 像素拼图，完成有奖励 |
| 💤 哄睡 | 空闲 > 5min | 点 zzz 哄咪兔睡觉，获得 "安眠"buff |
| 🎀 换装 | 亲密度 ≥ FRIEND | 解锁配饰商店，给咪兔换帽子/围巾/蝴蝶结 |
| 🏆 成就墙 | 全天候 | 系统自动追踪里程碑，如 "钓了 100 条鱼" |

### 5.10 与整体系统的关系

```
┌───────────────────────────────────────────────────────┐
│                    agent 主循环                         │
│  用户提问 → LLM streaming → 工具执行 → 回答             │
│       │                                                │
│       ▼                                                │
│  CompanionExtension.on_event(TurnEnd)                   │
│       │                                                │
│       ├── 情绪更新 + observer 记录                       │
│       └── _check_bubble_and_idle() → SSE push           │
│                                                        │
│                    ┌──────────────┐                     │
│  GET /minigame     │ MiniGame     │ ← streaming 中激活  │
│  /config           │ Host (前端)  │                     │
│  ──► 种子+签名     └──────┬───────┘                     │
│                           │                             │
│                    前端本地 PRNG(种子)                    │
│                    跑完整游戏循环                         │
│                           │                             │
│  POST /minigame           ▼                             │
│  /feed  ──► 重放验证 → FeedingSystem                    │
│              ├── food_value → bond_progress              │
│              ├── items → 特殊效果                         │
│              └── reaction → 咪兔气泡                      │
└───────────────────────────────────────────────────────┘
```

小游戏完全独立于 agent 推理流程。前端本地跑游戏（零延迟），后端只在下发种子和结算奖励时介入。

## 可玩性总览

| 系统 | 触发 | 前端负担 | 可玩性 |
|------|------|----------|--------|
| 稀有度揭示 | 登录瞬间 | 低（CSS 动画） | 抽卡般的惊喜 |
| 多帧动画 | 实时 500ms tick | 低（纯渲染） | 感觉"活"的 |
| 情绪反馈 | agent 事件 | 低（状态切换） | 陪伴感 |
| 气泡聊天 | 后端推送 | 极低（渲染文本） | 引导 + 趣味 |
| 伴侣记忆 | 静默观察 | 零 | 关系演化 |
| 亲密度 | 累计统计 | 零 | 养成感 |
| 引路 NPC | 规则触发 | 极低 | 探索引导 |
| 🎣 钓鱼 | streaming 等待 | 低（纯 CSS 动画） | 打发等待时间 |
| 🌱 扩展点 | MiniGame Protocol | 低（插件式接入） | 无限扩展 |

## 已知问题 & 隐患

### 设计已解决的

| 问题 | 方案 | 状态 |
|------|------|------|
| 伴侣记忆重启失忆 | `CompanionMemory` 接收 `MemoryStore` 注入，复用已有的 mem0/openviking | 设计完成 |
| 亲密度计数器不持久化 | 计数器和 `first_seen_at` 写入伴侣记忆，Observer 初始化时恢复 | 设计完成 |
| `extract_topic_hint` 质量兜底 | 长度 ≤12、敏感词黑名单、去重，校验失败跳过存储 | 已实现 |
| 气泡静音 | Header 铃铛 toggle，session 级 | 设计完成 |
| 小游戏状态归属 | 前端本地 PRNG(种子) 跑完整游戏，后端重放验证 | 设计完成 |
| Soul 生成时机 | 首次 session 后台异步生成，SSE 静默推送 | 设计完成 |
| 过期清理 | FIFO 环形缓冲区，每用户最多 200 条 | 设计完成 |
| 多 tab | 前端 `BroadcastChannel` 选举 active tab，与 SSE session 管理协同修 | 设计完成 |
| PRNG 双端实现 | 枚举通过 JSON 共享到前端构建流程，算法同步 | 设计完成 |

### 实施时才需要补的

| 项目 | 说明 |
|------|------|
| `FeedingResult` dataclass | Phase 5，仅 FeedingSystem 使用 |
| `_roll_fish_table(rng, bonus)` | Phase 5，从 FISH_TABLE 按权重抽鱼 |
| `_parse_facts()` | Phase 4，将 MemoryStore 的 records 转成 dict |
| `_repeated_tool_in_row` / `_user_said_continue` / `_days_ago` | Phase 4，签名已定，实施时写 body |
| `_game_params(game)` | Phase 5，返回 fish_table / 时长 / 稀有度加成 |

---

## 成熟度评估

| Phase | 成熟度 | 关键缺口 |
|-------|--------|---------|
| 1 登录页增强 | 80% | awake/happy/working 帧未设计，动画参数未指定 |
| 2 用户专属咪兔 | 85% | 揭示动画帧序列未定义 |
| 3 CompanionExtension | 85% | `send_event` 回调在 chat_assistant 层的注入点未指定 |
| 4 伴侣记忆 & NPC | 75% | 4 个辅助函数只有签名 + `_parse_facts` 未实现 |
| 5 小游戏系统 | 70% | FeedingResult 定义 + `_roll_fish_table` 实现 |
| **整体** | **78%** | 方案闭环，Phase 1-2 可直接实施 |

## 实施顺序

```
Phase 1 (2-3h):
  └── LoginCompanion.tsx + CompanionSprite.tsx +
      companion-store.ts + LoginPage 改造
      目标: 咪兔有动画、响应输入、登录瞬间有庆祝

Phase 2 (2-3h):
  └── agent_core/companion/ + 后端 API +
      前端 roll_companion + 稀有度揭示
      目标: 每个 uid 看到不同的咪兔，有稀有度

Phase 3 (3-4h):
  └── CompanionExtension + Header 咪兔 +
      SSE companion channel + 气泡
      目标: 咪兔伴随整个 session，实时反应
```
