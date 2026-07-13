# Agent SSE Event Specification v1

> 融合 OpenAI/Anthropic 行业标准与前端统一消息模型

## 1. SSE 事件类型总览

使用 **6 种** SSE event type：

| SSE `event:` | 说明 | 频率 |
|-------------|------|------|
| `heart` | 心跳保活 | 每 15-30s |
| `message` | 消息生命周期（start/end/error） | 每轮 2-3 次 |
| `content` | 内容块增量流式输出 | 高频（每 token） |
| `action` | Agent 动作（工具调用/任务步骤/人机交互） | 按需 |
| `state` | Agent 状态同步（快照/增量） | 按需 |
| `companion` | 宠物状态/气泡 | 按需 |

流终止信号：`data: [DONE]\n\n`

### 1.1 实现级别

| 级别 | 说明 | 需处理 event pattern |
|------|------|---------------------|
| **Level 0** | 最小实现（纯文本对话） | 4 种：`heart`, `message.start`, `content`, `message.end` |
| **Level 1** | + 工具调用 + Skill + 错误处理 | Level 0 + `tool_call.*`, `skill.*`, `message.error`（约 11 种） |
| **Level 2** | 完整体验（state/HITL/companion/step） | Level 1 + `state.*`, `human_input.*`, `step.*`, `companion`（约 20 种） |

前端可根据产品需求从 Level 0 开始渐进实现。

### 1.2 推荐前端接入模式

推荐 `onmessage` 单入口 + dispatch 模式（而非多个 addEventListener）：

```
const es = new EventSource("/v1/sessions/xxx/runs");
es.onmessage = (e) => {
  if (e.data === "[DONE]") return es.close();
  const evt = JSON.parse(e.data);
  switch (evt.type) {
    case "heart":                /* 连接存活 */ break;
    case "message.start":        /* 消息开始 */ break;
    case "message.end":          /* 消息结束 */ break;
    case "message.error":        /* 消息失败 */ break;
    // Level 1
    case "tool_call.started":    /* 工具开始 */ break;
    case "tool_call.completed":  /* 工具完成 */ break;
    // Level 1 — Skill
    case "skill.started":        /* 技能激活 (skillId + skillName + skillDescription) */ break;
    case "skill.completed":      /* 技能完成 (skillId) */ break;
    // Level 2
    case "state.snapshot":       /* 状态快照 */ break;
    case "state.delta":          /* 状态增量 */ break;
    // ...其他事件
  }
};
```

> 服务端所有事件统一通过 `event: message` 发送（单 SSE event channel），前端通过 `evt.type` 分发。`heart` 等保活事件单独 channel 避免干扰业务分发。

---

## 2. heart — 心跳

保持长连接存活，防止代理/负载均衡器断开空闲连接。

```
event: heart
data: {"type":"heart"}

```

- 每 **15-30 秒**发送一次（空闲时）
- 客户端超过 60s 未收到 heart 可判定连接断开

---

## 3. message — 消息生命周期

消息生命周期采用 **start/end 分离**模式（参考 Anthropic），`message` 只负责轻量信封，`content` 是唯一的 data channel，两者职责分离、零重复。

### 3.1 事件结构

```
/** 消息开始 — 轻量信封 */
interface MessageStart {
  type: "message.start";
  messageId: string;
  sessionId: string;
  runId: string;
  createdAt: number;
}

/** 消息结束 — 仅元数据，不携带 content[] */
interface MessageEnd {
  type: "message.end";
  messageId: string;
  stopReason: StopReason;
  completedAt: number;
  usage: Usage;
}

/** 消息失败 */
interface MessageError {
  type: "message.error";
  messageId: string;
  error: ErrorDetail;
}

type StopReason =
  | "end_turn"       // 模型主动结束
  | "tool_use"       // 模型请求工具调用（Agent 自动继续下一轮）
  | "max_tokens"     // 达到最大 token 限制被截断
  | "cancelled"      // 被用户中止
  | "error";         // 出错终止（含安全拒绝，通过 error.type="refusal" 区分）

interface Usage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
}
```

### 3.2 消息生命周期事件

#### message.start — 消息开始
```
event: message
data: {"type":"message.start","messageId":"msg_a1b2c3","sessionId":"scene-xxx","runId":"run_x1y2z3","createdAt":1780069413}

```

