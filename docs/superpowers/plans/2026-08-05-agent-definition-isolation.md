# Agent Definition 隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入一等公民 `AgentDefinition`，实现「用户 × Agent」会话隔离，以及 Agent 级私有/公用 MCP 工具与知识库组装。

**Architecture:** 进程内维护公用 MCP 连接池 + 按 `agent_id` 的私有 MCP 池；创建会话时根据 `AgentDefinition` 合并工具与知识库到该会话的 `ToolRegistry`；`SessionHeader` 增加 `agent_id`，列表/读写按 `owner` + `agent_id` 过滤。

**Tech Stack:** Python 3.11+, pydantic, 现有 `MCPManager` / `LocalKnowledgeBase` / `SessionStore` / `scene/http_sse`

**决策依据：** 方案 2（AgentDefinition），已与需求方确认（2026-08-05）。

---

## 0. 需求定稿（Locked）

### 0.1 已确认需求

| # | 需求 | 验收口径 |
|---|------|----------|
| R1 | 同一用户与不同 Agent 的聊天记录隔离 | `list_sessions(owner, agent_id=A)` 不含 Agent B 的会话；加载会话时校验 `header.agent_id` |
| R2 | 不同用户互不可见 | 沿用现有 `owner` 校验；跨 owner 读写抛 `PermissionError` |
| R3 | Agent 可有私有 MCP 工具列表 | `AgentDefinition.mcp.private` 中的 server 仅该 Agent 可见 |
| R4 | Agent 可引用公用 MCP / 内置工具 | `mcp.shared` + `tools.builtin` 合并进该 Agent 的 registry |
| R5 | Agent 可有私有知识库，也可引用公用知识库 | 本地目录 `shared/` + `agents/<id>/`；亦可引用 MCP `type=knowledge` |
| R6 | 多人可同时使用 | 不同 `session_id` 并发；同 session 仍由 Harness Phase Guard 串行 |

### 0.2 非目标（本期不做）

- 完整多租户：`tenant_id`、配额、per-tenant 模型凭证/成本隔离
- 跨 Agent 共享同一会话历史 / Handoff
- 进程外沙箱隔离 MCP
- 改写 `demo/`、改写 `core/loop.py` 状态机
- 强制废弃 Persona API（保留兼容层，见 §4）

### 0.3 术语

| 术语 | 含义 |
|------|------|
| **AgentDefinition** | 业务侧「一个 Agent」的配置：提示词、工具、MCP、知识库 |
| **shared MCP** | 进程级公用连接，多个 Agent 可引用同一 server 名 |
| **private MCP** | 仅某一 Agent 使用的 MCP server（独立连接，按 agent_id 管理） |
| **shared KB** | `.pi/knowledge/shared/` 下文档，可被多个 Agent 引用 |
| **private KB** | `.pi/knowledge/agents/<agent_id>/` 下文档，仅该 Agent |
| **owner** | 终端用户标识（现有 `uid` / `user_id`） |
| **agent_id** | AgentDefinition.id；会话归属字段 |

### 0.4 与现状差距

| 现状 | 问题 |
|------|------|
| `SessionManager` 进程级单例 `MCPManager` | 所有会话共享全部 MCP 工具，无法做 Agent 私有 MCP |
| Persona 仅有 `enabled_tools` / `knowledge_bases` 白名单 | 只能过滤，不能声明私有连接；语义过载 |
| 本地 KB 固定 `.pi/knowledge` | 无 shared/private 目录模型 |
| `SessionHeader` 仅有 `owner` | 无法按 Agent 列会话；换 persona 可能重建同一 session 语义混乱 |
| `docs/design.md` 称 MCP 未落地 | 文档过时；代码已有 `mcp_tool.py` |

---

## 1. 目标架构

### 1.1 配置模型

