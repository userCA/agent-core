# Changelog

## 2026-07-17 — AgentHarness 直连 Agent Loop（Hard-cut）

**Breaking change：** 生产 API 收敛为 `AgentHarness`，删除 `agent_core/core/agent.py` 与 `AgentSession` 别名。

**架构：**
- `AgentHarness.prompt → _execute_turn → run_agent_loop`（唯一生产调用链）
- 新建 `session/harness.py`、`turn_runtime.py`、`persistence.py`、`tool_utils.py`
- `ExtensionContext.harness: HarnessFacade` 替代 `agent`
- Scene 层 `ChatAssistant` 统一 `_harness` 字段
- TurnEnd 不再 flush pending writes（仅 save point / AgentEnd）

**迁移：** `Agent(...) + AgentSession(agent=..., store=...)` → `AgentHarness(provider=..., store=..., session_id=..., ...)`

**测试：** core/session/extensions/skill_evolution/prompts/tools 280 passed。

---

## 2026-07-17 — AgentHarness 成熟度 Phase A–D

对照 `pi-example/harness/doc/agent-harness.md` 补齐生产不变量与生命周期硬化。

**Phase A — 语义补洞：** 首 turn 使用 `create_turn_snapshot()`（active tools 立即生效）；session reopen 重放 model/thinking/active_tools；message persist 失败 → `AgentHarnessError("session")`；mutation hook 失败 → `AgentHarnessError("hook")`。

**Phase B — Resources：** `get/set_resources` + `ResourcesUpdate`；`TurnSnapshot.resources` / `session_id`；Extension `on_before_agent_start` 接入 harness hooks。

**Phase C — 生命周期：** `next_turn` 队列（abort 保留）；idle 拒绝 steer/follow_up；QueueUpdate await；`run_when_idle`；reentrancy 测试套件。

**Phase D — 收敛/文档：** Thin Agent 定位说明；FEATURES/CHANGELOG/design 标明已做 / 不做 / planned。

**测试：** `test_harness_lifecycle.py` / `test_harness_resources.py` / `test_harness_reentrancy.py` / steering 更新。

---

## 2026-07-17 — AgentHarness 语义补全（P0/P1/P2）

**Spec:** `.qoder/specs/Agent完备Harness演进_task-31c.md`

**P0 — 语义补全：** pending flush 真写 store；setter idle/busy 分岔；active tools 进 snapshot；compact cancel reducer；failure 走 harness 持久化；Settled/Abort 时序对齐。

**P1 — stream + hooks：** `stream_options` 快照与 get/set API；provider hook 管道（request patch / payload transform / response observe）。

**P2 — 职责收敛：** Agent 在有 `_harness` 时 `_handle_event`、`_notify_listeners`、`phase` getter 纯委托；删除 session 遗留 `_on_agent_event`；Harness phase setter 同步 Agent state。

**测试：** `test_harness_lifecycle.py` + `test_pending_writes.py` + `test_harness_stream.py`；core/session 197 passed。

---

## 2026-07-16 — 阶段 B: AgentSession → AgentHarness 职责上移

**问题**：Agent 类同时承担 loop runner 和编排核心两个角色，hooks/phase/queues/listeners/config setters/pending writes 全部集中在 Agent，AgentSession 仅是薄包装

**根因**：对标 TS AgentHarness 架构，所有编排职责应属于 Harness（Session），Agent 应精简为纯 loop runner

**方案**：7 步渐进式职责上移，每步保持向后兼容（Agent 通过 `_harness` 引用委托）：
1. **B1 Hooks 上移** — Session 拥有 `AgentHooks`，Agent.hooks 代理到 session.hooks，构造函数 hooks 自动合并
2. **B2 Phase 上移** — Session 拥有 `_phase`，Agent.phase setter 同步 session
3. **B3 Config Setters + Pending Writes** — Session 拥有 `_pending_writes` + set_model/set_thinking_level/set_tools/set_active_tools，Agent 委托
4. **B4 Queues 上移** — Session 拥有 `_steering`/`_follow_up` 队列，steer/follow_up/clear_all_queues 委托
5. **B5 Listeners + Event Handling** — Session 成为事件流唯一入口（`_handle_event`），Agent 的 emit sink 直接路由到 session，subscribe 委托
6. **B6 Agent 精简** — Agent 作为 loop runner，abort_and_wait 委托，文档更新架构定位
7. **B7 重命名** — `AgentSession` → `AgentHarness`，保留 `AgentSession = AgentHarness` 别名