#### message.end — 消息结束（仅元数据，无 content[]）
```
event: message
data: {"type":"message.end","messageId":"msg_a1b2c3","stopReason":"end_turn","completedAt":1780069420,"usage":{"input_tokens":1200,"output_tokens":350,"cache_read_tokens":800,"cache_write_tokens":0}}

```

#### message.error — 消息失败
```
event: message
data: {"type":"message.error","messageId":"msg_a1b2c3","error":{"type":"context_overflow","code":"context_length_exceeded","retryable":true}}

```

---

## 4. content — 内容块

### 4.1 Content Block 类型

所有输出内容统一为 Content Block 数组，每个块有独立 `contentId`、`index`、`phase` 生命周期。

#### Text — 文本
```json
{
  "type": "text",
  "contentId": "ct_001",
  "index": 0,
  "phase": "delta",
  "content": "你好，我来帮你分析"
}
```

#### Thinking — 思考过程（仅部分模型）
```json
{
  "type": "thinking",
  "contentId": "ct_002",
  "index": 0,
  "phase": "delta",
  "content": "让我分析一下这个问题..."
}
```

#### Image — 图片
```json
{
  "type": "image",
  "contentId": "ct_003",
  "index": 1,
  "phase": "done",
  "content": "http://example.com/uploads/xxx.png",
  "meta": {
    "name": "screenshot.png",
    "format": "png",
    "size": 102400,
    "width": 800,
    "height": 600,
    "thumb": {"type": "image", "content": "http://example.com/thumb/xxx.png"},
    "progress": 100
  }
}
```

#### Audio — 音频
```json
{
  "type": "audio",
  "contentId": "ct_004",
  "index": 1,
  "phase": "done",
  "content": "http://example.com/uploads/xxx.mp3",
  "meta": {
    "name": "response.mp3",
    "format": "mp3",
    "duration": 5000,
    "size": 51200,
    "progress": 100
  }
}
```

#### Video — 视频
```json
{
  "type": "video",
  "contentId": "ct_005",
  "index": 1,
  "phase": "done",
  "content": "http://example.com/uploads/xxx.mp4",
  "meta": {
    "name": "demo.mp4",
    "format": "mp4",
    "duration": 30000,
    "size": 1048576,
    "width": 1920,
    "height": 1080,
    "thumb": {"type": "image", "content": "http://example.com/thumb/xxx.png"},
    "progress": 100
  }
}
```

#### File — 文件
```json
{
  "type": "file",
  "contentId": "ct_006",
  "index": 1,
  "phase": "done",
  "content": "http://example.com/uploads/xxx.docx",
  "meta": {
    "name": "report.docx",
    "format": "docx",
    "size": 204800,
    "progress": 100
  }
}
```

#### Component — 前端组件（Widget）
```json
{
  "type": "component",
  "contentId": "ct_007",
  "index": 1,
  "phase": "done",
  "content": "widget-chart",
  "meta": {
    "chart_type": "bar",
    "data": {"labels": ["A", "B"], "values": [10, 20]},
    "width": 600,
    "height": 400
  }
}
```

### 4.2 Content Block 公共结构

```
interface Content {
  /** 必填 内容类型 */
  type: "text" | "thinking" | "image" | "audio" | "video" | "file" | "component";
  /** 必填 内容 ID（同一 Message 内唯一） */
  contentId: string;
  /** 必填 内容块在消息中的位置索引（从 0 开始） */
  index: number;
  /** 必填 生命周期阶段 */
  phase: "start" | "delta" | "done";
  /** 必填 内容值（文本内容 / URL / 组件名） */
  content: string;
  /** 选填 多媒体元信息 */
  meta?: Record<string, any>;
}
```

**phase 生命周期**：

| phase | 含义 | 典型特征 |
|-------|------|----------|
| `start` | 新内容块开始 | `content` 为空，前端创建渲染槽位 |
| `delta` | 增量数据 | `content` 为增量片段，前端拼接 |
| `done` | 内容块结束 | `content` 携带完整拼接后的内容 |

**前端推导规则**（无需服务端额外字段）：
```
const isCompleted = (content.phase === "done");
const isDelta = (content.type === "text" || content.type === "thinking") && content.phase !== "done";
```

### 4.3 流式输出模式

**增量流式（用于 text/thinking）**：三阶段 start → delta×N → done

```
event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"你好"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"，我来"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"帮你分析"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"done","content":"你好，我来帮你分析"}

```

