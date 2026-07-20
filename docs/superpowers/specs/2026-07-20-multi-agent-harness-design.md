# Multi-Agent Harness 设计规格

> 日期：2026-07-20  
> 状态：实施中  
> 范围：在现有 Python `agent-core` 上落地库级多 Agent 编排，并以 `scene/http_sse` 为验收宿主演示云端多用户客服/聊天。`scene/h5` 仅要求事件映射同构（同一 `delegation` 字段），不阻塞首版验收。

## 1. 背景与目标

### 1.1 问题

当前 `agent-core` 提供单 `AgentHarness` 运行时（事件、工具、Hook、有状态 Session），但没有一等的多 Agent 编排能力。Scene 侧仅以 `session_id` 区分会话，`SessionStore.list_sessions(owner=...)` 未真正用于多用户隔离。

参考材料：

| 文档 / 代码 | 用途 |
|-------------|------|
| `docs/multi-agent-harness-design.md` | Harness-in-Tool 编排模式（主参考） |
| `pi-example/harness/` | AgentHarness 生命周期与 Session fork 参考 |
| `docs/cloud-agent-framework-design.md` | 多租户云部署愿景（本规格仅吸收隔离/有状态要点，不做完整云拓扑） |

### 1.2 目标

1. **库级编排**：`create_multi_agent_harness` + `delegate_task`，支持 `single` / `parallel` / `chain`。
2. **云端多用户**：Scene 按 `owner`（user_id）隔离会话的创建/列表/删除/读取。
3. **有状态**：父会话与子会话均可持久化；断线后可恢复父会话 transcript。
4. **进度可见、细节折叠**：客户端看到委派进度与短摘要，不流式透出子 Agent 全文。
5. **Scene 可运行**：`scene/http_sse` 配置示例客服 Profile 后可端到端验证。

### 1.3 非目标（首版）

- Handoff（会话所有权转移给另一 Agent）
- ConversationEngine / Redis EventBus / 多 Worker 会话迁移
- RAG / KnowledgeBaseRegistry（可后续作为某 Profile 的工具）
- 进程级 sub-agent（spawn）
- 多 Agent 共享同一 Session 并发写入
- TaskDecomposer / DAG 自动拆解、AgentPool 池化
- 默认允许嵌套 `delegate_task`
- C 端子会话全文流式
- 修改 `demo/` 或改写 `core/loop.py` 状态机

## 2. 需求决策摘要

| 项 | 决策 |
|----|------|
| 场景 | 云端通用聊天 / 客服 |
| 协作形态 | 编排委派（Orchestrator + `delegate_task`）为主 |
| 持久化 | 有状态 |
| 用户可见性 | 进度可见、细节折叠 |
| 交付范围 | 库 + 现有 Scene 可运行 |
| 委派模式 | `single` + `parallel` + `chain` |
| 工厂返回值 | `(AgentHarness, MultiAgentHandle)` |
| 嵌套委派 | 默认关闭（`allow_nested_delegate=False`） |
| 子 Session 默认隔离 | `isolated` |

## 3. 架构

### 3.1 选定方案：Harness-in-Tool + Scene 薄接入

编排器是标准 `AgentHarness`，通过 `delegate_task` 工具在进程内启动子 `AgentHarness`。不继承/重写 phase 状态机。

```
用户 → scene/http_sse（按 owner 隔离）
         → ChatAssistant / create_multi_agent_harness
              → Orchestrator AgentHarness + delegate_task
                   → SubAgentRunner (single|parallel|chain)
                        → SubAgentFactory → AgentHarness × N
              → Tool on_update → delegation 进度 → SSE（折叠 UI）
              → SessionStore 有状态持久化
```

### 3.2 依赖方向

```
scene/http_sse  →  agent_core.multi_agent  →  agent_core.session
                                           →  agent_core.tools
                                           →  agent_core.core
```

`core` 保持零 IO；多 Agent 属于编排层，不进入 `loop.py`。

### 3.3 包布局

