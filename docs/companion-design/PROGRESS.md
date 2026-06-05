# 咪兔伴侣实现进度

> 文档日期: 2026-06-05
> 设定集: [`companion-design/`](./companion-design/)

## 进度总览

| 层 | 完成度 | 说明 |
|----|:--:|------|
| 后端 — 确定性生成 | 90% | bones/species 完成，breed/quirk/hat 已对接 |
| 后端 — Extension 事件驱动 | 70% | 基础 mood + bubble 规则完成，情绪状态机/里程碑/互动链未实现 |
| 后端 — 伴侣记忆 | 60% | Observer + GuideNPC + 模板完成，冷落/STYLE/日记未实现 |
| 后端 — 小游戏 | 60% | 钓鱼游戏协议+逻辑完成，前端宿主/API 结算未实现 |
| 前端 — 登录页伴侣 | 60% | 多帧动画+5 mood+稀有度揭示，仅有基础猫精灵无品种差异 |
| 前端 — 聊天页伴侣 | 20% | 仅有 Header 静态 logo，未替换为 CompanionSprite |
| 前端 — 品种精灵库 | 5% | 仅有基础 4 行猫精灵，7 品种 10 帧的 ASCII 库未接入 |
| 设定文档 | 95% | 14 份文档完整，缺 SSE schema + 存储格式规格 |

---

## 一、已实现详情

### 1.1 确定性生成 (`agent_core/companion/`)

| 功能 | 状态 | 文件 |
|------|:--:|------|
| FNV-1a hash + mulberry32 PRNG | ✅ | `bones.py` |
| 5 级稀有度加权随机 | ✅ | `bones.py` |
| 5 维性格 stat (CURIOSITY/SOCIAL/AFFECTION/PLAYFUL/LUCK) | ✅ | `species.py`, `bones.py` |
| 7 品种 + 稀有度门控 | ✅ | `species.py` (BREED_RARITY_GATE) |
| 13 怪癖 + 品种加权 | ✅ | `species.py` (QUIRK_BREED_BONUS) |
| 帽子 + 配饰系统 | ✅ | `species.py` (HATS, ACCENTS) |
| 闪亮判定 (1% + legend 强制) | ✅ | `bones.py` |
| 眼睛 / 耳朵 / 颜色随机 | ✅ | `bones.py` |
| append-only PRNG 序列 | ✅ | 新 roll 追加在末尾, 已有用户不受影响 |
| `/api/companion/{uid}` HTTP endpoint | ✅ | `scene/http_sse/server.py` |

### 1.2 CompanionExtension (`agent_core/extensions/companion.py`)

| 功能 | 状态 | 触发 |
|------|:--:|------|
| TurnStart → 竖耳 (ear_perk) | ✅ | 每次用户提问 |
| ToolExecStart → 忙碌 (busy) | ✅ | 工具调用开始 |
| ToolExecEnd(is_error) → 担心气泡 | ✅ | 工具执行失败 |
| TurnEnd/AgentEnd → 开心 (happy) | ✅ | 每次 turn 结束 |
| 空闲 > 5min → 打盹 (sleeping) | ✅ | idle detection |
| GuideNPC.decide_bubble() | ✅ | TurnEnd 触发，30s CD |
| 新用户引导气泡 | ✅ | prompt_count ≤ 2 |
| 回归欢迎气泡 (含离开天数) | ✅ | 基于 CompanionMemory |
| 重复工具提醒 (bash ×3) | ✅ | observer.repeated_tool() |
| 长 session 提醒 (>1h) | ✅ | observer.session_duration() |
| 随机贴士 (3% 概率) | ✅ | pick_idle_tip() |

### 1.3 伴侣记忆 (`agent_core/companion/`)

| 功能 | 状态 | 文件 |
|------|:--:|------|
| CompanionMemory (独立 MemoryStore) | ✅ | `memory.py` |
| SilentObserver (静默观察) | ✅ | `observer.py` |
| 话题提取 (规则, 不调 LLM) | ✅ | `topic_extractor.py` |
| 亲密度计算 (BondLevel STRANGER→CLOSE) | ✅ | `templates.py` |
| 欢迎语模板 (按 bond + days_away) | ✅ | `templates.py` |
| 工具建议模板 | ✅ | `templates.py` |
| observer 计数器 (prompt/tool/session) | ✅ | `observer.py` |

### 1.4 小游戏 (`agent_core/companion/minigames/`)

| 功能 | 状态 | 文件 |
|------|:--:|------|
| MiniGame Protocol (基类) | ✅ | `base.py` |
| FishingGame (5 阶段状态机) | ✅ | `fishing/game.py` |
| FishTable (12 种鱼, 5 稀有度) | ✅ | `fishing/fish_table.py` |
| FeedingSystem (喂食→反应) | ✅ | `fishing/rewards.py` |
| 小游戏 registry | ✅ | `minigames/__init__.py` |

### 1.5 前端 (`scene/http_sse/static/src/`)

