# 咪兔伴侣实现进度

> 文档日期: 2026-06-06

## 进度总览

| 层 | 完成度 | 说明 |
|----|:--:|------|
| 后端 — 确定性生成 | 95% | bones/species/breed/quirk/hat/stats 全部完成 |
| 后端 — Extension 事件驱动 | 85% | EmotionFSM + decay loop + 日周期 + 品种气泡完成 |
| 后端 — 伴侣记忆 | 65% | Observer + GuideNPC + 模板完成，冷落/STYLE 未实现 |
| 后端 — 小游戏 | 75% | 钓鱼协议+逻辑+API+结算完成；api/minigame/list 未加 |
| 前端 — 登录页伴侣 | 80% | breed selector + rarity reveal + kitten/adult stage + shiny 粒子 |
| 前端 — 聊天页 Header | 80% | Sprite + bubble + dock + 3 games (fish/catch/tap) + ResizeObserver anchor |
| 前端 — 品种精灵库 | 80% | 7品种×5mood×3帧，variant=header 截断为 3 行 |
| 设定文档 | 100% | 23 份核心 + 附录（协议/预览） |

---

## 一、已实现

### 1.1 后端 (`agent_core/`)

| 系统 | 关键文件 |
|------|---------|
| 确定性生成 (hash+PRNG) | `companion/bones.py` |
| 7品种+13怪癖+5属性+帽子+配饰 | `companion/species.py` |
| EmotionFSM (6状态+转换+衰减+品种参数) | `companion/state_machine.py` |
| DailyRhythm (7时段+quirk覆盖) | `companion/daily_rhythm.py` |
| CompanionExtension (事件→FSM→SSE) | `extensions/companion.py` |
| GuideNPC (品种专属欢迎/贴士/工具观察) | `companion/guide.py`, `templates.py` |
| Observer + Memory | `companion/observer.py`, `memory.py` |
| LLM 命名 (hatch endpoint) | `companion/naming.py` |
| 钓鱼小游戏 (协议+逻辑+API) | `companion/minigames/` |
| HTTP API | `scene/http_sse/server.py` |

### 1.2 前端 (`scene/http_sse/static/src/`)

| 系统 | 关键文件 |
|------|---------|
| 品种精灵库 (7×5×3帧) | `companion/breed-sprites.ts` |
| CompanionSprite (stage/shiny/eye/variant) | `companion/CompanionSprite.tsx` |
| LoginCompanion (kitten→adult, rarity reveal) | `companion/LoginCompanion.tsx` |
| HeaderCompanion (sprite+bubble+ResizeObserver) | `companion/HeaderCompanion.tsx` |
| Header (grid 2列, left+actions) | `header/Header.tsx` |
| MiniGameHost (teaser→dock→result, 3 games) | `companion/minigames/MiniGameHost.tsx` |
| FishingGame/CatchGame/TapGame | `companion/minigames/*.tsx` |
| game-api (fetch/submit) | `companion/minigames/game-api.ts` |
| companion-store (bones/emotion/bubble) | `stores/companion-store.ts` |
| SSE dispatch (useSSE → setEmotion/setBubble) | `hooks/useSSE.ts` |

---

## 二、未实现

| # | 内容 | 设定 | 工作量 |
|---|------|------|:--:|
| 1 | 前端 JS roll_companion (离线可用) | §02 | 中 |
| 2 | 动态属性层 (mood/energy/attention 公式化) | §04 | 中 |
| 3 | STYLE 分支 (TECH_PARTNER/COMPANION等) | §06 | 中 |
| 4 | 里程碑系统 (30+触发+叙事) | §10 | 中 |
| 5 | 冷落衰减 (回归反应+恢复) | §06 | 低 |
| 6 | 互动连锁 (InteractionChain DSL) | §07 | 中 |
| 7 | 隐藏互动 (10条彩蛋) | §07 | 低 |
| 8 | 生图 prompt 组装 | §13 | 低 |
| 9 | GET /api/minigame/list (manifest) | §23 | 低 |

---

## 三、设定文档 vs 代码

| 设定 | 代码 | 状态 |
|------|------|:--:|
| 7品种+权重 | BREEDS/BREED_WEIGHTS | ✅ |
| 13怪癖+加权 | QUIRKS/QUIRK_BREED_BONUS | ✅ |
| 5维stat | STAT_NAMES | ✅ |
| 帽子HATS | HATS | ✅ |
| 稀有度门控品种 | BREED_RARITY_GATE | ✅ |
| EmotionFSM 6状态 | state_machine.py | ✅ |
| 品种角色卡集成 | templates.py breed参数 | ✅ |
| 日周期 7时段 | daily_rhythm.py | ✅ |
| kitten/soulmate帧 | CompanionSprite stage prop | ✅ |
| 闪亮粒子 | CompanionSprite shiny prop | ✅ |
| LLM命名 | naming.py + hatch API | ✅ |
| 品种专属气泡 | templates.py breed greetings | ✅ |
| MiniGameHost多游戏 | MiniGameHost + 3 games | ✅ |
| STYLE分支 | — | ❌ |
| 里程碑 | — | ❌ |
| 互动连锁 | — | ❌ |