```
agent_core/multi_agent/
├── __init__.py
├── types.py                 # AgentProfile, modes, SubAgentResult, options, handle
├── profile_registry.py      # register/resolve/list + format_for_system_prompt
├── sub_agent_factory.py     # 子 session + 工具过滤 + 子 AgentHarness
├── sub_agent_runner.py      # single/parallel/chain + 信号量 + abort_all
├── delegate_tool.py         # delegate_task Tool
└── factory.py               # create_multi_agent_harness

agent_core/session/store.py  # 增量：fork_session；SessionHeader.owner；list 按 owner 过滤
```

对 `AgentHarness` 仅做必要只读 getter（若缺失）；abort 协作通过 Scene/`MultiAgentHandle` 完成，避免污染 Harness 构造签名。

## 4. 类型与公共 API

### 4.1 类型

```python
IsolationMode = Literal["isolated", "forked"]
DelegationMode = Literal["single", "parallel", "chain"]

@dataclass
class AgentProfile:
    name: str
    description: str
    system_prompt: str | Callable[..., Awaitable[str] | str]
    model: Any | None = None
    thinking_level: str | None = None
    tools: list[str] | None = None          # None = 继承编排器工具池（不含 delegate）
    isolation: IsolationMode = "isolated"
    max_concurrency: int = 1
    allow_nested_delegate: bool = False

@dataclass
class MultiAgentHarnessOptions:
    profiles: list[AgentProfile]
    max_concurrent_agents: int = 4
    delegate_tool_name: str = "delegate_task"
    routing_prompt: str | None = None
    cleanup_sub_sessions: bool = False      # True 则 run 结束后删除子 session

@dataclass
class SubAgentResult:
    agent_name: str
    task: str
    status: Literal["completed", "failed", "aborted"]
    response_text: str
    usage: dict[str, int | float]
    duration_ms: int
    error_message: str | None = None
    session_id: str | None = None

@dataclass
class MultiAgentHandle:
    registry: AgentProfileRegistry
    runner: SubAgentRunner
```

### 4.2 `delegate_task` 参数

```json
{
  "mode": "single | parallel | chain",
  "agent": "profile-name",
  "task": "任务描述",
  "tasks": [{ "agent": "name", "task": "..." }]
}
```

校验：

- `single`（默认）：需要 `agent` + `task`；忽略 `tasks`
- `parallel` / `chain`：需要非空 `tasks`；忽略顶层 `agent`/`task`
- 未知 `agent` → tool error（不拖垮编排器 turn）
- `chain`：后续 task 支持占位符 `{previous}`，替换为上一专家 `response_text`

### 4.3 工厂

```python
def create_multi_agent_harness(
    *,
    options: MultiAgentHarnessOptions,
    provider: ModelProvider,
    auth_source: AuthSource,
    store: SessionStore,
    session_id: str,
    tools: list[Tool] | ToolRegistry | None = None,
    system_prompt: str | None = None,
    # 其余与 AgentHarness 兼容的参数…
) -> tuple[AgentHarness, MultiAgentHandle]:
    ...
```

编排器 system prompt = `base` + `routing_prompt`（或默认路由说明）+ `<available_agents>...</available_agents>`。

子 Agent 默认不注册 `delegate_task`，除非该 profile `allow_nested_delegate=True`。

### 4.4 组件职责

| 组件 | 职责 |
|------|------|
| `AgentProfileRegistry` | 注册/解析/列表；XML 格式化供提示词 |
| `SubAgentFactory` | 创建子 session、过滤工具、组装子 `AgentHarness` |
| `SubAgentRunner` | 三模式执行、全局/profile 并发、进度回调、`abort_all` |
| `DelegateTaskTool` | 参数校验 → runner → `ToolResult`；`on_update` 推进度 |

## 5. 事件、隔离与持久化

### 5.1 进度事件

不新建平行事件总线。进度经工具 `on_update` / `ToolResult.details` 传递，结构：