```
.pi/
├── agents/                      # AgentDefinition JSON（新建）
│   ├── support.json
│   └── analyst.json
├── mcp/
│   ├── shared.mcp.json          # 公用 MCP（从现有 .mcp.json 迁移）
│   └── agents/
│       ├── support.mcp.json     # support 私有 MCP
│       └── analyst.mcp.json
├── knowledge/
│   ├── shared/                  # 公用 KB 文档
│   └── agents/
│       ├── support/
│       └── analyst/
└── personas/                    # 保留；可被 AgentDefinition 引用或逐步迁移
```

**AgentDefinition JSON 示例：**

```json
{
  "id": "support",
  "name": "客服助手",
  "description": "售后咨询",
  "system_prompt": "你是客服助手…",
  "tools": {
    "builtin": ["read", "confirm", "show_widget"],
    "shared_mcp": ["amap", "tavily"],
    "private_mcp": ["crm-db"]
  },
  "knowledge": {
    "shared": ["product-faq"],
    "private": ["refund-policy"],
    "shared_mcp_knowledge": [],
    "private_mcp_knowledge": ["crm-kb"]
  }
}
```

字段语义：

- `tools.builtin`：内置工具名白名单；`null`/`omit` = 不限制内置（仅受 MCP 列表约束时需明确文档）
- `tools.shared_mcp`：公用 MCP **server 名**列表（引用 `shared.mcp.json`）
- `tools.private_mcp`：私有 MCP **server 名**列表（引用 `agents/<id>.mcp.json`）
- `knowledge.shared` / `private`：本地文档目录名（相对对应 root）
- `*_mcp_knowledge`：MCP server 名且 `type=knowledge`

**兼容默认：** 若缺少 `tools`/`knowledge` 块，行为等同「仅内置全开 + 全部 shared MCP + shared KB」（便于迁移期）。

### 1.2 运行时组装

```
请求 (owner, agent_id, session_id?)
        │
        ▼
┌───────────────────┐
│ AgentRegistry     │  load AgentDefinition
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ MCPPool           │  shared adapters
│                   │  + private adapters[agent_id]
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ assemble_tools()  │  builtin ∩ whitelist
│                   │  + shared MCP tools (by server name)
│                   │  + private MCP tools
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ assemble_kb()     │  LocalKB(shared ∩ names)
│                   │  + LocalKB(agents/id ∩ names)
│                   │  + MCP knowledge tools
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ SessionStore      │  header: owner + agent_id
│ ChatAssistant     │  每会话独立 ToolRegistry
└───────────────────┘
```

### 1.3 会话隔离规则

1. 新建会话：生成 `session_id`，`SessionHeader.owner` / `agent_id` 写入 store。
2. 列表：`list_sessions(owner=..., agent_id=...)`；`agent_id=None` 时返回该 owner 下全部 Agent 会话（可选，需带 `agent_id` 字段）。
3. 读写/删除：除 `owner` 校验外，若请求带 `agent_id`，必须与 `header.agent_id` 一致。
4. **禁止**把已有会话绑定到另一个 `agent_id`（重建需新 session）。
5. 同 `owner` + 同 `agent_id` 可有多个 session（多轮对话并行）。

### 1.4 MCP 生命周期

| 池 | 启动 | 停止 | 可见性 |
|----|------|------|--------|
| shared | `SessionManager.start()` 连接 `shared.mcp.json` | 进程退出 | 被 Agent 的 `shared_mcp` 引用才进入该 Agent registry |
| private | 首次需要该 `agent_id` 时懒加载；或 start 时预加载已配置 agents | Agent 卸载 / 进程退出 | 仅该 agent_id |

实现要点：

- 抽取现有 `MCPManager` 为可多实例；新增 `MCPPool` 包装 shared + `dict[agent_id, MCPManager]`。
- `register_tools_for_agent(registry, agent_def)`：按 server 名过滤 adapters，再 register。
- 工具名冲突：私有优先于公用；同名二次 register 打 warning 并覆盖（与现有 `ToolRegistry` 行为一致）。

