# 咪兔 (Mitu) 角色设定

> 一只住在网页 / App 里的终端风格猫，每只都不一样，只属于你。

## 文档索引

| # | 文档 | 内容 | 状态 |
|---|------|------|:--:|
| 01 | [角色定位](./01-character-identity.md) | 一句话描述、五层体验目标、设计原则 | ✅ |
| 02 | [视觉设定](./02-visual-design.md) | 7 品种、精灵帧、眼睛池、双轨配饰、稀有度视觉差异 | ✅ |
| 03 | [动画系统](./03-animation-system.md) | 帧驱动模型、空闲序列、10 种触发帧、品种专属动作、过渡 | ✅ |
| 04 | [性格系统](./04-personality-system.md) | 三维性格轴、怪癖系统 (Quirk)、属性→行为映射 | ✅ |
| 05 | [稀有度系统](./05-rarity-system.md) | 五级权重、稀有度→内容解锁矩阵、闪亮 | ✅ |
| 06 | [亲密度与成长](./06-bond-growth.md) | 亲密度五级、STYLE 分支、冷落衰退、SOULMATE 后内容 | ✅ |
| 07 | [互动系统](./07-interaction-system.md) | 触发表、连锁互动 (InteractionChain)、隐藏互动 | ✅ |
| 08 | [情绪状态机](./08-emotion-state-machine.md) | 完整状态转换图、衰减率、叠加规则、输入→转换表 | ✅ |
| 09 | [日周期](./09-daily-rhythm.md) | 7 段时间表、energy/mood/animation 乘数 | ✅ |
| 10 | [里程碑系统](./10-milestone-system.md) | 触发条件清单、叙事模板、存储格式 | ✅ |
| 11 | [命名系统](./11-naming-system.md) | LLM 生成 prompt、品种名池 | ✅ |
| 12 | [品种角色卡](./12-breed-profiles.md) | 7品种完整设定: 行为基线/口吻/成长/唯一性 | ✅ |
| 13 | [形象演化与媒体](./13-visual-evolution-media.md) | 幼年→成年→SOULMATE 形象变化、生图/视频、成长相册 | ✅ |
| 14 | [前后端职责边界](./14-frontend-backend-boundary.md) | 职责分配、数据流、唯一数据源、新增功能 checklist | ✅ |
| 15 | [核心玩法循环](./15-core-game-loop.md) | 分钟/日/周/长期循环、轻资源、目标系统、终端风兑现 | ✅ |
| 16 | [资源与奖励系统](./16-economy-and-rewards.md) | 4 类轻资源、产出消耗、奖励优先级、防刷与回归补偿 | ✅ |
| 17 | [终端风界面与交互体验](./17-terminal-ui-ux.md) | 常驻层/轻展开层/深信息层、快捷入口、窄屏降级、点线界面语法 | ✅ |
| 18 | [目标与防疲劳系统](./18-goals-and-anti-fatigue.md) | 每日/每周/隐藏目标、错过补偿、回归周、反打卡压力与目标文案规范 | ✅ |
| 19 | [回忆与收藏系统](./19-memory-collection.md) | 回忆卡、时间线、成长相册、图鉴、纪念卡与收藏陈列 | ✅ |
| 20 | [产品宿主与交互模型](./20-product-host-and-interaction-model.md) | 网页/App宿主、终端风格定义、动作模型、入口映射、跨端一致性与维护规则 | ✅ |
| 21 | [范围收敛与 MVP 聚焦](./21-mvp-scope-and-focus.md) | 做什么/不做什么、MVP边界、保留/缩减/延后清单、以联动和可玩性为先 | ✅ |
| 22 | [Header Companion 场景设计稿](./22-header-companion-scene.md) | 顶栏场景的布局、交互、状态、动画、信息密度、降级方案与实现边界 | ✅ |
| 23 | [Header SVG 收敛方案](./23-header-svg-converged-plan.md) | SVG 在 Header 中的职责边界、收敛方向、保留/删除规则与推荐组合方案 | ✅ |
| — | [附录: 精灵帧库](./appendix/sprite-frame-library.md) | 全部品种 × 全部帧的 ASCII 定义 | ✅ |
| — | [附录: SSE 协议](./appendix/sse-schema.md) | companion 事件类型、顶层信封、字段约束、版本兼容与前端消费规则 | ✅ |
| — | [附录: 持久化规格](./appendix/persistence-schema.md) | Bones/Soul 分层、snapshot/history 分离、schema_version、append-only 与幂等写入 | ✅ |
| — | [附录: Header SVG 收敛预览](./appendix/svg-header-converged-preview.html) | Header 场景下的 SVG 收敛版预览，对比常驻态、反馈态、浮层态和窄屏态 | ✅ |
| — | [附录: Header SVG 外壳预览](./appendix/svg-header-shell-preview.html) | ASCII 猫主体 + SVG 外壳的 Header 预览，对比常驻态、反馈态、深夜态、浮层态与窄屏态 | ✅ |
| — | [附录: Header 产品贴合预览](./appendix/svg-header-product-fit-preview.html) | 贴近现有产品 Header 结构的预览，包含常驻态、反馈态、深夜态与轻动效 | ✅ |
| — | [附录: Header 小游戏 Dock 预览](./appendix/svg-header-minigame-dock-preview.html) | 以 Activity Dock 方式将钓鱼等小游戏接入 Header，支持 teaser、Dock、结果回收与后续扩展 | ✅ |
| — | [附录: Header 终版预览](./appendix/svg-header-terminal-final-preview.html) | 更贴近终端风格的最终预览，统一小游戏为 command/lane/result queue 协议并保留 Header 轻量密度 | ✅ |
| — | [附录: Header Inline Dock 终版预览](./appendix/svg-header-inline-dock-final-preview.html) | 最终确定方向：小游戏完全内嵌在 Header 行内，保持终端风、简约感和可扩展性 | ✅ |