**改动文件**：
- `agent_core/core/agent.py` — 新增 `_harness` 字段，所有编排方法添加委托逻辑
- `agent_core/session/session.py` — 新增 hooks/phase/queues/pending_writes/listeners/_handle_event，重命名为 AgentHarness
- `agent_core/session/__init__.py` — 导出 AgentHarness + AgentSession 别名

**影响范围**：Agent、AgentSession/AgentHarness、所有场景层 ChatAssistant

---

## 2026-07-16 — Harness P3: 统一 Hook 系统

**问题**：Agent 的 Hook 系统分散在多个 `_chain_*` 方法中，每个方法独立管理一类 Hook，缺乏统一的注册、分发和 reducer 语义

**根因**：`_before_hooks`、`_after_hooks`、`_transform_hooks`、`_before_agent_start_hooks` 各自维护独立的列表和链式调用逻辑，外部无法统一观察/参与事件，新增 Hook 类型需要添加新的 `_chain_*` 方法

**方案**：
1. 新建 `AgentHooks` 类，提供 `observe()`（只读）、`on(type, handler)`（参与 reducer）、`emit(event)`（唯一入口）三个 API
2. 类型化 HookEvent：`ContextHookEvent`（链式 transform）、`BeforeAgentStartHookEvent`（accumulate）、`ToolCallHookEvent`（early exit on block）、`ToolResultHookEvent`（patch 累积）
3. Agent 的 `_chain_*` 方法委托给 `self.hooks.emit()`，旧 API 完全兼容
4. 构造函数传入的 `before_tool_call`/`after_tool_call`/`transform_context` 通过 legacy adapter 注册到统一系统

**改动文件**：
- `agent_core/core/hooks.py` — 新建 AgentHooks + 类型化 HookEvent + reducer 实现
- `agent_core/core/agent.py` — 集成 hooks，旧 _chain_* 委托 emit，添加 _maybe_await
- `agent_core/core/__init__.py` — 导出 AgentHooks + HookEvent 类型
- `tests/core/test_hooks.py` — 14 个 reducer 语义 + observer + 异常测试
- `tests/core/test_agent.py` — 3 个 Agent 层 hooks 集成测试
- `tests/tools/test_aigc_creation.py` — 适配统一 hooks 断言

---

## 2026-07-16 — Harness P1: Turn Snapshot + Save Point

**问题**：Agent loop 在多轮执行（工具调用、steering、follow_up）时，各轮之间无法感知运行时配置变更（如 model/thinking_level/system_prompt 修改），且缺乏显式的 save point 语义

**根因**：loop 在整个 run 期间复用同一个 `AgentContext` 和 `AgentLoopConfig`，外部在 turn 间修改 state 后无法被新一轮感知

**方案**：
1. 新增 `TurnSnapshot` 不可变快照数据类（messages/system_prompt/tools/model/thinking_level）
2. 新增 `PrepareNextTurn` 回调类型，在 save point 被 loop 调用
3. loop.py 新增 `_save_point()` 辅助函数：调用 `prepare_next_turn` 刷新 context/config + emit `SavePoint` 事件
4. Agent 新增 `create_turn_snapshot()` 公共方法 + `_prepare_next_turn()` 私有回调
5. events.py 新增 `SavePoint` 事件类型

**改动文件**：
- `agent_core/core/context.py` — TurnSnapshot + PrepareNextTurn 类型
- `agent_core/core/events.py` — SavePoint 事件
- `agent_core/core/loop.py` — _save_point 辅助 + prepare_next_turn 调用
- `agent_core/core/agent.py` — create_turn_snapshot + _prepare_next_turn
- `agent_core/core/__init__.py` — 导出更新
- `tests/core/test_agent.py` — TurnSnapshot + SavePoint 测试

**影响面**：core 层，session 层通过 `prepare_next_turn` 回调间接受益

---

## 2026-07-16 — Harness P0: Emit Sink + Phase 状态机

**问题**：Agent loop 使用 async generator (yield) 模式，无法在事件发出后执行异步副作用（如持久化、session flush），且缺乏显式生命周期阶段管理

**根因**：`agent_loop()` 作为 async generator 只能单向 yield 事件，调用方无法在事件发生时同步执行异步操作；`is_streaming: bool` 无法表达 busy/idle/compaction 等多阶段语义

**方案**：
1. 新增 `AgentHarnessPhase` 枚举（IDLE/TURN/COMPACTION/BRANCH_SUMMARY/RETRY）替代 `is_streaming`
2. 新增 `run_agent_loop()` 使用 emit-sink 回调模式，旧 `agent_loop()` 保留为兼容薄包装
3. Agent 类新增 `phase` 属性，`prompt()`/`continue_()` 加 phase 守卫，`_finish_run()` 重置 phase 至 IDLE
4. `state.phase` 字段同步维护，`is_streaming` 标记为 deprecated

