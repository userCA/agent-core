# H5 Features Status

## 模型支持

| Provider | Model | Status | Context | Max Output |
|----------|-------|--------|---------|------------|
| **DeepSeek** | deepseek-v4-flash | ✅ **默认** | 128K | 8192 |
| **DeepSeek** | deepseek-chat | ✅ 可用 | 64K | 8192 |
| **DeepSeek** | deepseek-reasoner | ✅ 可用 | 64K | 8192 |
| MiniMax | minimax-m2.7 | ⚠️ 限额 | 256K | 4096 |
| Agnes | agnes-2.0-flash | ✅ 可用 | 256K | 65536 |
| OpenAI | gpt-4o | 需配置 | - | - |
| Anthropic | claude-sonnet-4 | 需配置 | - | - |

## H5 前端功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 水墨风视觉系统 | ✅ 完成 | 原型像素级还原（背景渐变、书法字体、手绘边框、硬偏移阴影） |
| @font-face Latin 覆盖 | ✅ 完成 | 英文文本用 sans-serif，中文用 Ma Shan Zheng |
| 流式输出 | ✅ 完成 | SSE streaming + typing cursor，严格遵守 SSE v1 三阶段生命周期 (start→delta→done) + 15s 心跳 |
| Markdown 渲染 | ✅ 完成 | 代码块紧凑布局 + 复制图标浮动右上角 + 语言标签内联 + 字体统一 Ma Shan Zheng |
| Header 标题 | ✅ 完成 | 对称三区布局，标题可点击唤起宠物，新建会话右侧按钮 |
| 工具面板 | ✅ 完成 | 定位限制在手机框架内，不再超出操作界面 |
| 错误处理 | ✅ 完成 | 中文友好提示 + 去重 + 429 自动重试 |
| 消息气泡 | ✅ 完成 | user/assistant/error 三种样式，用户气泡 min-width: 120px，推理与结果拆分独立卡片 |
| 历史记录 | ✅ 完成 | 卡片式布局 + 搜索 |
| 欢迎页选项 | ✅ 完成 | 4 分类 × 4 选项，全部可用，工具链完整 |
| SuggestionPills | ✅ 完成 | 仅会话中展示快捷操作，欢迎页隐藏 |
| 手机框架尺寸 | ✅ 完成 | 390px × 100dvh，与原型一致 |
| 抽屉定位 | ✅ 完成 | 工具/宠物/认证抽屉均限制在手机框架内 |
| 新建会话 | ✅ 完成 | 会话中 Header 右侧按钮，清空消息 + 恢复欢迎页 |
| 工具抽屉 | ✅ 完成 | 微信风格上拉抽屉，3 个媒体操作（相册/拍摄/文件），已清空原有快捷指令 |
| 宠物抽屉 | ✅ 完成 | 头像+心情+活动+想法 |
| 建议药丸 | ✅ 完成 | 水平滚动 |
| TraceCard | ✅ 完成 | 推理线程折叠卡片 + image/video/widget 内容块渲染 + skill 节点（绿色）+ 独立视觉样式（2px边框+阴影）+ 完成后摘要显示 + 基于 stopReason 的中间/最终结果分类 + delegation 统一收敛至步骤轨道（紫色节点+可展开 agent 明细）+ 中间文本收纳至折叠区 |
| Skill Action 可见性 | ✅ 完成 | skill.started/skill.completed action 事件 + TraceCard 绿色节点 + SKILL.md tools 字段关联 + 历史消息恢复（tool_to_skill 映射持久化） |
| Image Content Block | ✅ 完成 | 后端 image content block 发射 + streaming Markdown 去重 + 前端专用图片块渲染 + 会话重载恢复 |
| StreamingMessage | ✅ 完成 | typing dots + cursor blink |
| SuggestionPills | ✅ 完成 | 水平滚动建议 |
| H5ChatInput | ✅ 完成 | 输入框 + shadow-card + 图片预览缩略图 + 附件显示 |

## 后端 API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/chat/stream` | POST | ✅ | SSE 流式响应 + 15s 心跳 + message.error + 规范错误码 (E00001-E00011) + 多模态 content 字段 (§9.1) |
| `/models` | GET | ✅ | 7 个可选模型 |
| `/sessions` | GET | ✅ | 历史会话列表 |
| `/personas` | GET | ✅ | 4 个专家角色 |
| `/capabilities` | GET | ✅ | 可用技能 + 工具 |
| `/connectors` | GET | ✅ | amap + tavily |
| `/knowledge` | GET | ✅ | 知识文档 |

## Agent Core 架构

