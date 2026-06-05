# 前后端职责边界

> 维护者必读 — 新增 companion 功能时先对照此文档。

## 核心原则

```
BACKEND = 所有判断逻辑的来源
FRONTEND = 渲染引擎，不包含任何判断
```

## 职责分配

| 层 | 拥有 | 禁止 |
|----|------|------|
| **Backend** | 数据定义 (species), 状态决策 (FSM), 气泡生成 (guide), 记忆 (memory), 游戏逻辑 (minigames), SSE 推送 | — |
| **Frontend** | ASCII 精灵数据 (静态), 帧循环 (视觉), 用户输入捕获, CSS 动画, API 调用 | mood 决定, 业务数据, 游戏鱼表, 重复 PRNG(除种子回放外) |

## 数据流

```
用户操作 → Frontend 捕获 → API/SSE → Backend 处理 → SSE push → Frontend 渲染
                                                        ↓
                                                  state_machine
                                                  guide/memory
                                                  minigame logic
```

## 谁决定 mood

1. **Backend EmotionFSM** 根据 agent 事件决定 `emotion` → `frontend_mood`
2. SSE companion event 推送 `{emotion, eye_override, frontend_mood}` 
3. Frontend store.setEmotion() 写入 → mood 字段自动派生
4. **任何前端组件不得调用 setMood() 或自算 mood**（setMood 已删除）

## 数据源唯一性

| 数据 | 唯一源 | 前端如何获取 |
|------|--------|------------|
| 品种定义 + 权重 | `species.py` BREEDS | `GET /api/companion/{uid}` |
| 怪癖表 + 加权 | `species.py` QUIRKS | 同上 |
| 属性名 | `species.py` STAT_NAMES | 同上 |
| 情绪状态 | `state_machine.py` EmotionFSM | SSE companion event |
| 气泡内容 | `guide.py` + `templates.py` | SSE companion_bubble event |
| 鱼表 | `fish_table.py` FISH_TABLE | `GET /api/minigame/config` params.fish_table |
| 品种 ASCII 精灵 | `breed-sprites.ts` | 编译时静态数据 (前端独有) |
| 稀有度颜色/星 | `LoginCompanion.tsx` 常量 | 编译时静态数据 (前端独有，纯视觉) |

## 允许的例外

| 例外 | 原因 | 约束 |
|------|------|------|
| `breed-sprites.ts` ASCII 帧 | 纯视觉数据，不变业务逻辑 | 品种名必须与 `species.py` BREEDS 一致 |
| `LoginCompanion.tsx` RARITY_COLORS | 视觉常量，CSS 颜色 | 与 `species.py` RARITY_COLORS 保持 hex 一致 |
| `FishingGame.tsx` mulberry32 | 种子回放验证需要两端 PRNG 一致 | 算法不得独立修改 |
| `LoginCompanion` zzz/稀有度揭示 | 依赖本地 UI 状态 (hasInput/loading) | 不影响 mood 决策 |

## 新增 companion 功能的 checklist

- [ ] 判断逻辑在 backend `agent_core/companion/` 或 `extensions/companion.py`
- [ ] 数据定义在 `species.py`（append-only）
- [ ] 前端通过 SSE 或 API 获取数据，不本地拷贝业务数据
- [ ] 前端组件不设 mood、不判断业务状态
- [ ] 两端共享类型如有变更，同步更新 `companion-store.ts` 的 TypeScript 接口