**改动文件**：
- `agent_core/core/state.py` — AgentHarnessPhase 枚举 + phase 字段
- `agent_core/core/loop.py` — run_agent_loop emit sink + agent_loop 兼容层
- `agent_core/core/agent.py` — phase 管理 + emit sink 调用
- `agent_core/core/__init__.py` — 导出更新
- `tests/core/test_state.py` — phase 测试
- `tests/core/test_loop_text.py` — emit sink 测试
- `tests/core/test_agent.py` — phase 断言

**影响面**：core 层全量，scene/session 层通过兼容层无感知

---

## 2026-07-14 13:15 — TraceCard 工具名称 fallback 修复

**问题**：TraceCard 中部分工具步骤显示为通用“工具”字样，而非实际工具名

**根因**：`tool_call.started` 创建 block 时 `toolName` 直接取自 `ae.name`，若 SSE 事件未携带 name 字段，`toolName` 为 undefined，`_flushPending` 映射到 `label` 也为空，TraceCard 回退显示“工具”

**方案**：在 `useSSE.ts` 的 `tool_call.started` handler 中添加 fallback 链：`ae.name || ae.toolCallId || 'tool'`，确保 toolName 始终有值

**改动文件**：`scene/h5/static/src/hooks/useSSE.ts`

**影响面**：仅前端 SSE 处理逻辑，无后端变更

---

## 2026-07-14 12:52 — HitlCard 表单渲染修复 + 空白流式气泡消除

**问题**：
- 确认卡片（HitlCard）无法渲染输入字段，用户无法填写内容
- 模型回答过程中出现空白消息卡片占位（仅工具步骤无文本时）

**根因**：
- H5 HitlCard 期望 JSON Schema 格式（`{properties, required}`），但后端 `confirm` 工具发送的是 `{fields: [...]}` 扁平数组格式，`jsonSchemaToFields` 解析 `schema.properties` 为 `undefined`，导致表单字段列表为空
- `StreamingMessage` 在有 `streamBlocks`（工具步骤）但无流式文本时，仍渲染一个带有 padding 的 streaming-bubble 容器（内部内容被 `hidden` class 隐藏），产生可见的空白卡片

**方案**：
1. `HitlCard.tsx`：`useMemo` 中先检查 `inputSchema.fields` 是否为数组，若是则直接使用；否则走 JSON Schema 解析（兼容两种格式）
2. `StreamingMessage.tsx`：streaming-bubble 仅在 `currentText.length > 0 || audios.length > 0 || hitlRequest` 时渲染，消除空白占位

**改动文件**：
- `scene/h5/static/src/components/hitl/HitlCard.tsx`
- `scene/h5/static/src/components/chat/StreamingMessage.tsx`

**影响面**：仅前端渲染逻辑，无后端/API 变更

---

## 2026-07-14 09:51 — 基于 stopReason 的中间/最终结果分类 + 流式→归档无闪烁交接

**问题**：
- 前端按 block type 硬编码分类中间过程与最终结果，同一 type 在不同 turn 中含义不同（如图片可以是工具中间产物，也可以是最终交付物）
- 流式结束后 TraceCard/Content Card 切换时存在布局跳变（闪烁）
- 流式→归档交接有 350ms 延迟，导致 100ms 空白期

**根因**：
- type 映射无法区分同一 type 在不同 turn 中的语义差异，真正的信号在 LLM turn 的 `stopReason` 字段
- `stopReason: tool_use` 表示中间 turn，`stopReason: end_turn` 表示最终 turn
- 工具执行事件发生在 turn 之间，默认未标记 turnPhase

**方案**：
1. `useSSE.ts` 新增 `turnStartIdxRef` 追踪 turn 边界，`currentTurnPhaseRef` 追踪当前阶段
2. `message.end` 时根据 `stopReason` 回标当前 turn 的所有 blocks
3. 工具执行期间的 blocks 继承 `currentTurnPhaseRef`（默认为 intermediate）
4. 归档时按 `turnPhase` 分流为 `intermediateBlocks` / `finalBlocks`
5. `MessageBubble` 优先使用 `intermediateBlocks`，无此字段时回退到 type 过滤（兼容历史消息）
6. 流式结束时立即清空 `currentText`，消除 350ms 延迟闪烁

**改动范围**：
| 文件 | 改动 |
|------|------|
| `scene/h5/static/src/stores/chat-store.ts` | MessageBlock 增加 turnPhase，ChatMessage 增加 intermediateBlocks |
| `scene/h5/static/src/hooks/useSSE.ts` | turn 边界追踪 + stopReason 回标 + 归档分流 + 交接时序优化 |
| `scene/h5/static/src/components/chat/MessageBubble.tsx` | turnPhase 分流 + type 回退 + 非 step 块捕获 |
| `scene/h5/static/src/components/chat/TraceCard.tsx` | turnPhase 感知的内部分类 |

