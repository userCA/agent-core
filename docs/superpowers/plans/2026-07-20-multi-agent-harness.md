# Multi-Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `agent_core` 落地 Harness-in-Tool 多 Agent 编排（single/parallel/chain），并让 `scene/http_sse` 支持 owner 隔离与委派进度 SSE/折叠 UI。

**Architecture:** `create_multi_agent_harness` 返回标准 `AgentHarness` + `MultiAgentHandle`；`delegate_task` 工具经 `SubAgentRunner` 进程内启动子 harness；进度经 `ToolResult.details.delegation` 与 SSE `delegation` 帧透出；SessionStore 增加 `owner` 过滤与 `fork_session`。

**Tech Stack:** Python 3.11+, pydantic, pytest-asyncio, React/TS (scene/http_sse/static)

**Spec:** `docs/superpowers/specs/2026-07-20-multi-agent-harness-design.md`

---

## 文件结构

### 新建

| 文件 | 职责 |
|------|------|
| `agent_core/multi_agent/__init__.py` | 公共导出 |
| `agent_core/multi_agent/types.py` | Profile/Options/Result/Handle/modes |
| `agent_core/multi_agent/profile_registry.py` | 注册表 + XML 提示词 |
| `agent_core/multi_agent/sub_agent_factory.py` | 子 session + 子 harness |
| `agent_core/multi_agent/sub_agent_runner.py` | 三 mode + 信号量 + abort |
| `agent_core/multi_agent/delegate_tool.py` | `delegate_task` Tool |
| `agent_core/multi_agent/factory.py` | `create_multi_agent_harness` |
| `tests/multi_agent/test_profile_registry.py` | Registry 测试 |
| `tests/multi_agent/test_store_fork_owner.py` | owner/fork 测试 |
| `tests/multi_agent/test_sub_agent_runner.py` | Runner 三 mode/abort |
| `tests/multi_agent/test_factory.py` | 集成：编排器 → delegate |
| `scene/http_sse/multi_agent_profiles.py` | 示例客服 profiles |
| `scene/http_sse/static/src/components/chat/DelegationCard.tsx` | 折叠委派卡 |

### 修改

| 文件 | 修改 |
|------|------|
| `agent_core/session/store.py` | `SessionHeader.owner`；Protocol `fork_session` |
| `agent_core/session/inmemory_store.py` | owner 过滤 + fork |
| `agent_core/session/jsonl_store.py` | 同上 |
| `agent_core/session/sqlite_store.py` | 同上 |
| `scene/http_sse/chat_assistant.py` | 多 Agent 工厂接入 |
| `scene/http_sse/manager.py` | owner 校验 + 级联删子会话 |
| `scene/http_sse/server.py` | 解析 owner |
| `scene/http_sse/events.py` | delegation SSE |
| `scene/http_sse/static/src/hooks/useSSE.ts` | 消费 delegation |
| 相关前端 store/组件 | 折叠卡渲染 |

---

### Task 1: types + AgentProfileRegistry

**Files:**
- Create: `agent_core/multi_agent/types.py`, `profile_registry.py`, `__init__.py`
- Test: `tests/multi_agent/test_profile_registry.py`

- [x] Write failing tests for register/resolve/format_for_system_prompt
- [x] Implement types + registry
- [x] `pytest tests/multi_agent/test_profile_registry.py -v` PASS

### Task 2: SessionStore owner + fork_session

**Files:**
- Modify: `store.py`, `inmemory_store.py`, `jsonl_store.py`, `sqlite_store.py`
- Test: `tests/multi_agent/test_store_fork_owner.py` (+ extend `tests/session/test_store.py` if needed)

- [x] Failing tests: list by owner; fork copies entries
- [x] Implement across three backends
- [x] pytest PASS

### Task 3: SubAgentFactory + SubAgentRunner

**Files:**
- Create: `sub_agent_factory.py`, `sub_agent_runner.py`
- Test: `tests/multi_agent/test_sub_agent_runner.py`

- [x] Failing tests: single/parallel/chain/{previous}/abort/concurrency
- [x] Implement factory + runner (FakeProvider)
- [x] pytest PASS

### Task 4: DelegateTaskTool + create_multi_agent_harness

**Files:**
- Create: `delegate_tool.py`, `factory.py`; update `__init__.py`
- Test: `tests/multi_agent/test_factory.py`

- [x] Failing integration test: orchestrator calls delegate_task, gets tool result
- [x] Implement tool + factory
- [x] pytest PASS

### Task 5: Scene 后端（owner + multi-agent + SSE）

**Files:**
- Modify: `chat_assistant.py`, `manager.py`, `server.py`, `events.py`
- Create: `multi_agent_profiles.py`

- [x] Wire profiles → factory; abort_all; owner isolation; delegation SSE frames
- [x] Smoke: import + unit-level event mapping test if feasible

### Task 6: 前端折叠委派卡

**Files:**
- Create: `DelegationCard.tsx`
- Modify: `useSSE.ts` + message list 渲染路径

- [x] SSE `delegation` → store → 折叠卡；delegate_task 不双份 tool 卡
- [ ] 历史 hydrate 从 tool details（可后续：从 tool_result.details 恢复）

### Task 7: 验收与开发日志

- [x] `pytest tests/multi_agent/ tests/session/test_store.py -v`
- [ ] 更新 `docs/development-log/2026-07-20.md`（提交时）
- [x] Spec 状态改为实施中

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| ProfileRegistry + XML | 1 |
| owner + fork | 2 |
| single/parallel/chain + abort | 3 |
| create_multi_agent_harness + delegate_task | 4 |
| Scene owner/SSE/profiles | 5 |
| 折叠 UI | 6 |
| 库测试绿灯 | 3–4, 7 |