### 1.5 知识库模型

```
.pi/knowledge/
  shared/<doc_name>/...
  agents/<agent_id>/<doc_name>/...
```

- `LocalKnowledgeBase` 支持多 root 或新增 `CompositeKnowledgeBase`（多个 LocalKB 顺序检索合并）。
- Agent 组装时：只索引声明的 `shared`/`private` 文档名；空列表 = 该层不启用；`["*"]` = 该层全部（可选便利语法，首版可用显式名单，避免隐式）。
- 自动检索（若 ChatAssistant 已有 pre-LLM inject）：仅使用该 Agent 组装后的 composite retriever。

### 1.6 API / Scene 变更（验收宿主：`scene/http_sse`）

| 端点/参数 | 变更 |
|-----------|------|
| `POST /chat/stream` | 增加 `agent_id`（推荐）；`persona_id` 保留为兼容别名 → 映射到 agent |
| `GET /sessions` | 支持 `agent_id` 过滤；响应增加 `agent_id` |
| `GET /agents` | 新建：列表 AgentDefinition |
| `POST /agents` / `DELETE /agents` | 新建：CRUD（对称现有 personas） |
| `GET /personas` | 保留；内部可读 agents 或双写迁移期 |
| knowledge API | 支持 `scope=shared\|agent` + `agent_id` |
| connectors API | 支持 `scope=shared\|agent` + `agent_id` |

前端（H5/桌面）最低要求：选 Agent 后带 `agent_id` 建会话、列历史按 Agent 过滤。可放在 Phase 4，不阻塞库层合并。

---

## 2. 文件结构

### 2.1 新建

| 文件 | 职责 |
|------|------|
| `agent_core/resources/agents.py` | `AgentDefinition` dataclass + load/save/delete/list |
| `agent_core/tools/mcp_pool.py` | `MCPPool`：shared + private managers；按 agent 过滤 adapters |
| `agent_core/knowledge/composite.py` | 多 root / 多 LocalKB 合并检索 |
| `agent_core/session/agent_binding.py` | 纯函数：校验 session↔agent、组装 header 字段（可选，避免逻辑散落） |
| `tests/resources/test_agents.py` | AgentDefinition 加载/校验 |
| `tests/tools/test_mcp_pool.py` | shared/private 过滤与冲突 |
| `tests/knowledge/test_composite_kb.py` | 合并检索与范围 |
| `tests/session/test_agent_id_filter.py` | store 按 agent_id 过滤 |
| `tests/scene/test_agent_isolation_http.py` | 可选：http_sse 集成（FakeProvider） |
| `.pi/agents/*.json` | 示例 Agent（从现有 personas 迁移 1–2 个） |
| `.pi/mcp/shared.mcp.json` | 从根 `.mcp.json` 迁移 |

### 2.2 修改

| 文件 | 修改 |
|------|------|
| `agent_core/session/store.py` | `SessionHeader.agent_id`；`SessionMeta.agent_id`；`list_sessions(..., agent_id=)` |
| `agent_core/session/inmemory_store.py` | 同上过滤 |
| `agent_core/session/jsonl_store.py` | 同上 |
| `agent_core/session/sqlite_store.py` | 同上（无强制 schema migration：header JSON 内字段） |
| `agent_core/tools/mcp_tool.py` | 小改：支持从指定路径 load；保持 `MCPManager` 可单测 |
| `agent_core/knowledge/local_kb.py` | 允许自定义 root；文档列举 API 按 root |
| `scene/http_sse/manager.py` | 使用 `MCPPool`；`get_or_create(..., agent_id=)`；owner+agent 校验 |
| `scene/http_sse/chat_assistant.py` | 按 `AgentDefinition` 组装 tools/KB；Persona 兼容路径 |
| `scene/http_sse/server.py` | `/agents` CRUD；chat/sessions/knowledge/connectors 参数 |
| `docs/design.md` | 更新 MCP 已实现 + AgentDefinition 简述（收尾时） |
| `docs/api-event-spec-v1.md` | 补充 `agentId` / `/agents`（收尾时） |