**影响**：
- 多 turn 工具调用场景下，中间过程的文本/图片/工具结果正确收入 TraceCard，仅最终 turn 显示在内容卡片
- 流式→归档切换无闪烁，交接在 260ms 内完成
- 历史消息渲染保持向后兼容（type-based 回退）

---
## 2026-07-10 19:30 — Skill 事件持久化：历史消息恢复推理卡片技能节点

**需求**：历史消息加载时推理卡片缺少 Skill 节点（实时流有，历史没有）

**方案**：在 ChatAssistant.start() 中持久化 tool_to_skill 映射为 CustomEntry，/session API 从 JSONL 加载该映射，前端 loadMessages 将匹配的 tool blocks 转换为 skill blocks

**改动范围**：
| 文件 | 改动 |
|------|------|
| `scene/h5/chat_assistant.py` | start() 中持久化 tool_to_skill + descriptions 为 CustomEntry |
| `scene/h5/server.py` | /session API 加载 skill_mapping 并返回 |
| `scene/h5/static/src/stores/chat-store.ts` | loadMessages 接收 skillMapping，flushAssistant 中转换 tool→skill blocks |

**影响**：
- 历史消息推理卡片现在显示 Skill 节点，与实时流一致
- tool_result 处理在转换之前执行，保证 widget/video/image 重建不受影响

---
## 2026-07-10 18:45 — 历史消息加载：修复推理卡片与实时流不一致 + 内容去重

**问题**：
- 历史消息中推理卡片显示与实时流不一致：Skill 节点丢失，Tool 显示格式不同
- 生成过程内容被合并到最终输出的消息卡片中（第一轮 assistant 的 "好的！" 文本 + 最终 assistant 的文字都挤在同一个内容卡片）

**根因**：
- `loadMessages` 将连续的 assistant 消息合并为一条 ChatMessage，导致第一轮文本 + 最终文本 + 重复图片 markdown 都混入同一个内容卡片
- Skill 事件是运行时注入的 SSE 事件，不存储在 session 消息中，历史加载无法恢复

**方案**：
- 每个 assistant 消息独立 flush，不再合并（匹配实时流的拆分行为）
- 图片 URL 去重：跟踪 tool_result 中的图片 URL，后续 assistant 消息中的重复图片 markdown 自动剥离

**改动范围**：
| 文件 | 改动 |
|------|------|
| `scene/h5/static/src/stores/chat-store.ts` | `loadMessages` 重构：每个 assistant 独立 flush + collectedImageUrls 去重 |

**影响**：
- 历史消息加载后，第一轮 assistant 消息（含 tool_call）显示为独立推理卡片
- 后续 assistant 消息（最终文本）显示为独立内容卡片，不再重复图片
- Skill 节点在历史加载中已支持（见 19:30 条目）

---
## 2026-07-10 17:30 — Skill Action SSE 增强 + 推理卡片独立视觉样式 + 布局优化

**需求**：
- H5 页面消息输出过程中，显式标注使用了什么 Skill（之前 Skill 是 system prompt 中的指令文本，完全不可见）
- 推理卡片（TraceCard）与普通消息气泡需有明显视觉区分
- 推理卡片内容过于拥挤，需参考原型优化间距
- Skill 完成后副标题不应丢失描述信息

**方案**：
- 新增 `skill.started` / `skill.completed` 两种 action 事件类型，后端事件命名为 `SkillStart` / `SkillEnd`（遵循 `{Entity}{Start|End}` 模式）
- Skill 类型新增 `tools` 字段，建立 tool_name → skill 映射，当 LLM 调用关联工具时自动触发 skill 激活事件
- TraceCard 时间线新增绿色 skill 节点（复用已有的 `.t-node.skill` 样式）
- 推理卡片始终使用 `bubble-trace-only` 类，脱离普通气泡容器
- `.bubble-trace-only .msg-content > .trace`（特异性 0,3,0）恢复独立 trace 外观（2px 墨色边框 + 3px 阴影）
- TraceCard 完成后显示 `block.detail` 摘要（最长 60 字符），而非简单的"完成"
- 步骤间距从 2px 增至 6px，rail padding 增至 12px，提升呼吸感

