# H5 场景模板前端框架设计

> 日期：2026-07-20  
> 状态：待评审  
> 范围：APP / H5 端侧；配置驱动场景模板（聊天 / 知识库问答 / AIGC 创作）

---

## 1. 背景与目标

`agent-core` 后端以「不可变 agent loop + 可插拔 skills / persona」驱动多场景。前端需要对齐同一思想：

- **不变**：SSE → 时间线 blocks → 卡片渲染管道  
- **可变**：场景声明（YAML）+ 卡片包（预置 React 卡 + 协议动态卡）

### 1.1 产品目标

产品/运营通过改场景声明文件调整界面（欢迎文案、壳交互开关、启用哪些卡、引用哪个 persona/skill），**少写 React**。  
首期不做可视化配置台；提供**薄预览页**便于对照声明效果。

### 1.2 非目标（首期不做）

- 嵌套布局 DSL / 拖拽搭建器 / 可视化配置台  
- 在场景声明中重写 system_prompt 或工具定义  
- 搬迁现有 H5 的 Companion、Skills 进化、桌面 Sidebar 等业务页  
- 发明第二套 SSE 事件协议  

---

## 2. 需求结论（已确认）

| 决策点 | 选择 |
|--------|------|
| 形态 | 配置驱动的场景模板库（非先抽独立 npm 包、非纯演进现网整站） |
| 配置范围 | 前端呈现为主；用 `persona_id` / `skill_ids` 引用后端资源 |
| 首期场景 | 聊天 + 知识库 + AIGC；**验收主路径 = 通用聊天** |
| 进入方式 | 不同 URL / 原生 WebView 入口（`?scene=`），不做应用内场景 Tab |
| 代码关系 | 新建轻量运行时，复用现有 SSE 协议与部分组件 |
| 卡片扩展 | 预置卡注册表 + 协议动态卡（display / HITL） |
| 产品配置方式 | 改 YAML/JSON + 薄预览（`preview=1`） |

---

## 3. 架构总览

采用 **方案 1：Scene Manifest + Card Registry**。

```
scene/h5_scenes/
├── static/src/
│   ├── main.tsx                 # ?scene=&preview=
│   ├── runtime/
│   │   ├── sse/                 # 对齐 scene/h5 事件协议（搬迁精简）
│   │   ├── timeline/            # MessageBlock 时间线
│   │   ├── registry/            # CardRegistry
│   │   └── scene-loader/        # 加载校验 manifest
│   ├── shell/                   # Header / MessageList / Composer / Welcome
│   ├── cards/
│   │   ├── common/
│   │   ├── chat/
│   │   ├── kb/
│   │   └── aigc/
│   ├── scenes/
│   │   ├── chat.yaml
│   │   ├── kb.yaml
│   │   └── aigc.yaml
│   └── preview/                 # 只读预览行为
└── （后端继续 scene/h5 或同协议网关）
```

### 3.1 依赖方向（单向）

```
scenes/*.yaml → scene-loader → shell + CardRegistry
                    ↓
              runtime/sse → timeline → cards/*
```

- `runtime` 不感知「聊天 vs 知识库」，只认 block/card `type`  
- `cards` 可依赖 runtime 类型，不反向修改 loader  
- `scenes` 纯数据；产品改这里调界面  

### 3.2 与后端同构关系

| 后端 | 前端 |
|------|------|
| `run_agent_loop` | SSE → timeline 管道 |
| Skills / Persona | Scene Manifest + card packs |
| `ToolResult.display` / HITL | dynamic cards |
| `ChatAssistant` 场景组装 | URL 入口绑定一份 yaml |

---

## 4. 场景声明 Schema

产品主要编辑 `scenes/*.yaml`。一份声明 = **壳 + 卡片编排 + 后端引用**。