### 2.3 明确不改

- `agent_core/core/loop.py`
- `demo/**`
- 多租户配额相关（phase2 §8.3 仍为远期）

---

## 3. 分阶段任务

### Phase 1 — AgentDefinition + Session `agent_id`（库层）

**目标：** 配置可加载；会话可按 agent 隔离存储/列表。无 MCP/KB 行为变化也可合并。

#### Task 1.1: AgentDefinition 资源模块

**Files:**
- Create: `agent_core/resources/agents.py`
- Test: `tests/resources/test_agents.py`

- [x] **Step 1: 写失败测试**

```python
# tests/resources/test_agents.py
from pathlib import Path
from agent_core.resources.agents import AgentDefinition, load_agents, get_agent, save_agent

def test_load_agent_with_private_and_shared(tmp_path: Path):
    agents_dir = tmp_path / ".pi" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "support.json").write_text(
        '{"id":"support","name":"客服","system_prompt":"hi",'
        '"tools":{"builtin":["read"],"shared_mcp":["amap"],"private_mcp":["crm"]},'
        '"knowledge":{"shared":["faq"],"private":["refund"]}}',
        encoding="utf-8",
    )
    agent = get_agent("support", cwd=str(tmp_path))
    assert agent is not None
    assert agent.tools.shared_mcp == ["amap"]
    assert agent.tools.private_mcp == ["crm"]
    assert agent.knowledge.private == ["refund"]
```

- [x] **Step 2: 实现 `AgentDefinition` / `AgentTools` / `AgentKnowledge` + load/save/get/delete**
- [x] **Step 3: `pytest tests/resources/test_agents.py -v` PASS**
- [x] **Step 4: Commit** `feat(resources): add AgentDefinition loader`

#### Task 1.2: SessionHeader / list_sessions 支持 agent_id

**Files:**
- Modify: `agent_core/session/store.py`, `inmemory_store.py`, `jsonl_store.py`, `sqlite_store.py`
- Test: `tests/session/test_agent_id_filter.py`（或扩展现有 `tests/session/test_store.py`）

- [x] **Step 1: 失败测试**

```python
async def test_list_sessions_filters_by_agent_id(store):
    await store.create_session("s1", SessionHeader(id="s1", timestamp="t", owner="u1", agent_id="support"))
    await store.create_session("s2", SessionHeader(id="s2", timestamp="t", owner="u1", agent_id="analyst"))
    metas = await store.list_sessions(owner="u1", agent_id="support")
    assert [m.session_id for m in metas] == ["s1"]
    assert metas[0].agent_id == "support"
```

- [x] **Step 2: 扩展 Protocol 与三后端；缺省 `agent_id=""` 兼容旧会话**
- [x] **Step 3: pytest PASS**
- [x] **Step 4: Commit** `feat(session): filter sessions by agent_id`

**验收 Phase 1：** 单测覆盖 load agent + list 过滤；旧 session（无 agent_id）仍可列出（`agent_id=""`）。

---

### Phase 2 — MCPPool（私有 + 公用）

**目标：** 按 Agent 组装可见 MCP 工具集。

#### Task 2.1: 配置路径拆分

**Files:**
- Modify: `agent_core/tools/mcp_tool.py`（`load_mcp_server_configs(path|cwd)`）
- Create: 默认读 `.pi/mcp/shared.mcp.json`，fallback 根目录 `.mcp.json` / `MCP_SERVERS`

- [x] 测试：指定 path 加载；fallback 行为不变
- [x] Commit: `refactor(mcp): load configs from explicit path`

#### Task 2.2: MCPPool