**改动范围**：
| 文件 | 改动 |
|------|------|
| `agent_core/resources/types.py` | Skill dataclass 新增 `tools: list[str]` 字段 |
| `agent_core/resources/skills.py` | 解析 frontmatter 中的 `tools` 逗号分隔列表 |
| `agent_core/core/events.py` | 新增 `SkillStart` / `SkillEnd` 事件类型并加入 `AgentEvent` union |
| `scene/h5/chat_assistant.py` | 构建 `tool_to_skill` 映射，`_on_agent_event` 拦截 ToolExecutionStart 注入 SkillStart/End；AgentEnd 兆底清理 `_active_skills` |
| `scene/h5/events.py` | SSE 转换层处理 SkillStart/SkillEnd → `skill.started`/`skill.completed` |
| `scene/h5/static/src/api/types.ts` | ActionEvent 注释文档补充 skill action 类型 |
| `scene/h5/static/src/stores/chat-store.ts` | `MessageBlock.type` 添加 `'skill'` |
| `scene/h5/static/src/hooks/useSSE.ts` | 处理 `skill.started`/`skill.completed` action，_Block 支持 skill 类型；`skill.completed` 使用 `findLast` 匹配最后一个 running block |
| `scene/h5/static/src/components/chat/TraceCard.tsx` | stepBlocks 过滤添加 skill；完成后显示 detail 摘要而非"完成" |
| `scene/h5/static/src/components/chat/TraceCard.css` | 步骤间距 6px、rail padding 12px、t-kind flex-shrink:0、t-sub line-height:1.4 |
| `scene/h5/static/src/components/chat/MessageBubble.tsx` | 推理卡片始终使用 `bubble-trace-only` 类 |
| `scene/h5/static/src/components/chat/MessageBubble.css` | `.bubble-trace-only` 透明容器 + `.msg-content > .trace` 恢复独立外观 + rail padding 覆盖 |
| `scene/h5/static/src/components/chat/StreamingMessage.tsx` | TraceCard 拆到独立 `bubble-trace-only` 容器 |
| `docs/api-event-spec-v1.md` | Section 5 新增 skill.started/skill.completed 规范定义 |

**影响**：
- 后端 Skill 类型新增可选字段 `tools`，不影响现有 skill
- 后端 agent 事件流新增 SkillStart/SkillEnd 事件，前端可据此渲染技能节点
- TraceCard 时间线中 skill 节点显示为绿色，位于 tool 节点之前
- 推理卡片与普通消息气泡有明显视觉区分（2px 粗边框 + 3px 阴影 vs 1.5px 浅色边框）
- 推理卡片完成后显示有意义摘要，步骤间距更宽松

---
## 2026-06-30 — 多模态消息支持 + 微信风格输入交互重构

**需求**：
- ChatRequest 支持多模态消息（图片/音频/视频/文件），符合 API 规范 §9.1
- 输入区域参考微信交互，图片选择放入上拉抽屉，清空原有快捷指令按钮

**方案**：
- 后端新增 `ContentBlockInput` 模型，`ChatRequest.content` 字段，`_content_blocks_to_images()` 转换器
- 前端 `streamChat` 新增 `content` 参数，`sendMessage` 支持 `File[]` 并转 base64
- 工具抽屉清空 9 个快捷指令（搜索/代码对比/调试等），替换为微信风格媒体操作（相册/拍摄/文件）
- 图片预览缩略图显示在输入框上方，用户消息气泡显示附件图片

**改动范围**：
| 文件 | 改动 |
|------|------|
| `server.py` | 新增 `ContentBlockInput` 模型、`ChatRequest.content` 字段、`_content_blocks_to_images()` 转换逻辑、`message` 从必填改为可选（默认空串） |
| `chat_assistant.py` | `send_message()` 新增 `images` 参数，透传至 session/agent |
| `types.ts` | 新增 `ContentBlockInput` 接口、`ChatRequest.content` 字段 |
| `client.ts` | `streamChat` 新增 `content` 参数，body 携带多模态内容块 |
| `useSSE.ts` | 新增 `fileToBase64()` / `filesToContentBlocks()` 工具函数；`sendMessage` 支持 `File[]`，生成预览 URL |
| `H5ChatInput.tsx` | 移除独立图片按钮，新增 `pendingImages` 状态、预览行、`handleDrawerFiles` 回调；Props 签名改为 `(text, files?)` |
| `ToolDrawer.tsx` | 清空原 TOOLS 数组，替换为 3 个媒体操作（相册/拍摄/文件），各自隐藏 `<input type="file">` |
| `ToolDrawer.css` | 移除旧 `.td-tool` / `.td-header` 样式，新增微信风格 `.td-media-btn` / `.td-media-ic`（56px 圆形图标） |
| `H5ChatInput.css` | 新增 `.h5-image-preview-row` / `.h5-image-preview` / `.h5-image-remove` / `.h5-image-add` 样式 |
| `chat-store.ts` | `ChatMessage` 新增 `attachments?: string[]` 字段 |
| `MessageBubble.tsx` | 用户消息气泡渲染图片附件缩略图 |
| `MessageBubble.css` | 新增 `.user-attachments` / `.user-attachment-thumb` 样式 |