**快照模式（用于 image/audio/video/file/component）**：仅 start + done

```
event: content
data: {"type":"image","contentId":"ct_003","index":1,"phase":"start","content":""}

event: content
data: {"type":"image","contentId":"ct_003","index":1,"phase":"done","content":"http://...","meta":{...}}

```

---

## 5. action — Agent 动作

Agent 特有事件（工具调用、任务步骤、人机交互），统一到 `action` SSE event type，通过 `actionType` 区分。

### 5.1 Action 类型

#### tool_call.started — 模型请求调用工具
```json
{
  "actionType": "tool_call.started",
  "toolCallId": "call_abc123",
  "name": "read_file",
  "arguments": {"path": "/src/main.py"}
}
```

> `arguments` 为 `null` 时表示参数将通过 `arguments_delta` 流式推送。

#### tool_call.arguments_delta — 工具参数增量流（Optional，默认推荐在 started 中直接传完整 arguments）
```json
{
  "actionType": "tool_call.arguments_delta",
  "toolCallId": "call_abc123",
  "delta": "{\"path\": \"/sr"
}
```

> 前端拼接所有 `delta` 片段，在 `tool_call.completed` 时得到完整 JSON 参数。仅当参数极大或需要流式时才使用。

#### tool_call.progress — 工具执行中间更新
```json
{
  "actionType": "tool_call.progress",
  "toolCallId": "call_abc123",
  "output": "正在编译..."
}
```

#### tool_call.completed — 工具执行完成
```json
{
  "actionType": "tool_call.completed",
  "toolCallId": "call_abc123",
  "result": {
    "output": "def main():\n  ...",
    "isError": false,
    "display": null
  }
}
```

**result 字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `output` | string | 结果文本 |
| `isError` | boolean | 是否出错 |
| `display` | object? | 富媒体展示（Image/Audio/Component Content Block） |

#### human_input.required — 需要用户输入
```json
{
  "actionType": "human_input.required",
  "toolCallId": "call_xyz789",
  "prompt": "确认删除文件 /tmp/test.txt？",
  "inputSchema": {
    "type": "object",
    "properties": {
      "confirm": {"type": "boolean", "title": "确认", "default": false}
    },
    "required": ["confirm"]
  },
  "timeoutSeconds": 300
}
```

#### human_input.submitted — 用户已提交输入
```json
{
  "actionType": "human_input.submitted",
  "toolCallId": "call_xyz789",
  "status": "accepted"
}
```