**Files:**
- Create: `agent_core/tools/mcp_pool.py`
- Test: `tests/tools/test_mcp_pool.py`

核心 API（实现须与此一致）：

```python
class MCPPool:
    def __init__(self, *, shared: MCPManager, cwd: str = "") -> None: ...

    async def start_shared(self) -> None: ...

    async def ensure_private(self, agent_id: str) -> MCPManager:
        """Load .pi/mcp/agents/<agent_id>.mcp.json if needed."""
        ...

    def adapters_for_agent(self, agent: AgentDefinition) -> list[MCPToolAdapter]:
        """Union of shared∩shared_mcp and private∩private_mcp (+ knowledge servers)."""
        ...

    def register_tools(self, registry: ToolRegistry, agent: AgentDefinition) -> int: ...

    async def stop(self) -> None: ...
```

- [x] 用假 adapter / mock connection 测过滤与私有优先
- [x] Commit: `feat(mcp): add MCPPool for shared/private agents`

#### Task 2.3: ChatAssistant / SessionManager 接入 MCPPool

**Files:**
- Modify: `scene/http_sse/manager.py`, `chat_assistant.py`

- [x] `SessionManager.start` 创建 `MCPPool` 并 `start_shared`
- [x] `ChatAssistant.create(..., agent: AgentDefinition | None)`：若有 agent，用 `mcp_pool.register_tools`；否则保持旧「全量 register」兼容
- [x] 单测或 scene 级测试：两个 agent 不同 private MCP，互不可见
- [x] Commit: `feat(scene): assemble MCP tools per AgentDefinition`

**验收 Phase 2：** Agent A 的 registry 不含 Agent B 的 private MCP 工具名。

---

### Phase 3 — 知识库 shared / private

**目标：** 与 MCP 对称的 KB 隔离。

#### Task 3.1: CompositeKnowledgeBase

**Files:**
- Create: `agent_core/knowledge/composite.py`
- Modify: `local_kb.py`（root 参数化，若尚未支持）
- Test: `tests/knowledge/test_composite_kb.py`

```python
class CompositeKnowledgeBase:
    def __init__(self, retrievers: list[Any]) -> None: ...
    async def retrieve(self, query: str, limit: int = 5) -> list[RetrievedChunk]: ...
```

- [x] 两个 root 各放一篇文档，复合检索能命中声明范围；未声明 root 不命中
- [x] Commit: `feat(knowledge): composite retriever for shared/private roots`

#### Task 3.2: 按 Agent 组装 KB + scene knowledge API

**Files:**
- Modify: `chat_assistant.py`（替换单一 `LocalKnowledgeBase(cwd/.pi/knowledge)`）
- Modify: `server.py` knowledge 路由增加 `scope` / `agent_id`

目录约定：

- shared docs → `.pi/knowledge/shared/<name>/`
- private docs → `.pi/knowledge/agents/<agent_id>/<name>/`

迁移：现有 `.pi/knowledge/<name>/` 视为 **shared**（启动时文档说明；可选一次性搬迁脚本，非必须）。

- [x] Commit: `feat(knowledge): per-agent shared/private knowledge roots`

**验收 Phase 3：** Agent A 自动/工具检索不到 Agent B private 目录文档；二者均可检索 shared 中已声明文档。

---

### Phase 4 — Scene API 与兼容层

**目标：** HTTP 面可运行验收；Persona 平滑过渡。

#### Task 4.1: `/agents` CRUD + chat/sessions 参数

**Files:**
- Modify: `scene/http_sse/server.py`, `manager.py`

规则：

```
agent_id 优先于 persona_id
若仅有 persona_id：
  1) 尝试 get_agent(persona_id)
  2) 否则 get_persona(persona_id) → 运行时合成临时 AgentDefinition
     （tools.builtin = persona.enabled_tools；knowledge 从 persona.knowledge_bases 映射）
```