**影响**：
- H5 输入区域恢复为 `[+] [textarea] [↑]` 三按钮布局
- 点击 + 打开上拉抽屉，选择相册/拍摄/文件后图片显示为预览缩略图
- 发送时图片转 base64 通过 `content` 字段发送到后端
- 用户消息气泡上方显示附件图片缩略图

---
## 2026-06-30 — 推理过程与结果输出拆分为独立卡片

**问题**：
- 推理步骤（think/tool blocks）和最终输出（text/widget/video blocks）都在同一个 `.bubble-assistant` 内
- `TraceCard` 内部的 `.trace` 容器有自己的卡片样式（边框/背景/阴影/圆角），导致“卡片中嵌套卡片”的双重边框问题
- 所有内容塞进一张卡片，视觉上过于拥挤

**方案**：
- `MessageBubble.tsx` 中将 blocks 拆分为 `stepBlocks`（推理步骤）和 `contentBlocks`（输出内容），各自渲染为独立的 `.bubble-assistant` 气泡
- 两个气泡紧密贴合：上方气泡 `border-radius: 16px 16px 4px 4px`，下方气泡 `border-radius: 4px 4px 16px 16px`，`margin-bottom: -1px` 重叠边框
- `TraceCard` 嵌套在 `.bubble` 内时去除自身卡片样式（背景透明/无边框/无阴影/无圆角），与父气泡视觉统一

**改动范围**：
| 文件 | 改动 |
|------|------|
| `MessageBubble.tsx` | 拆分 blocks 为 step/content，渲染两个独立气泡 |
| `MessageBubble.css` | 新增 `.bubble-trace-only` / `.bubble-content-only` 样式 |
| `TraceCard.css` | 新增 `.bubble .trace` / `.bubble .trace-head` / `.bubble .trace-rail` / `.bubble .trace-content` 覆盖样式 |

**影响**：
- 有推理步骤 + 输出内容时，拆分为两张卡片（上：推理过程，下：结果输出）
- 仅有推理或仅有内容时，保持单卡片行为
- TraceCard 独立使用时仍保留原有卡片样式

---

## 2026-06-30 — 用户消息气泡最小宽度修复

**问题**：
- 用户消息气泡（`.bubble-user`）没有设置 `min-width`，纯靠内容撑宽度
- 短消息如“你是谁”（3个字）在 390px 屏幕上只有约 75px，视觉过于窄小

**方案**：
为 `.bubble-user` 添加 `min-width: 120px`，确保短消息气泡有合理的最小宽度

**改动范围**：
| 文件 | 改动 |
|------|------|
| `MessageBubble.css` | `.bubble-user` 添加 `min-width: 120px` |
| `h5.css` | `.h5-app-layout .bubble-user` 同步添加 `min-width: 120px` |

**影响**：
- 短消息气泡最小宽度 120px，不再过窄
- 长消息不受影响（内容宽度 > 120px 时 min-width 不生效）
- max-width: 72% 约束仍然保持

---

## 2026-06-30 — Markdown 字体统一修复

**问题**：
- `.markdown-body` 在 tokens.css 中显式设置了系统字体栈 (`-apple-system, BlinkMacSystemFont, ...`)
- 导致所有 AI 消息内容（Markdown 渲染）使用系统字体而非设计系统指定的 Ma Shan Zheng 书法字体
- 聊天页面字体与设计系统不统一

**方案**：
移除 `.markdown-body` 的 `font-family` 显式覆盖，使其继承 `body` 的 `var(--font-sans)`（Ma Shan Zheng 优先）

**改动范围**：
| 文件 | 改动 |
|------|------|
| `tokens.css` | `.markdown-body` 移除 `font-family: -apple-system, ...` 覆盖 |

**影响**：
- AI 消息内容字体从系统 sans-serif 变为 Ma Shan Zheng（与设计系统一致）
- 代码块和 inline code 仍使用 `var(--font-mono)`（不受影响）
- 英文文本仍通过 `@font-face` Latin override 渲染为 Arial（不受影响）

---

## 2026-06-30 — H5 Header 布局优化 + 代码块紧凑化 + 新建会话功能

**问题**：
- Header 缺少“新建会话”入口，进入会话后无法重置对话
- 新建会话和历史按钮挤在左侧视觉拥挤，宠物头像按钮占用右侧空间
- 代码块 header 行（语言标签 + “复制”文字按钮）在 390px 手机上占用过多垂直空间