```python
{
  "type": "delegation",
  "phase": "start" | "agent_start" | "agent_end" | "end",
  "mode": "single" | "parallel" | "chain",
  "delegation_id": "uuid",
  "agent": "billing",
  "task": "...",
  "status": "running" | "completed" | "failed" | "aborted",
  "index": 0,
  "total": 2,
  "summary": "短摘要",
  "error_message": None,
  "session_id": "parent__sub__billing__a1b2c3d4",
}
```

| phase | 用户可见 |
|-------|----------|
| `start` | 正在协调专家 |
| `agent_start` | 某专家处理中 |
| `agent_end` | 短 summary（可折叠） |
| `end` | 整次委派完成/失败 |

子 Agent 的 `text_delta` / 内部 tool 流不挂到父 SSE。编排器对用户的最终回复仍走主会话 `text_delta`。

### 5.2 Session 隔离

| 模式 | 行为 |
|------|------|
| `isolated`（默认） | 新 session，空历史；task 为唯一用户输入 |
| `forked` | `store.fork_session(parent → new)` 拷贝 entries 快照后再跑 |

子 session 命名：`{parent_session_id}__sub__{profile_name}__{8hex}`。

生命周期：默认保留子 session 供审计；`cleanup_sub_sessions=True` 可在 `finally` 删除。删除父会话时 Scene 级联删除 `{parent}__sub__*`。

### 5.3 SessionStore 增量

```python
class SessionHeader(BaseModel):
    # 现有字段…
    owner: str = ""

class SessionStore(Protocol):
    # 现有方法；list_sessions(owner=...) 必须真正过滤
    async def fork_session(
        self, source_session_id: str, new_session_id: str, *, header: SessionHeader
    ) -> None: ...
```

实现：jsonl / sqlite / inmemory 均支持全量 entry 拷贝（简化版 fork，不做完整树游标语义）。

### 5.4 多用户隔离

- 创建会话必须带 `owner`（Scene 从 `uid` header 或 `user_id` query 解析）
- `get` / `delete` / `list` / `messages` 校验 owner；不匹配则拒绝或空
- `/sessions` 只返回当前用户会话
- `tenant_id` 首版不强制；可放 header metadata 预留

### 5.5 持久化划分

| 数据 | 位置 |
|------|------|
| 用户 ↔ 编排器对话 | 父 session |
| `delegate_task` ToolResult（含 delegation 终态） | 父 session |
| 子 Agent 完整轨迹 | 子 session |
| Profile 配置 | Scene/进程配置（首版） |

Compaction 各自独立；短子任务通常不触发。

### 5.6 Abort

```
用户 abort → harness.abort() + handle.runner.abort_all()
           → 子 harness.abort()
           → delegate_task 返回 status=aborted
```

Runner 将 `ToolContext.signal` 与子运行链接。

### 5.7 并发

- 全局 `max_concurrent_agents`（默认 4）
- 每 profile `max_concurrency`
- parallel：`asyncio.Semaphore` + `gather`
- chain：严格串行 + `{previous}` 替换

## 6. Scene / SSE / 前端

### 6.1 后端改动

| 组件 | 变化 |
|------|------|
| `ChatAssistant` | 有 profiles 时用工厂；持有 `MultiAgentHandle`；abort 时 `abort_all` |
| `SessionManager` | owner 绑定与校验；级联删子 session |
| `server.py` | 解析 owner：优先 `uid` header，其次 `user_id` query；皆无时用 `anonymous`（可用环境变量 `REQUIRE_SESSION_OWNER=1` 拒绝匿名创建） |
| `events.py` | `details.delegation` → SSE `delegation` 帧 |
| 配置模块 | 示例客服 Profile（billing / knowledge / logistics 等） |

与现有 `persona_id`：profiles 为主；persona 可选写入 `routing_prompt`，不替代专家池。

### 6.2 SSE 帧

在保留 `tool_*` 的同时增加：