- [x] `GET /sessions?agent_id=support` 只返回该 Agent
- [x] 创建 session 写入 `header.agent_id`
- [x] 用错误 agent_id 访问他人会话 → 403/PermissionError
- [x] Commit: `feat(http_sse): agent_id on chat and sessions APIs`

#### Task 4.2: connectors / knowledge scope

- [x] shared connectors 读写 `.pi/mcp/shared.mcp.json`
- [x] agent connectors 读写 `.pi/mcp/agents/<id>.mcp.json`，并 `ensure_private` + reload
- [x] Commit: `feat(http_sse): scoped connectors and knowledge APIs`

#### Task 4.3: 示例配置与手动验收清单

- [x] 新增 `.pi/agents/support.json`、`.pi/agents/analyst.json`（可从 coder/general personas 改编）
- [x] 迁移说明写入本计划「运维」节（已含）
- [x] 手动验收（见 §5）— 由自动化集成测试覆盖（V1–V7 对应行为见 `tests/scene/test_agent_http_api.py`、`test_agent_mcp_wiring.py`、`test_agent_kb_wiring.py`、`test_connectors_scope.py`）；live 双用户手动跑通待执行（见 §9 边界）
- [x] Commit: `chore: sample AgentDefinitions and mcp path layout`

**验收 Phase 4：** 两用户 × 两 Agent 交叉矩阵通过 §5 清单。

---

### Phase 5 — 文档与收尾

- [x] 更新 `docs/design.md`：删除「MCP 未实现」；增加 AgentDefinition 一节
- [x] 更新 `docs/api-event-spec-v1.md`：`agentId`、`/agents`
- [x] 追加 `docs/development-log/2026-MM-DD.md`（提交日）
- [x] 对照本计划 §0 需求表做一次自检，勾选完成项

---

## 4. Persona 兼容策略

| 阶段 | 行为 |
|------|------|
| 本期 | Persona CRUD API 保留；内部优先 AgentDefinition |
| 映射 | `persona_id` → 同名 `agent_id`；无同名 agent 则临时合成 |
| 后续（另计划） | UI 只暴露 Agents；Personas 标 deprecated |

**禁止：** 在同一 `session_id` 上切换 `agent_id` 并继续追加历史（应新建 session）。

---

## 5. 验收清单（手动 / 集成）

用两个测试用户 `u1`/`u2`，两个 Agent `support`/`analyst`：

| # | 步骤 | 期望 |
|---|------|------|
| V1 | u1 对 support 发消息，再对 analyst 发消息 | 两条会话 `agent_id` 不同；列 support 不见 analyst 历史 |
| V2 | u2 列 sessions | 不见 u1 任何会话 |
| V3 | support 私有 MCP 工具名出现在 capabilities；analyst 不可见该工具 | 过滤正确 |
| V4 | 二者均可调用同一 shared MCP（如 tavily） | 公用可用 |
| V5 | shared KB 文档两边（若声明）可检索；private 仅归属 Agent | KB 隔离 |
| V6 | 旧客户端只传 `persona_id=coder` | 仍可对话（兼容路径） |
| V7 | 并发：u1-support 与 u2-analyst 同时 stream | 互不干扰、无串会话 |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 私有 MCP 懒加载首请求变慢 | start 时预加载已配置 agents；或健康检查预热 |
| 工具名跨 MCP 冲突 | 私有优先 + warning 日志；后续可加 `server__tool` 前缀（另议，本期不加） |
| 旧 knowledge 目录结构 | 无 `shared/` 时把旧扁平目录当作 shared root fallback |
| sqlite/jsonl 旧 header 无 agent_id | 默认 `""`；过滤 `agent_id=X` 时不返回旧会话（或仅 `agent_id=None` 时返回）——**采用：缺省空字符串，显式过滤时不匹配空** |
| 文档与代码双源（Persona+Agent） | Phase 4 映射表 + API 文档标明优先字段 |