| 功能 | 状态 | 说明 |
|------|------|------|
| Emit Sink Loop | ✅ 完成 | `run_agent_loop` 使用 emit 回调替代 async generator，支持异步副作用 |
| Phase 状态机 | ✅ 完成 | `AgentHarnessPhase`（idle/turn/compaction/branch_summary/retry）替代 is_streaming |
| Phase Guard | ✅ 完成 | prompt/continue 入口校验 IDLE，防止并发调用 |
| 兼容层 | ✅ 完成 | `agent_loop` async generator 保留为薄包装，scene/session 层无感知 |
| Turn Snapshot | ✅ 完成 | 每轮创建不可变 `TurnSnapshot`，运行时配置变更影响下一轮而非当前轮 |
| Save Point | ✅ 完成 | turn_end 后 flush + refresh snapshot，`SavePoint` 事件通知 listeners |
| prepareNextTurn | ✅ 完成 | save point 回调刷新 context/model/thinking_level，支持多轮间配置热更新 |
| 统一 Hook 系统 | ✅ 完成 | `AgentHooks` 类统一注册/分发/reducer，支持 observe + on(type) + emit |
| Hook Reducer 语义 | ✅ 完成 | context(链式 transform) / before_agent_start(accumulate) / tool_call(early exit) / tool_result(patch) |
| Hook 兼容层 | ✅ 完成 | 旧 `before_tool_call`/`after_tool_call`/`transform_context` 通过 legacy adapter 无感迁移 |
| AgentHarness 直连 Loop | ✅ 完成 | 删除 `Agent`/`AgentSession`；Harness 直接 `run_agent_loop` |
| Harness 模块拆分 | ✅ 完成 | `harness.py` / `turn_runtime.py` / `persistence.py` / `tool_utils.py` |
| ExtensionContext.harness | ✅ 完成 | `HarnessFacade` Protocol；扩展不再依赖 Agent |
| TurnEnd 单次 flush | ✅ 完成 | 仅 save point / AgentEnd flush pending writes |
| AgentHarness 重命名 | ✅ 完成 | 唯一生产 API 为 `AgentHarness`（无 `AgentSession` 别名） |
| Harness Own Events | ✅ 完成 | ModelUpdate/ThinkingLevelUpdate/ToolsUpdate/QueueUpdate/Settled/AbortEvent/ResourcesUpdate |
| SessionStore 多后端 | ✅ 完成 | `jsonl` / `sqlite` / `inmemory`；`create_session_store()` + `SESSION_STORE` |
| Pending Writes | ✅ 完成 | busy 时排队写操作，save point/agent_end 时 FIFO flush |
| emitRunFailure | ✅ 完成 | 运行失败走完整事件流 MessageStart→MessageEnd→TurnEnd→AgentEnd |
| Compact 一等公民 | ✅ 完成 | `AgentHarness.compact()` 带 Phase Guard + SessionBeforeCompactHookEvent |
| Pending Flush 真持久化 | ✅ 完成 | idle/busy setter 分岔；`ActiveToolsChangeEntry`；FIFO flush 写 store |
| Active Tools Snapshot | ✅ 完成 | 首 turn + save point 均从 `create_turn_snapshot()` 过滤 active tools |
| Stream Options | ✅ 完成 | `get/set_stream_options` + TurnSnapshot 快照；save point 刷新 |
| Provider Hooks | ✅ 完成 | before_provider_request/payload + after_provider_response |
| AgentHarnessError 接线 | ✅ 完成 | persist/hook 失败归一化；failure 走 harness sink；Settled→Abort 时序 |
| 职责收敛 | ✅ 完成 | Harness 为 state/phase/queues/hooks 唯一所有者 |
| Session 配置重放 | ✅ 完成 | reopen 重放 ModelChange / ThinkingLevel / ActiveTools entries |
| Resources Snapshot | ✅ 完成 | `get/set_resources` + `ResourcesUpdate` + TurnSnapshot.resources/session_id |
| nextTurn 队列 | ✅ 完成 | idle 用 `next_turn`；abort 保留；steer/follow_up 仅 turn 中允许 |
| run_when_idle | ✅ 完成 | listener 安全调度，避免 `wait_for_idle` 死锁 |
| Reentrancy 测试 | ✅ 完成 | `test_harness_reentrancy.py` / resources / lifecycle 首 turn+restore |
| Session tree / leaf | ❌ 不做 | 与 TS navigateTree 不对齐；文档非目标 |
| SkillStart/SkillEnd emit | ⏳ planned | 待 `skill()` 公开 API |
| HarnessSession facade | ⏳ planned | 扩展侧 pending-write 门面（TS 亦未完成） |