```yaml
id: chat
version: 1
title: 智能助手

backend:
  persona_id: default          # 传给现网会话 API；空则宿主默认
  skill_ids: []                # 可选；未接线时 no-op + 预览警告

shell:
  header:
    show_title: true
    show_session_switch: false
  welcome:
    enabled: true
    headline: 你好，需要我帮什么？
    prompts:
      - label: 总结一段文字
        text: 请帮我总结下面内容：
  composer:
    placeholder: 输入消息…
    enable_image: false
    enable_voice: false
    enable_stop: true

cards:
  preset:
    - text
    - think
    - tool_trace
    - follow_up_chips
  dynamic:
    - hitl
    - widget
    - audio

preview:
  read_only: true
```

### 4.1 加载规则

1. `?scene=chat` → 加载 `scenes/chat.yaml`  
2. 校验失败 → 错误页（缺字段 / 未注册 card id），不静默吞错  
3. 发送时携带 `backend.persona_id`（对齐现网 query）；`skill_ids` 有则传，无接线则忽略并警告  
4. 渲染：`timeline` → `registry`，仅实例化声明启用的 type  

### 4.2 刻意不做

嵌套布局树、拖拽坐标、全量主题 DSL。主题沿用现有 CSS token；首期最多 `theme` 枚举（可选，非必须）。

---

## 5. 卡片协议与注册表

### 5.1 契约

```ts
type CardContext = {
  sceneId: string
  preview: boolean
  actions: {
    sendPrompt: (text: string) => void
    submitHitl: (toolCallId: string, payload: unknown) => void
    stop: () => void
  }
}

type CardProps<T = unknown> = {
  id: string
  type: string
  status: 'streaming' | 'done' | 'error'
  data: T
  ctx: CardContext
}
```

`CardRegistry.register({ type, kind: 'preset' | 'dynamic', component })`  
`BlocksRenderer`：`registry.resolve(type)`；场景未启用或未知 → `FallbackCard`。

### 5.2 进时间线的路径

```
SSE events → event_to_block → timeline blocks
    → scene.cards 允许? → CardRegistry → UI
                        → 否 → FallbackCard（preview 显示 type 名）
```

| 来源 | type 示例 | 声明字段 |
|------|-----------|----------|
| 流式文本/思考 | `text` / `think` | `cards.preset` |
| 工具生命周期 | `tool_trace` | `cards.preset` |
| 追问 | `follow_up_chips` | `cards.preset` |
| HITL | `hitl` | `cards.dynamic` |
| `ToolResult.display` | `widget` / `audio` / `media_result` | `cards.dynamic` |
| 知识库 | `citation` / `source_list` | `cards.preset`（优先 `display.citations`） |
| AIGC | `generation_progress` / `media_result` / `regenerate` | preset + dynamic |

**原则：**

- UI 卡与 LLM 可见内容分离（继续用 `display` / HITL）  
- 新卡种 = 注册组件一次 + event→block 映射 + yaml 启用  
- 产品不写 React，只能开关已注册 type  

### 5.3 复用与不搬

| 复用 | 不搬 |
|------|------|
| H5 SSE 类型 / parser、`DisplayPayload`、HitlCard、WidgetFrame、markdown/think | Companion、Skills 进化页、桌面壳、完整 Tab |
| 时间线思想（可精简重写 store） | 工具名正则抠视频等特判 → 改为 display 驱动 |

### 5.4 首期注册表

**common（chat 必须齐）：** `text` · `think` · `tool_trace` · `hitl` · `widget` · `audio` · `fallback`  
**chat：** `follow_up_chips`  
**kb（可占位）：** `citation` · `source_list`  
**aigc（可占位）：** `generation_progress` · `media_result` · `regenerate`

---

## 6. 三场景模板与数据流

### 6.1 入口

- `/h5_scenes/?scene=chat` · `?scene=kb` · `?scene=aigc`  
- 可选 `&preview=1`  
- 原生 APP：不同 WebView 打开不同 URL，不做壳内场景切换  

### 6.2 发消息链路

1. Composer / welcome prompt → `streamChat(text, persona_id, skill_ids?)`  
2. SSE → `event_to_block` 追加 timeline  
3. Registry 按 manifest 渲染 preset / dynamic 卡  
4. `message_end` 后，若启用 `follow_up_chips` 则追加追问卡  