**方案**：
1. Header 对称三区布局：左`[历史]` 中`[咪兔·在线(可点击唤起宠物)]` 右`[新建会话]`
2. 标题“咪兔”可点击唤起宠物抽屉，移除 header 右侧宠物头像按钮
3. 代码块去掉独立 header 行，复制按钮改为 28px 小图标 absolute 定位在右上角
4. 语言标签缩小为 10px inline badge 在代码块右下角

**改动范围**：
| 文件 | 改动 |
|------|------|
| `CompactHeader.tsx` | 新增新建会话按钮、标题可点击、移除宠物头像、流式时替换为停止按钮 |
| `CompactHeader.css` | 新增 `.h5-header-right`、`.h5-header-title-btn`，移除 `.h5-header-pet` |
| `App.tsx` | 新增 `handleNewChat` 回调 + `onNewChat` prop |
| `markdown.ts` | 代码块去掉 `.code-block-header`，复制按钮改为纯图标 |
| `Markdown.tsx` | 复制反馈改为 SVG 图标切换（clipboard→check） |
| `tokens.css` | 代码块 CSS 紧凑化：absolute 定位复制按钮、新增 `.code-lang-tag` |

**影响面**：Header 更简洁、代码块节省约 28px 垂直空间、新增会话管理能力

---

## 2026-06-30 — H5 页面尺寸对齐原型 + 宠物/工具抽屉定位修复

**问题**：
- 手机框架宽度 430px 与原型 `oriental-chat-journal.html` 的 390px 不一致
- `CompanionDrawer` 和 `AuthPanel` 使用 `position: fixed` 定位到浏览器视口而非手机框架，导致超出 APP 范围
- `ToolDrawer` 已在前轮修复，但 `CompanionDrawer` 遗漏

**根因/方案**：
1. `#root:has(.h5-app-layout)` 的 `max-width` 从 430px 改为 390px，与原型 `.phone-frame` 一致
2. `CompanionDrawer` 和 `AuthPanel` 从 `MotionConfig` 外层移入 `.h5-app-layout` 内部
3. `h5.css` 新增 `.cd-overlay`、`.cd-sheet`、`.h5-auth-backdrop` 的 `position: absolute` 覆盖

**改动范围**：
| 文件 | 改动 |
|------|------|
| `App.css` | `max-width: 430px` → `390px` |
| `App.tsx` | `CompanionDrawer`、`AuthPanel` 移入 `.h5-app-layout` 内部 |
| `h5.css` | 新增 `.cd-overlay/.cd-sheet`、`.h5-auth-backdrop/.h5-auth-panel` absolute 定位覆盖 |

**影响面**：所有抽屉组件（工具/宠物/认证）均限制在手机框架内，不再溢出到浏览器视口。

---

## 2026-06-30 — SuggestionPills 欢迎页隐藏 + 会话场景限制

**问题**：
- SuggestionPills（搜索认证、代码对比等硬编码开发工具按钮）在欢迎页也显示，但实际应仅在会话中展示
- 欢迎页的 prompt-grid 已随分类 tab 动态切换，与 SuggestionPills 功能重叠

**根因/方案**：
- `App.tsx` 中 `SuggestionPills` 无条件渲染，未区分欢迎页与会话状态
- 通过 `useChatStore` 获取 `messages.length > 0` 判断是否有会话，条件渲染 SuggestionPills

**改动范围**：
| 文件 | 改动 |
|------|------|
| `App.tsx` | 新增 `hasMessages` 状态，`SuggestionPills` 仅在 `hasMessages` 为 true 时渲染 |

**影响面**：欢迎页更简洁，仅显示分类相关的 prompt 卡片；会话中保留快捷操作按钮。

---

## 2026-06-30 — 消息卡片双层边框 + 工具面板定位修复

**问题**：
1. 助手消息卡片出现“双层边框”：`.bubble-assistant` 边框与内部 `.code-block-wrapper` 边框叠加
2. 工具面板（ToolDrawer）过大且超出手机框架，`position: fixed` 定位到视口而非手机框架

**根因/方案**：
- 双层：`.bubble-assistant` 和 `.code-block-wrapper` 各有独立 `border`，在 H5 手机布局中叠加显示
- 工具面板：`.td-sheet` 和 `.td-overlay` 使用 `position: fixed`，在手机模拟器中定位到全屏视口

**改动范围**：
| 文件 | 改动 |
|------|------|
| `h5.css` | `.bubble-assistant .code-block-wrapper` 移除边框和阴影；`.td-overlay/.td-sheet` 改为 `position: absolute` + `max-height: 55%` |
| `App.css` | `.h5-app-layout` 添加 `position: relative` 建立定位上下文 |