## 架构总览

## 产品载体

咪兔是**运行在网页版 / App 中的 companion 模块**，不是在真实系统终端里直接运行的 TUI 应用。

这里的"终端"指的是:

- 黑白 / 点线 / ASCII 的视觉语言
- 类命令面板、快捷操作、低干扰信息结构
- 开发者工具与工作流氛围

而不是:

- 依赖系统 shell 的交互方式
- 要求用户在真实命令行中输入所有操作
- 以系统终端窗口作为唯一宿主

```
┌─────────────────────────────────────────────────────────┐
│                   agent_core (核心 — 不修改)              │
│                                                         │
│  core/loop.py → 产出 AgentEvent                         │
│       │                                                 │
│       ▼                                                 │
│  extensions/base.py → ExtensionRunner                   │
│       │                                                 │
│       │ on_event(ctx, evt)  ← 异常隔离                   │
│       ▼                                                 │
│  ┌─────────────────────────────────────┐                │
│  │  extensions/companion.py (薄胶水层)  │                │
│  │                                     │                │
│  │  事件 → 路由到各子系统 → 返回 Reaction  │                │
│  └──────────┬──────────────────────────┘                │
│             │                                            │
│    ┌────────┼────────┬──────────┬──────────┐            │
│    ▼        ▼        ▼          ▼          ▼            │
│ 情绪状态机  动态属性  亲密度/STYLE  互动链     里程碑      │
│             │                                            │
│    ┌────────┴────────┐                                   │
│    ▼                 ▼                                   │
│ CompanionMemory    SSE push → 前端渲染                   │
└─────────────────────────────────────────────────────────┘

前端 (scene/http_sse/static/src/components/companion/)
  └── CompanionSprite.tsx  ← 纯渲染, 读 companion-store
      CompanionBubble.tsx  ← SSE 气泡渲染
      LoginCompanion.tsx   ← 登录页精灵
```

## 子系统依赖关系

```
                ┌──────────────┐
                │ bones/物种/配饰│ ← 确定性生成，永不变
                └──────┬───────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │ 性格系统 │  │ 稀有度系统 │  │ 命名系统  │
    └────┬────┘  └────┬─────┘  └──────────┘
         │            │
         └─────┬──────┘
               ▼
       ┌──────────────┐
       │  情绪状态机    │ ← 核心调度层
       └──────┬───────┘
              │
    ┌─────┬───┴───┬─────┬──────┐
    ▼     ▼       ▼     ▼      ▼
  动态属性 亲密度  互动链  日周期  里程碑
    │     │       │     │      │
    └─────┴───┬───┴─────┴──────┘
              ▼
        ┌──────────┐
        │ 气泡/动画  │ ← 输出层
        └──────────┘
```

## 设计原则

1. **隔离于 agent 核心** — 所有逻辑在 Extension 层，崩溃不影响 agent 主循环
2. **确定性第一** — hash(uid) + seeded PRNG 决定基因，不可伪造
3. **骨骼/灵魂分离** — Bones 每次重算，Soul 持久化存储
4. **前端只渲染** — 所有智能逻辑在后端，前端零负担
5. **规则驱动，零 LLM** — 气泡/情绪/互动全部规则+模板，不调 LLM