| 功能 | 状态 | 文件 |
|------|:--:|------|
| Zustand companion-store | ✅ | `stores/companion-store.ts` |
| LoginCompanion (5 mood 动画) | ✅ | `components/companion/LoginCompanion.tsx` |
| CompanionSprite (500ms tick, 15-step idle seq) | ✅ | `components/companion/CompanionSprite.tsx` |
| 稀有度揭示动画 | ✅ | `LoginCompanion.tsx` |
| 登录页 CSS 样式 | ✅ | `LoginCompanion.css` |
| SSE companion channel 消费 | ✅ | `server.py` (后端推送, 前端接收) |

### 1.6 设定文档 (`docs/companion-design/`)

| 文档 | 状态 |
|------|:--:|
| README (架构 + 索引) | ✅ |
| 01 角色定位 | ✅ |
| 02 视觉设定 | ✅ |
| 03 动画系统 | ✅ |
| 04 性格系统 | ✅ |
| 05 稀有度系统 | ✅ |
| 06 亲密度与成长 | ✅ |
| 07 互动系统 | ✅ |
| 08 情绪状态机 | ✅ |
| 09 日周期 | ✅ |
| 10 里程碑系统 | ✅ |
| 11 命名系统 | ✅ |
| 12 品种角色卡 | ✅ |
| 13 形象演化与媒体 | ✅ |
| 附录 精灵帧库 | ✅ |

---

## 二、未实现清单 (按优先级)

### P0 — 阻断完整体验

| # | 内容 | 对应设定 | 工作量 |
|---|------|---------|:--:|
| 1 | **前端品种精灵库** — 7 品种 × 10 帧的 ASCII 接入 CompanionSprite | §02, §03, 附录 | 中 |
| 2 | **聊天页 Header 伴侣** — 用 HeaderCompanion 替换静态 logo | 原设计 Phase 3 | 低 |
| 3 | **前端 JS 版 roll_companion** — 前端本地算 bones (目前依赖 API) | 原设计 Phase 2 §2.2 | 中 |

### P1 — 核心体验增量

| # | 内容 | 对应设定 | 工作量 |
|---|------|---------|:--:|
| 4 | **情绪状态机** — 6 状态 + 转换表 + 衰减 + 叠加规则 | §08 | 中 |
| 5 | **动态属性层** — mood/energy/attention 正式定义 + tick 驱动 | §04 末尾, (缺独立文档) | 中 |
| 6 | **品种角色卡集成** — 7 品种的行为差异在 guide/memory 中生效 | §12 | 中 |
| 7 | **品种专属气泡** — 橘猫说吃、暹罗话唠、黑猫说谜语 | §12 | 低 |

### P2 — 长期留存

| # | 内容 | 对应设定 | 工作量 |
|---|------|---------|:--:|
| 8 | **STYLE 分支** — TECH_PARTNER/COMPANION/MUSE/LIBRARIAN 判定 | §06 | 中 |
| 9 | **里程碑系统** — 30+ 触发条件 + 叙事模板 | §10 | 中 |
| 10 | **冷落衰减** — days_away → 状态变化 + 回归动画 | §06 | 低 |
| 11 | **日周期** — 7 时段 energy/mood 乘数 | §09 | 低 |
| 12 | **形象演化** — kitten/adult/soulmate 三阶段帧 | §13 | 低 |

### P3 — 锦上添花

| # | 内容 | 对应设定 | 工作量 |
|---|------|---------|:--:|
| 13 | **互动连锁** — InteractionChain DSL + 5 条内置 chain | §07 | 中 |
| 14 | **隐藏互动** — 10 条彩蛋 | §07 | 低 |
| 15 | **闪亮粒子特效** — 前端 ＊ 随机渲染 | §02 | 低 |
| 16 | **LLM 命名** — hatch 时生成 name + personality | §11 | 低 |
| 17 | **小游戏前端宿主** — MiniGameHost + FishingGame UI | 原设计 Phase 5 | 高 |
| 18 | **生图 prompt 组装** — compose_visual_prompt() | §13 | 低 |

---

## 三、设定文档 vs 代码对齐状态

| 设定文档定义 | 代码实现 | 对齐？ |
|------------|---------|:--:|
| 7 品种 + 权重 | `BREEDS`, `BREED_WEIGHTS` | ✅ |
| 13 怪癖 + 品种加权 | `QUIRKS`, `QUIRK_BREED_BONUS` | ✅ |
| 5 维 stat (EN) | `STAT_NAMES = ["CURIOSITY", ...]` | ✅ |
| 帽子 HATS | `HATS` | ✅ |
| 稀有度门控品种 | `BREED_RARITY_GATE` | ✅ |
| 品种角色卡 (行为参数) | — | ❌ 仅定义, 未在代码中引用 |
| 情绪状态机 (6 状态) | `CompanionExtension` 仅有 5 个 mood 字符串 | 🟡 简化版 |
| 气泡模板按 breed/Style 分 | `templates.py` 仅通用欢迎语 | 🟡 仅通用 |
| 互动连锁 | — | ❌ |
| 日周期 | — | ❌ |
| 里程碑 | — | ❌ |
| kitten/SOULMATE 帧 | 前端仅有通用 5 mood 猫 | ❌ |