```json
{"event": "delegation", "phase": "start", "delegation_id": "...", "mode": "parallel", "total": 2}
{"event": "delegation", "phase": "agent_start", "delegation_id": "...", "agent": "billing", "task": "...", "index": 0, "total": 2}
{"event": "delegation", "phase": "agent_end", "delegation_id": "...", "agent": "billing", "status": "completed", "summary": "...", "index": 0, "total": 2}
{"event": "delegation", "phase": "end", "delegation_id": "...", "status": "completed", "mode": "parallel"}
```

`scene/h5` v1：将同一载荷挂到 `action` channel（如 `delegation.start`）；字段与上表相同。非首版验收阻塞项。

### 6.3 前端

- 折叠委派卡片：显示 mode、各项 agent 状态、一行 summary
- 展开仅更多 metadata，不拉子会话全文
- `useSSE` 识别 `delegation` 写入当前 turn；`delegate_task` 用委派卡替代通用 tool 卡，避免双份 UI
- 历史 hydrate：从父会话 ToolResult.details 恢复折叠卡

### 6.4 API

| 接口 | 行为 |
|------|------|
| `POST /chat/stream` | 绑定 owner；启用多 Agent（若配置 profiles） |
| `GET /sessions` | 仅当前 owner |
| `GET/DELETE /session` | owner 校验；DELETE 级联子会话 |
| `GET /session/messages` | 父会话 transcript |

可选后续：客服后台 `GET` 子会话轨迹。

## 7. 测试与验收

### 7.1 库测试

- Registry：注册/解析/format
- Factory：isolated/forked、工具白名单、默认无嵌套 delegate
- Runner：三 mode、`{previous}`、并发上限、abort
- 集成：FakeProvider 编排器 → `delegate_task` → 子结果回灌

### 7.2 Scene 验收

1. 用户 A/B 会话互不可见  
2. 触发委派出现折叠卡，主 Agent 汇总回复  
3. parallel 显示多项进度  
4. chain 第二步使用上一步结果  
5. 刷新后父历史与委派终态可恢复  
6. abort 级联停止子 Agent  

### 7.3 成功标准

多用户可在有状态 Scene 中与编排器对话；编排器通过 `delegate_task` 以 single/parallel/chain 调用专家；用户看到可折叠进度而非子 Agent 全文；会话按 owner 隔离且可恢复。

## 8. 风险

| 风险 | 级别 | 缓解 |
|------|------|------|
| 双层 LLM 延迟 | 中 | 轻量编排模型；进度 SSE；profile 独立模型 |
| Abort 未传播 | 中 | handle.abort_all + signal 链接 + 测试 |
| forked 存储膨胀 | 中 | 默认 isolated；级联删除 |
| 伪造 session_id 越权 | 高 | 读写均校验 owner |
| 工具名冲突 | 低 | `delegate_tool_name` 可配 |
| 并行打满限流 | 中 | 双层信号量 |
| 乱路由 | 中 | routing_prompt + description；非法名 tool error |

## 9. 实施顺序

1. `types` + `AgentProfileRegistry`  
2. `SessionHeader.owner` + `list_sessions` 过滤 + `fork_session`  
3. `SubAgentFactory` + `SubAgentRunner`（三 mode）  
4. `DelegateTaskTool` + `create_multi_agent_harness`  
5. 库测试绿灯  
6. ChatAssistant / SessionManager / SSE  
7. 前端折叠委派卡  
8. 示例 profiles + 端到端验收  

预估：库约 600–900 行；`AgentHarness` 仅小改动。

## 10. 后续扩展（接口预留，不做）

- `tenant_id` 与租户级 Profile/工具 ACL  
- Handoff（`transfer_to_agent`）  
- 子会话后台查看 API  
- ConversationFactory / 水平扩展  
- RAG 作为 knowledge profile 工具  
- 嵌套委派白名单启用  

## 11. 参考

- `docs/multi-agent-harness-design.md`
- `docs/cloud-agent-framework-design.md`
- `pi-example/harness/doc/agent-harness.md`
- `pi-example/harness/session/repo-utils.ts`（`getEntriesToFork`）
- `agent_core/session/harness.py`
- `scene/http_sse/manager.py` / `chat_assistant.py` / `events.py`