#### step.start — 任务步骤开始
```json
{
  "actionType": "step.start",
  "stepId": "s1",
  "stepName": "分析需求",
  "type": "tool_calls"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `stepId` | string | 步骤唯一标识 |
| `stepName` | string | 步骤名称 |
| `type` | `"tool_calls"` \| `"message_creation"` | 步骤类型（工具密集 / 文本生成） |

#### step.end — 任务步骤完成
```json
{
  "actionType": "step.end",
  "stepId": "s1",
  "stepName": "分析需求"
}
```

> Step 是比 tool_call **更高粒度**的任务阶段。一个 Step 内可能包含多次工具调用和文本输出，前端可据此渲染步骤条/进度条。前端可根据 `type` 决定渲染方式（`tool_calls` 显示折叠面板，`message_creation` 显示文本流）。

#### skill.started — 技能激活
```json
{
  "actionType": "skill.started",
  "skillId": "image-generation",
  "skillName": "image-generation",
  "skillDescription": "当用户要求生成图片、创建插画、制作海报、设计头像、画图等视觉内容时，使用此技能。"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `skillId` | string | 技能唯一标识（对应 SKILL.md 的 name） |
| `skillName` | string | 技能标识名（与 skillId 相同，用于前端节点标签） |
| `skillDescription` | string | 技能描述（用于前端展示详情，对应 SKILL.md 的 description） |

> Skill 是 System Prompt 中的指令文本，当 LLM 调用了与 Skill 关联的工具时触发 `skill.started`。一个 Skill 在一次对话轮次中只触发一次 started，即使关联多个工具被多次调用。
> **skillName 与 skillDescription 分离传递**：前端用 `skillName` 作为 TraceCard 节点标签（简洁），`skillDescription` 作为展开内容（信息完整）。

#### skill.completed — 技能完成
```json
{
  "actionType": "skill.completed",
  "skillId": "image-generation"
}
```

> `skill.completed` 在 **TurnEnd**（Agent 轮次结束）时统一发送，关闭所有已激活的 Skill。注意不是在 `message.end` 时关闭——生命周期必须完整覆盖工具执行过程，避免过早结束导致技能重复激活。

### 5.2 Skill 与 Tool 的分层架构

Skill 和 Tool 是分层概念：

| 层级 | 概念 | 触发方式 | SSE 事件 |
|------|------|----------|----------|
| **Skill** | System Prompt 中的指令文本 | 关联工具被调用时自动注入 | `skill.started` / `skill.completed` |
| **Tool** | Python 可执行函数 | LLM function calling | `tool_call.started` / `tool_call.completed` |

```
skill.started (image-generation)
    ↓
  tool_call.started (generate_image) → ... → tool_call.completed
    ↓
skill.completed (image-generation)   ← TurnEnd 时统一关闭
```

> **历史恢复**：Session JSONL 中持久化了 `skill_mapping`（tool_name → skill_name 映射），`GET /session` 返回 `skill_mapping` 字段，前端据此在历史消息中重建 Skill 节点显示。

### 5.3 工具生命周期状态机

```
tool_call.started (arguments 完整 或 null+arguments_delta)
    ↓
tool_call.progress×N (可选，中间输出)
    ↓                    ↗ human_input.required → human_input.submitted
tool_call.progress  ────┘        ↓ (回到 progress 继续执行)
    ↓
tool_call.completed
```

> `human_input.required` 可出现在工具生命周期的**任意阶段**（不仅是 started 之后），工具收到用户输入后继续执行直到 completed。

### 5.4 任务步骤与工具调用的关系

```
step.start (s1, "分析需求", type="tool_calls")
    ↓
  tool_call.started → ... → tool_call.completed
  tool_call.started → ... → tool_call.completed
  content (text delta...)
    ↓
step.end (s1, "分析需求")

step.start (s2, "编码实现", type="tool_calls")
    ↓
  tool_call.started → ... → tool_call.completed
    ↓
step.end (s2, "编码实现")
```

> Step 是可选的。简单对话（单轮问答）可以不发 step 事件；复杂多步骤任务建议发送，便于前端可视化。
> **Step 不支持嵌套**（一层即可）。同名但不同阶段的 Step 通过 `stepId` 区分。

**step 与 state 职责边界**：

| | step | state |
|---|---|---|
| **解决的问题** | 结构分组 — 哪些事件属于同一阶段 | 数据同步 — Agent 当前知道什么 |
| **前端渲染** | 折叠面板、步骤条、时间线 | 数据表格、进度百分比、仪表盘 |
| **更新频率** | 每阶段 2 次（start + end） | 按需（数据变化时） |
| **是否可选** | 是（简单对话不发） | 是（无状态需求不发） |

### 5.5 Action 公共结构

```
interface Action {
  /** 必填 动作类型 */
  actionType: string;
  /** 选填 工具调用 ID */
  toolCallId?: string;
  /** 选填 工具名称 */
  name?: string;
  /** 其他字段按 actionType 不同 */
  [key: string]: any;
}
```

---

## 6. state — Agent 状态同步

将 Agent 内部状态实时推送给前端，前端可直接渲染为数据表格、仪表盘等 UI，无需猜测 Agent 当前状态。

### 6.1 事件结构

```
/** 状态快照 — 完整状态传输（初始化 / 重连时发送） */
interface StateSnapshot {
  type: "state.snapshot";
  snapshot: Record<string, any>;
}

/** 状态增量 — Merge Patch（后续更新只发差异） */
interface StateDelta {
  type: "state.delta";
  delta: Record<string, any>;
}
```

### 6.2 事件示例

#### state.snapshot — 初始状态
```
event: state
data: {"type":"state.snapshot","snapshot":{"task":"分析竞品定价","competitors":[],"currentPhase":"搜索竞品列表","progress":0}}

```

#### state.delta — 增量更新
```
event: state
data: {"type":"state.delta","delta":{"competitors":[{"name":"产品A","price":"¥99"},{"name":"产品B","price":"¥129"}],"currentPhase":"对比分析中","progress":60}}

```

### 6.3 典型流程

```
state.snapshot   ← 完整初始状态（连接建立 / Run 开始时）
state.delta      ← 增量更新 #1
state.delta      ← 增量更新 #2
state.snapshot   ← 偶尔完整刷新（重要状态变化时）
state.delta      ← 继续增量
```

> **前端处理规则**：
> - 收到 `state.snapshot` 时，直接替换整个状态对象
> - 收到 `state.delta` 时，浅合并到现有状态：`state = Object.assign(state, delta)`
> - `null` 值表示删除该字段

---

## 7. companion — 宠物事件

#### 状态变更
```json
{
  "companionType": "state",
  "uid": "user_123",
  "emotion": "happy",
  "eyeOverride": "sparkle",
  "frontendMood": "awake"
}
```

#### 气泡消息
```json
{
  "companionType": "bubble",
  "uid": "user_123",
  "text": "加油！",
  "ttlMs": 5000,
  "priority": "normal"
}
```

---

## 8. 错误码体系

### 8.1 ErrorDetail.code 规范

| code | 说明 |
|------|------|
| `000000` | 成功 |
| `E00001` | 请求参数无效 |
| `E00002` | 鉴权失败 |
| `E00003` | 会话不存在 |
| `E00004` | 模型不可用 |
| `E00005` | 上下文超限 |
| `E00006` | 频率限制 |
| `E00007` | 工具执行失败 |
| `E00008` | 超时 |
| `E00009` | 内部错误 |
| `E00010` | 被取消 |
| `E00011` | 服务过载 |

### 8.2 结构化 Error 对象

message.error 事件中的 `error` 字段：

```
interface ErrorDetail {
  /** 错误类型 */
  type: string;
  /** 错误码 */
  code: string;
  /** 是否可重试 */
  retryable: boolean;
}
```

**错误类型映射**：

| type | code 范围 | HTTP 等效 | retryable |
|------|-----------|-----------|-----------|
| `invalid_request` | E00001 | 400 | false |
| `authentication_error` | E00002 | 401 | false |
| `not_found` | E00003 | 404 | false |
| `model_error` | E00004 | 502 | true |
| `context_overflow` | E00005 | 413 | true |
| `rate_limit` | E00006 | 429 | true |
| `tool_execution_error` | E00007 | - | false |
| `timeout` | E00008 | 504 | true |
| `internal_error` | E00009 | 500 | false |
| `cancelled` | E00010 | - | false |
| `overloaded` | E00011 | 529 | true |

### 8.3 HTTP REST 端点错误格式

非 SSE 端点的错误响应：
```json
{
  "code": "E00001",
  "info": "session_id is required",
  "error": {
    "type": "invalid_request",
    "code": "missing_parameter",
    "retryable": false
  }
}
```

---

## 9. REST 端点

### 9.1 对话

```
POST /v1/sessions/{session_id}/runs
```

**Request Body:**

纯文本消息（简写）：
```json
{
  "message": "帮我写一段代码",
  "provider": "openai",
  "model": "gpt-4o",
  "personaId": "backend-expert"
}
```

多模态消息（Content Block 数组）：
```json
{
  "message": "分析这张图片",
  "content": [
    {"type": "text", "content": "分析这张图片中的内容"},
    {"type": "image", "content": "http://example.com/uploads/chart.png",
     "meta": {"name": "chart.png", "format": "png", "width": 800, "height": 600}},
    {"type": "file", "content": "http://example.com/uploads/report.pdf",
     "meta": {"name": "report.pdf", "format": "pdf", "size": 204800}}
  ],
  "provider": "openai",
  "model": "gpt-4o"
}
```

**输入侧 Content Block 类型**：

| type | content 值 | meta 字段 | 说明 |
|------|-----------|----------|------|
| `text` | 文本内容 | — | 必填，至少包含一个 text 块 |
| `image` | 图片 URL | `name`, `format`, `width`, `height`, `size` | 支持 png/jpg/webp/gif |
| `audio` | 音频 URL | `name`, `format`, `duration`, `size` | 支持 mp3/wav/ogg |
| `video` | 视频 URL | `name`, `format`, `duration`, `width`, `height`, `size` | 支持 mp4/webm |
| `file` | 文件 URL | `name`, `format`, `size` | 通用文件（pdf/docx/csv 等） |

> 当 `content` 字段缺省时，服务端将 `message` 字段作为单个 text Content Block 处理。
> 多媒体资源需先通过 `POST /v1/uploads` 上传获取 URL，再引用。

- `session_id` 为 `new` 时自动创建新会话
- **Response:** `text/event-stream`

### 9.2 提交工具结果（HITL）

```
POST /v1/sessions/{session_id}/tool-results
```

```json
{
  "toolCallId": "call_xyz789",
  "values": {"confirm": true}
}
```

### 9.3 中止

```
POST /v1/sessions/{session_id}/abort
```

### 9.4 会话管理

```
GET    /v1/sessions                        列表（分页）
GET    /v1/sessions/{session_id}/messages   历史消息（含 skill_mapping）
GET    /v1/sessions/{session_id}/export     导出文本
DELETE /v1/sessions/{session_id}            删除
```

#### 历史消息响应中的 skill_mapping

`GET /v1/sessions/{session_id}/messages` 返回 `skill_mapping` 字段，用于历史消息中恢复 Skill 节点显示：

```json
{
  "success": true,
  "session_id": "scene-xxx",
  "messages": [...],
  "skill_mapping": {
    "tool_to_skill": {
      "generate_image": "image-generation",
      "edit_image": "image-generation",
      "web_search": "web-research"
    },
    "descriptions": {
      "image-generation": "当用户要求生成图片、创建插画等视觉内容时，使用此技能。",
      "web-research": "当用户需要搜索网络信息时使用此技能。"
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_to_skill` | `Record<string, string>` | tool_name → skill_name 映射 |
| `descriptions` | `Record<string, string>` | skill_name → skill_description 映射 |

> `skill_mapping` 在 `ChatAssistant.start()` 时持久化到 JSONL。历史加载时前端根据此映射将 tool 块转换为 skill 块显示。当无 Skill 关联时返回空对象 `{}`。

### 9.5 能力与配置

```
GET    /v1/capabilities          Skills + Tools
GET    /v1/models                可用模型
GET    /v1/personas              角色列表
POST   /v1/personas              创建/更新角色
DELETE /v1/personas/{id}         删除角色
```

### 9.6 知识库

```
GET    /v1/knowledge                  文档列表
POST   /v1/knowledge                  添加文档（JSON）
POST   /v1/knowledge/upload           上传文件
GET    /v1/knowledge/{name}           文档详情
PUT    /v1/knowledge/{name}/tags      设置标签
DELETE /v1/knowledge/{name}           删除文档
```

### 9.7 文件上传

```
POST /v1/uploads           multipart/form-data
```

### 9.8 Skills

```
POST /v1/skills/import     导入 Skill
```

### 9.9 MCP Connectors

```
GET    /v1/connectors              列表
POST   /v1/connectors              添加/更新
DELETE /v1/connectors/{name}       删除
POST   /v1/connectors/health       健康检查
```

### 9.10 Channels

```
GET    /v1/channels                列表（密钥脱敏）
POST   /v1/channels                添加/更新
DELETE /v1/channels/{id}           删除
```

### 9.11 Skill Evolution

```
GET  /v1/skills/evolution/summary                       trace 统计
POST /v1/skills/evolution/analyze                       触发分析
GET  /v1/skills/evolution/proposals/{skill_name}        查看提案
POST /v1/skills/evolution/proposals/{id}/accept         接受提案
POST /v1/skills/evolution/proposals/{id}/reject         拒绝提案
GET  /v1/skills/evolution/audit                         审计日志
```

### 9.12 Companion

```
GET  /v1/companion/{uid}          骨骼配置
POST /v1/companion/{uid}/hatch    孵化
```

---

## 10. 完整事件时序示例

### 10.1 简单文本回复

```
event: message
data: {"type":"message.start","messageId":"msg_001","sessionId":"scene-xxx","runId":"run_001","createdAt":1780069413}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"你好"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"，世界！"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"done","content":"你好，世界！"}

event: message
data: {"type":"message.end","messageId":"msg_001","stopReason":"end_turn","completedAt":1780069420,"usage":{"input_tokens":100,"output_tokens":10,"cache_read_tokens":0,"cache_write_tokens":0}}

data: [DONE]

```

### 10.2 包含工具调用的对话（含 arguments_delta）

```
event: message
data: {"type":"message.start","messageId":"msg_001","sessionId":"scene-xxx","runId":"run_001","createdAt":1780069413}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"让我查看文件"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"done","content":"让我查看文件"}

event: action
data: {"actionType":"tool_call.started","toolCallId":"call_abc","name":"read_file","arguments":null}

event: action
data: {"actionType":"tool_call.arguments_delta","toolCallId":"call_abc","delta":"{\"path\": \"/src"}

event: action
data: {"actionType":"tool_call.arguments_delta","toolCallId":"call_abc","delta":"/main.py\"}"}

event: action
data: {"actionType":"tool_call.completed","toolCallId":"call_abc","result":{"output":"def main():\n  ...","isError":false,"display":null}}

event: content
data: {"type":"text","contentId":"ct_002","index":1,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_002","index":1,"phase":"delta","content":"根据文件内容，建议如下修改..."}

event: content
data: {"type":"text","contentId":"ct_002","index":1,"phase":"done","content":"根据文件内容，建议如下修改..."}

event: message
data: {"type":"message.end","messageId":"msg_001","stopReason":"end_turn","completedAt":1780069420,"usage":{"input_tokens":1200,"output_tokens":350,"cache_read_tokens":800,"cache_write_tokens":0}}

data: [DONE]

```

### 10.3 人机交互（HITL）— 工具执行中暂停请求输入

```
event: message
data: {"type":"message.start","messageId":"msg_001","sessionId":"scene-xxx","runId":"run_001","createdAt":1780069413}

event: action
data: {"actionType":"tool_call.started","toolCallId":"call_xyz","name":"deploy_app","arguments":{"app":"my-app"}}

event: action
data: {"actionType":"tool_call.progress","toolCallId":"call_xyz","output":"检测到 2 个可用环境"}

event: action
data: {"actionType":"human_input.required","toolCallId":"call_xyz","prompt":"请选择部署目标环境：","inputSchema":{"type":"object","properties":{"env":{"type":"string","enum":["staging","production"],"title":"目标环境"}},"required":["env"]},"timeoutSeconds":120}

(用户通过 POST /v1/sessions/scene-xxx/tool-results 提交 {"toolCallId":"call_xyz","values":{"env":"production"}})

event: action
data: {"actionType":"human_input.submitted","toolCallId":"call_xyz","status":"accepted"}

event: action
data: {"actionType":"tool_call.progress","toolCallId":"call_xyz","output":"正在部署到 production..."}

event: action
data: {"actionType":"tool_call.completed","toolCallId":"call_xyz","result":{"output":"✓ 部署成功: my-app@production v1.2.3","isError":false,"display":null}}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"应用已成功部署到 production 环境。"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"done","content":"应用已成功部署到 production 环境。"}

event: message
data: {"type":"message.end","messageId":"msg_001","stopReason":"end_turn","completedAt":1780069425,"usage":{...}}

data: [DONE]

```

### 10.4 心跳（空闲期间）

```
event: heart
data: {"type":"heart"}

event: heart
data: {"type":"heart"}

```

### 10.5 包含 Skill 的工具调用

```
event: message
data: {"type":"message.start","messageId":"msg_001","sessionId":"scene-xxx","runId":"run_001","createdAt":1780069413}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"好的，我来帮你生成一张图片。"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"done","content":"好的，我来帮你生成一张图片。"}

event: action
data: {"actionType":"skill.started","skillId":"image-generation","skillName":"image-generation","skillDescription":"当用户要求生成图片、创建插画、制作海报等视觉内容时，使用此技能。"}

event: action
data: {"actionType":"tool_call.started","toolCallId":"call_img01","name":"generate_image","arguments":{"prompt":"一只可爱的猫咪","size":"1024x1024"}}

event: action
data: {"actionType":"tool_call.completed","toolCallId":"call_img01","result":{"output":"![生成图片](http://cdn.example.com/cat.png)","isError":false,"display":null}}

event: action
data: {"actionType":"skill.completed","skillId":"image-generation"}

event: content
data: {"type":"text","contentId":"ct_002","index":1,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_002","index":1,"phase":"delta","content":"图片已生成完毕！"}

event: content
data: {"type":"text","contentId":"ct_002","index":1,"phase":"done","content":"图片已生成完毕！"}

event: message
data: {"type":"message.end","messageId":"msg_001","stopReason":"end_turn","completedAt":1780069425,"usage":{"input_tokens":600,"output_tokens":80,"cache_read_tokens":400,"cache_write_tokens":0}}

data: [DONE]

```

> **Skill 事件时序要点**：
> - `skill.started` 在关联的 `tool_call.started` **之前**发送
> - `skill.completed` 在 **TurnEnd** 时统一发送（所有活跃 Skill 一起关闭），位于 `message.end` 之前
> - 一个 Skill 在同一轮次中只触发一次 `skill.started`，即使多个关联工具被调用

### 10.6 多步骤任务（含 Step + State）

```
event: message
data: {"type":"message.start","messageId":"msg_001","sessionId":"scene-xxx","runId":"run_001","createdAt":1780069413}

event: state
data: {"type":"state.snapshot","snapshot":{"task":"分析竞品定价","competitors":[],"currentPhase":"搜索竞品","progress":0}}

event: action
data: {"actionType":"step.start","stepId":"s1","stepName":"搜索竞品","type":"tool_calls"}

event: action
data: {"actionType":"tool_call.started","toolCallId":"call_001","name":"web_search","arguments":{"q":"竞品定价"}}

event: action
data: {"actionType":"tool_call.completed","toolCallId":"call_001","result":{"output":"找到产品A(¥99)、产品B(¥129)","isError":false,"display":null}}

event: state
data: {"type":"state.delta","delta":{"competitors":[{"name":"产品A","price":"¥99"},{"name":"产品B","price":"¥129"}],"progress":50}}

event: action
data: {"actionType":"step.end","stepId":"s1","stepName":"搜索竞品"}

event: action
data: {"actionType":"step.start","stepId":"s2","stepName":"对比分析","type":"message_creation"}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"start","content":""}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"delta","content":"根据对比分析，产品A定价最低..."}

event: content
data: {"type":"text","contentId":"ct_001","index":0,"phase":"done","content":"根据对比分析，产品A定价最低..."}

event: state
data: {"type":"state.delta","delta":{"currentPhase":"完成","progress":100}}

event: action
data: {"actionType":"step.end","stepId":"s2","stepName":"对比分析"}

event: message
data: {"type":"message.end","messageId":"msg_001","stopReason":"end_turn","completedAt":1780069445,"usage":{"input_tokens":800,"output_tokens":200,"cache_read_tokens":400,"cache_write_tokens":0}}

data: [DONE]

```

---

## 11. 与旧 API 的映射

| 旧事件 | 新 SSE event | 新结构 |
|--------|-------------|--------|
| `{"event":"session_id",...}` | `message` (type=message.start) | 轻量消息开始事件 |
| `{"event":"text_delta","text":"..."}` | `content` (type=text, phase=delta) | Content Block 增量 |
| `{"event":"thinking_delta","text":"..."}` | `content` (type=thinking, phase=delta) | Content Block 增量 |
| `{"event":"tool_start",...}` | `action` (actionType=tool_call.started) | Action 事件 |
| `{"event":"tool_update",...}` | `action` (actionType=tool_call.progress) | Action 事件 |
| `{"event":"tool_end",...}` | `action` (actionType=tool_call.completed) | Action 事件 |
| `{"event":"human_input_required",...}` | `action` (actionType=human_input.required) | Action 事件 |
| `{"event":"message_end","usage":{...}}` | `message` (type=message.end) | 轻量消息结束事件 |
| `{"event":"error","message":"..."}` | `message` (type=message.error) | 消息失败事件 |
| `{"event":"done"}` | `data: [DONE]` | 标准终止符 |
| `{"event":"companion",...}` | `companion` (companionType=state) | Companion 事件 |
| `{"event":"companion_bubble",...}` | `companion` (companionType=bubble) | Companion 事件 |
| — | `heart` | **新增** 心跳 |
| — | `content` (phase=start/done) | **新增** Content Block 生命周期边界 |
| — | `content` (type=image/audio/video/file/component) | **新增** 多媒体 Content Block |
| — | `action` (actionType=tool_call.arguments_delta) | **新增** 工具参数流式（Optional） |
| — | `action` (actionType=human_input.submitted) | **新增** 用户输入确认 |
| — | `action` (actionType=step.start/step.end) | **新增** 任务步骤生命周期（含 stepId + type） |
| — | `action` (actionType=skill.started/skill.completed) | **新增** 技能激活/完成生命周期（含 skillId + skillName + skillDescription） |
| — | `state` (type=state.snapshot/state.delta) | **新增** Agent 状态同步（Merge Patch） |
| — | REST `skill_mapping` 响应字段 | **新增** 历史消息 Skill 恢复映射（tool_to_skill + descriptions） |