事件协议：对齐现有 H5 v1 多频道，从 `scene/h5/static` **搬迁精简**，不另起协议。

### 6.3 场景差异

| | chat（主路径） | kb | aigc |
|--|----------------|----|------|
| welcome | 通用快捷 | 问文档/知识库 | 创作主题/风格 |
| composer | 文本 + stop | 可开图片 | 可开图片 + stop |
| preset 增量 | follow_up_chips | citation / source_list | generation_progress / media_result / regenerate |
| 验收 | 改 yaml 可见；完整流式 + 工具轨迹 + 动态卡 | 能打开；引用卡可占位 | 能打开；进度/结果可占位 |

`regenerate`：通过 `ctx.actions.sendPrompt`；yaml 可配置 `regenerate_prompt` 模板字符串。

### 6.4 状态边界

| 状态 | 归属 |
|------|------|
| manifest、preview | SceneRuntime |
| blocks、streaming、hitl | TimelineStore（精简） |
| session / auth | 薄 Session 封装 |
| 不进首期 | companion、skills 进化、多 Tab 业务页 |

### 6.5 失败降级

| 情况 | 行为 |
|------|------|
| 未知 scene / yaml 无效 | 错误页 |
| 断流 / 4xx | error 块或 banner |
| 未启用 dynamic type | 跳过；preview 下 Fallback 显示 type |
| skill_ids 未接线 | 聊天可用；预览警告条 |

---

## 7. 薄预览与首期交付边界

### 7.1 预览（`preview=1`）

- 同一运行时、同一 shell  
- `actions.sendPrompt` / `submitHitl` no-op 或 toast「预览只读」  
- 未启用 / 未知 type 用 `FallbackCard` 显示 type 名，方便产品对照 yaml  
- 可选：页面顶栏展示当前 `scene id` + 已启用 cards 列表  

### 7.2 首期交付清单

1. `scene/h5_scenes` 轻量运行时可启动  
2. 三份场景 yaml：`chat` / `kb` / `aigc`  
3. chat 卡片与壳交互齐全（验收主路径）  
4. kb / aigc 模板可打开，专用卡允许占位 UI  
5. `?preview=1` 只读预览可用  
6. `persona_id` 接线现网；`skill_ids` 能接则接，否则明确警告不阻塞  

### 7.3 明确不做（首期）

- 可视化配置台  
- 应用内场景 Tab 切换  
- 布局 DSL  
- 完整复刻现有 H5 全部页面  

---

## 8. 后端薄适配（实现期）

- **必须：** 流式请求携带 `persona_id`（现网已支持）  
- **尽量：** `skill_ids` 透传 → Session/ChatAssistant 过滤可见 skill；若工作量大，首期 yaml 保留字段 + 预览警告，聊天主路径不阻塞  
- **不改：** agent loop；场景差异仍靠 persona / skill 资源  

---

## 9. 成功标准

1. 产品修改 `chat.yaml` 的 welcome / cards 开关后，刷新即可看到界面变化  
2. `?scene=chat` 完成一轮真实（或 FakeProvider 等价）流式对话，文本 + 工具轨迹正确渲染  
3. 动态卡（HITL 或 widget）在声明启用时能出现，未启用时不出现  
4. `?scene=kb` / `?scene=aigc` 可进入且不白屏  
5. `preview=1` 下无法发送，且能看到卡 type 对照信息  

---

## 10. 后续演进（本设计不实施）

- 声明文件 + 预览之上的可视化配置台  
- 场景包热更新 / 远端下发 manifest  
- 将 registry 抽成可被其他宿主复用的包  
- kb / aigc 专用卡与真实 skill display 协议对齐并去占位  

---

## 11. 开放实现细节（不阻塞设计）

- yaml 用 `js-yaml` 还是构建期转 JSON：实现时二选一，推荐构建期或启动时校验一次  
- 静态托管路径与 Vite base：与现有 `scene/h5` 并行，避免抢同一入口  
- `follow_up_chips` 数据来源：后端 custom 字段优先，否则前端启发式（可配置关闭）  