**影响面**：助手消息卡片单层边框显示；工具面板限制在手机框架内。

---

## 2026-06-30 — Header 标题修复 + Markdown 代码渲染白屏修复

**问题**：
1. Header `<h1>` 显示会话标题而非“咪兔”，导致长标题被截断
2. 输出包含代码块时页面白屏（React 崩溃）

**根因/方案**：
- `CompactHeader.tsx` 中 `title` 变量使用了 `currentSession.title`，应始终显示“咪兔”
- `markdown.ts` 中 `renderer.code` 使用了新式对象 API `{ text, lang }`，但已安装的 `marked` v12.0.2 仍使用旧式三参数 API `(code, infostring, escaped)`，导致 `text` 为 `undefined`，调用 `.replace()` 崩溃

**改动范围**：
| 文件 | 改动 |
|------|------|
| `CompactHeader.tsx` | `title` 始终为“咪兔”，移除 `useSessionStore` 依赖 |
| `markdown.ts` | `renderer.code` 改为 `(code: string, infostring?: string)` 旧式 API |

**影响面**：Header 始终显示应用名称；代码块不再导致白屏崩溃。

---

## 2026-06-30 — SSE v1 内容块生命周期合规 + 风格统一

**需求**：检查聊天首页选项可用性，保证整体风格统一，消息流式展示契合 API 规范。

**根因/方案**：
- 欢迎页 `scene-tab` / `prompt-card` 边框 1.5px 与原型 `border-2 border-ink` (2px) 不一致
- `useSSE.ts` 仅处理 `phase=delta`，忽略 `start` / `done`，不符合 SSE v1 三阶段规范
- 非文本 Content Block（image/audio/video/component）未处理

**改动范围**：
| 文件 | 改动 |
|------|------|
| `WelcomeScreen.css` | scene-tab + prompt-card 边框 1.5px → 2px |
| `useSSE.ts` | 完整实现 phase=start→delta→done 三阶段；新增 image/audio/video/component 处理 |

**影响面**：流式消息严格遵守 SSE v1 规范；欢迎页视觉与原型统一。

**欢迎页 16 个选项可用性**：全部 ✅（代码开发4项、日常办公4项、设计创意4项、深度研究4项，均有对应工具支持）。

---

## 2026-06-30 — DeepSeek V4 Flash 模型集成

**需求**：将 H5 场景默认模型从 MiniMax M2.7 切换为 DeepSeek V4 Flash。

**根因/方案**：
- MiniMax API 用量已达限额（429），需切换到更经济的 DeepSeek
- DeepSeek 使用 OpenAI 兼容 API，复用 `OpenAIProvider` 实现
- base_url: `https://api.deepseek.com`（不带 `/v1` 后缀）

**改动范围**：
| 文件 | 改动 |
|------|------|
| `.env` | 新增 `DEEPSEEK_API_KEY`，`AGENT_PROVIDER=deepseek`，`AGENT_MODEL=deepseek-v4-flash` |
| `scene/h5/chat_assistant.py` | 新增 deepseek auth 分支 + OpenAIProvider 配置（3 个模型：deepseek-v4-flash / deepseek-chat / deepseek-reasoner） |
| `scene/h5/server.py` | `/models` 端点新增 3 个 deepseek 选项 |

**影响面**：H5 场景默认使用 DeepSeek V4 Flash，128K 上下文，8192 max output tokens。

---

## 2026-06-30 — H5 错误处理优化

**需求**：修复 HTTP 500 报错体验 + 右上角图标不符合水墨风。

**改动**：
1. **后端错误传播**：`server.py` agent 循环失败后发送 `message.error` SSE 事件
2. **前端错误国际化**：`client.ts` 将 HTTP 状态码翻译为中文友好提示
3. **错误去重**：`useSSE.ts` 使用 `errorShownRef` 防止重复显示
4. **429 重试**：`client.ts` withRetry 支持 429 状态码自动重试
5. **图标替换**：`CompactHeader.tsx` 像素猫 → 天蓝色抽象水滴 SVG
6. **错误气泡样式**：`MessageBubble.css` 适配水墨风主题色

---

## 2026-06-29 — H5 水墨风原型全面复刻

**需求**：H5 页面尽全力复刻 `oriental-chat-journal.html` 原型。

**改动**：完成 25+ 项 CSS/组件修复，包括背景渐变 135deg、@font-face Latin 子集覆盖、Ma Shan Zheng 书法字体全局应用、2px border-ink 手绘边框、shadow-card 硬偏移阴影、gentleBounce 动画等。