---

## 7. 建议排期

| Phase | 预估 | 可合并 PR |
|-------|------|-----------|
| 1 AgentDefinition + session agent_id | 1–2 日 | 是 |
| 2 MCPPool | 2–3 日 | 是 |
| 3 Knowledge | 1–2 日 | 是 |
| 4 Scene API + 示例 | 2 日 | 是 |
| 5 文档收尾 | 0.5 日 | 与 Phase 4 同 PR 亦可 |

总计约 **1–1.5 周**（单人，含测试）。

---

## 8. 运维迁移步骤（部署时）

1. 创建目录：`.pi/agents/`、`.pi/mcp/`、`.pi/knowledge/shared/`、`.pi/knowledge/agents/`
2. 将现有根目录 `.mcp.json` 复制/移动为 `.pi/mcp/shared.mcp.json`（保留 fallback 可读旧路径）
3. 将需要隔离的 MCP 条目拆到 `.pi/mcp/agents/<id>.mcp.json`
4. 为每个业务 Agent 写 `.pi/agents/<id>.json`
5. （可选）将原 `.pi/knowledge/<doc>` 移到 `shared/<doc>`
6. 客户端改为传 `agent_id`；观察 logs 中 persona 兼容告警

---

## 9. Spec 覆盖自检

| 需求 | 对应任务 | 状态（2026-08-06 实现后） |
|------|----------|----------|
| R1 用户×Agent 聊天隔离 | Task 1.2, 4.1, V1 | ✅ `list_sessions(owner, agent_id)` 过滤；加载校验 `header.agent_id`；禁止改绑 |
| R2 用户间隔离 | 现有 owner + Task 4.1, V2 | ✅ 沿用 owner 校验 + agent 绑定校验（403） |
| R3 私有 MCP | Task 2.2–2.3, V3 | ✅ `MCPPool` 私有池按 agent_id 隔离；测试互不可见 |
| R4 公用 MCP/内置 | Task 2.2–2.3, V4 | ✅ shared MCP 按 server 名合并；`tools.builtin` 白名单（agent 路径） |
| R5 私有/公用 KB | Phase 3, V5 | ✅ `ScopedKnowledgeBase` + `CompositeKnowledgeBase`，scope 前缀防重名冲突 |
| R6 多人并发 | 现有 session 模型 + V7 | ✅ 不同 session_id 并发；同 session 由 Harness 串行（池单飞锁） |
| Persona 兼容 | §4, Task 4.1, V6 | ✅ persona_id → 同名 agent 优先；否则原 persona 路径（不合成，见下） |
| 非目标未膨胀 | §0.2 明确排除 tenant 配额等 | ✅ 未引入 tenant/配额/进程外沙箱 |

**已知边界（本期接受，未封口）**：

1. **store 重启边界**：agent-bound 会话不在内存（服务重启）时，persona-only 请求仍可能把它重建为 persona 会话（`_assert_rebind_allowed` 仅守卫内存中的会话）。罕见路径。
2. **Persona 合成不做**：`Persona.enabled_tools` 是工具**名称**扁平白名单，`AgentDefinition.tools` 按 MCP **server** 名选择——合成会静默丢 MCP 工具，故兼容路径保留原 persona 行为。
3. **h5 scene**（`scene/h5/`）未同步 http_sse 的 agent/kb/mcp 改造（§1.6 验收宿主为 `scene/http_sse`）。
4. **live 手动验收**（§5 V1–V7 双用户矩阵）由自动化集成测试覆盖，尚未实际起服跑通。

---

## 10. 执行方式

Plan 已保存。实现时可选用：

1. **Subagent-Driven（推荐）** — 每 Task 新开 subagent，Task 间人工/主 agent review  
2. **Inline Execution** — 本会话按 Phase 连续实现并设检查点  

开始前建议先从 **Phase 1 / Task 1.1** 开做，保持小步可合并。
