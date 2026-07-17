# AgentHarness 语义补全 Implementation Plan（修订版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **修订说明（2026-07-17）：** 取代原「Step 1–7 从零补齐」叙事。P0/P1/P3 骨架与 Step 1–6 API **大多已存在**；本版目标是修语义空洞、钉死时序契约、收敛双份职责，再补 Provider/stream。对照参考：`pi-example/harness/`、`pi-example/harness/doc/agent-harness.md`。

**Goal:** 让 Python `AgentHarness`（`AgentSession` 别名）在 pending flush、runtime setter、失败事件、compact、active tools、lifecycle 事件顺序上具备可验证、可持久化的真实语义，而不是脚手架假完成。

**Architecture:** Thin Core（`loop.py` 纯 emit-sink 循环）+ Thick Harness（`session/session.py` 拥有队列、pending writes、持久化、settled、setter）。`Agent` 只负责跑 loop、构造 turn snapshot、在无 harness 时提供 standalone 路径。Save point = flush pending → `prepare_next_turn` 刷新 snapshot → emit `SavePoint`；不重建 loop callbacks。

**Tech Stack:** Python 3.11+ / pytest-asyncio / 现有 `FakeProvider`（`tests/conftest.py`）/ `InMemorySessionStore`

---

## 0. 现状盘点（禁止再做）

### 0.1 已完成（不要重写）

| 能力 | 位置 | 备注 |
|------|------|------|
| Phase 状态机 | `state.py` `AgentHarnessPhase` | `BRANCH_SUMMARY`/`RETRY` 仍未使用，本版不实现 |
| Emit sink `run_agent_loop` | `loop.py` | 旧 `agent_loop` 保持 deprecated |
| TurnSnapshot + save point | `context.py`, `loop.py`, `agent.py` | 字段偏瘦 → P1 扩展 |
| `AgentHooks` + 部分 reducer | `hooks.py` | compact cancel 缺 reducer → P0 |
| `AgentHarnessError` 类型 | `errors.py` | `normalize_*` 未接线 → P0 |
| 可观测事件类 | `events.py` | `ResourcesUpdate` 等事件类已有，setter 未齐 |
| Setter / pending / Settled / Abort API | `agent.py`, `session.py` | **语义空洞** → P0 |
| `_emit_run_failure` 四事件流 | `agent.py` | 绕过 harness → P0 |
| `compact()` API | `agent.py` | auto-compact 不经 phase → P0 |

### 0.2 假完成清单（本版必须修）

| # | 空洞 | 证据 |
|---|------|------|
| H1 | `_flush_pending_writes` 只 pop+debug，不写 store | `session.py:333-337` |
| H2 | setter 不区分 idle/busy；idle 也不立即 persist | `session.py:343+` |
| H3 | `set_active_tools` 不改运行时工具过滤 | `session.py:389-403` |
| H4 | `session_before_compact` 无 reducer，cancel 死路径 | `hooks.py:170-178` |
| H5 | `_maybe_compact` 不经 `agent.compact()` / COMPACTION phase | `session.py:539+` |
| H6 | `_emit_run_failure` 固定走 `agent._handle_event`，跳过 harness 持久化 | `agent.py:627-630` vs `583-589` |
| H7 | `normalize_harness_error` / `normalize_hook_error` 无调用点 | 仅导出 |
| H8 | `Settled.next_turn_count` 永不赋值；无 nextTurn 队列 | `events.py` |
| H9 | `QueueUpdate` 经 `create_task` fire-and-forget | 违背 await settlement |
| H10 | Agent 与 Harness 双份 hooks/queues/pending/setters | 架构债 → P2 收敛 |

### 0.3 本版明确不做

| 项 | 原因 |
|----|------|
| 树形 Session / `navigateTree` / `BRANCH_SUMMARY` | 聊天场景不需要 |
| 半持久化恢复（durable harness） | TS 也仅有设计文档 |
| Hook context facade / `runWhenIdle` | 依赖完整 reentrancy 套件后再做 |
| 把 `Agent` 从 loop 路径完全删除 | 过大；P2 只收敛，不删除 standalone |
| 泛型 `HookEvent<TResult>` | Python 收益低 |
| 盲抄 TS settled 时序而不写测试 | TS 自身仍标 provisional |

---

## 1. 锁定的生命周期契约（先契约，后代码）

实现任何 Task 前，以本节为准。与 TS 冲突时**采用本节**，并在测试中钉死。

### 1.1 Phase

| Phase | 允许的操作 |
|-------|-----------|
| `IDLE` | prompt / continue_ / compact / 全部 setter（立即 persist） |
| `TURN` | steer / follow_up / abort / runtime setters（enqueue pending） |
| `COMPACTION` | 仅 compact 内部；外部 structural op → `busy` |

Structural op（prompt / continue_ / compact）在非 IDLE 时抛 `AgentHarnessError("busy")`。

### 1.2 消息与 pending 顺序（关键）

```
message_end:
  1. append message → state.messages
  2. persist MessageEntry（立即）
  3. notify listeners

turn_end:
  1. append tool_results → state.messages
  2. flush pending writes（FIFO；失败不丢队头）
  3. notify TurnEnd listeners
  4. loop 随后 _save_point:
       a. flush pending（可能为空）
       b. prepare_next_turn → 新 TurnSnapshot 应用到 context/config
       c. emit SavePoint

agent_end:
  1. flush leftover pending
  2. phase = IDLE          ← 在 emit 之前
  3. notify AgentEnd
  4. emit Settled(next_turn_count=…)
  5. 可选：auto-compact（走 agent.compact()，见 Task 4）

failure cleanup (executeTurn/finally 等价):
  flush pending（即使前面抛错）
```

**硬约束：** Agent 产出的消息在 `message_end` 立即持久化；listener/setter 产生的 pending 永远排在这些消息之后。禁止把 agent 消息丢进 pending 队列与 config change 混排。

### 1.3 Setter 契约

| API | idle | busy | 事件 | 持久化 |
|-----|------|------|------|--------|
| `set_model` | persist `ModelChangeEntry` → commit → emit | enqueue → commit → emit | `ModelUpdate` | 是 |
| `set_thinking_level` | 同上 `ThinkingLevelChangeEntry` | 同上 | `ThinkingLevelUpdate` | 是 |
| `set_tools` / `set_active_tools` | persist `ActiveToolsChangeEntry` → commit → emit | enqueue → commit → emit | `ToolsUpdate` | 只持久化 active names，不持久化 tool 实现 |
| `set_stream_options`（P1） | commit only | commit only | 无（对齐 TS） | 否 |
| `set_resources`（P1，可选） | commit + emit | commit + emit | `ResourcesUpdate` | 否 |
| queue mode setters | live，立即生效于下次 drain | 同左 | 无 | 否 |

Getter 始终返回 **最新 harness config**，不是 in-flight snapshot。

### 1.4 Abort / Settled 顺序

```
abort_and_wait:
  1. 快照并清空 steer + follow_up（不清 next_turn，若尚未实现则文档注明）
  2. 触发 abort signal
  3. await wait_for_idle（内部会走 agent_end → Settled）
  4. 再 emit AbortEvent(cleared_steer=[], cleared_follow_up=[])  # 消息列表，非 bool
  5. pending writes 不丢弃

同步 abort() 保留：仅 set signal + cancel HITL，不 emit AbortEvent（兼容）
```

验证断言顺序：`… → Settled → AbortEvent`（在 abort_and_wait 路径上）。

### 1.5 失败事件

- loop **正常返回** error/aborted assistant → 已由 loop 发 turn_end/agent_end，不走 `_emit_run_failure`
- loop **抛异常** → `_emit_run_failure`：`MessageStart → MessageEnd → TurnEnd → AgentEnd`，且每步走 **与正常路径相同的 sink**（有 harness 则 `harness._handle_event`）
- 公开 API 异常统一 `AgentHarnessError`；子系统错误保留 `cause`

### 1.6 Reentrancy（最低保证）

- listener / hook 内调用 structural op（prompt/compact）在 TURN 时必须得 `busy`
- listener 内可调用 setter / steer / follow_up（按上表）
- **禁止**在 active run 的 listener 里 `await wait_for_idle()` / `await abort_and_wait()` 作为推荐用法（会死锁）；本版不实现 `runWhenIdle`，但 P1 测试需证明当前会死锁或文档标明禁止

---

## 2. 文件职责

| 文件 | 本版职责 |
|------|----------|
| `agent_core/session/session.py` | Harness 权威：pending flush 真写、setter idle/busy、`_handle_event` 时序、Settled、abort_and_wait、auto-compact 委托 |
| `agent_core/core/agent.py` | loop 运行、snapshot、failure sink 路由、standalone 退化路径；减少与 harness 重复的「真逻辑」 |
| `agent_core/core/loop.py` | `_save_point` 顺序不变；P1 接入 provider hooks / stream options 刷新 |
| `agent_core/core/hooks.py` | 补 `session_before_compact` reducer；P1 provider hook 事件 |
| `agent_core/core/context.py` | 扩展 `TurnSnapshot`（active_tools / stream_options） |
| `agent_core/core/events.py` | AbortEvent 字段改为消息列表；必要时微调 Settled |
| `agent_core/core/errors.py` | 保持；接线 normalize |
| `agent_core/core/pending_writes.py` | 保持类型；flush 消费方在 session |
| `agent_core/session/store.py` | 新增 `ActiveToolsChangeEntry`；jsonl/inmemory 反序列化 |
| `tests/core/test_harness_lifecycle.py` | **新建** — 时序与语义主测 |
| `tests/session/test_pending_writes.py` | **新建** — flush / idle-busy setter |

---

## 3. 执行任务

### Task 0: 契约测试骨架（先红）

**Files:**
- Create: `tests/core/test_harness_lifecycle.py`
- Create: `tests/session/test_pending_writes.py`

- [x] **Step 0.1** 新建两个测试文件，放入本节列出的失败用例（先 `pytest.mark.xfail` 或直接红），覆盖：
  - busy 时 `set_model` → pending 非空 → save point 后 store 有 `ModelChangeEntry`
  - idle 时 `set_model` → 无 pending、store 立即有 entry
  - `set_active_tools` 后下一 turn 的 tools 列表被过滤
  - failure 路径下 `MessageEntry` 经 store 可加载
  - compact hook `{"cancel": True}` 取消压缩
  - `abort_and_wait` 事件顺序含 Settled 后 AbortEvent

- [x] **Step 0.2** 跑测试确认当前失败（证明空洞存在）

```bash
pytest tests/core/test_harness_lifecycle.py tests/session/test_pending_writes.py -v
```

**验证:** 测试文件可收集；至少一个断言因 H1/H3/H6 失败。

---

### Task 1: Pending flush 真持久化（修 H1）

**Files:**
- Modify: `agent_core/session/session.py` (`_flush_pending_writes`)
- Modify: `agent_core/session/store.py` — 新增 `ActiveToolsChangeEntry`
- Modify: `agent_core/session/jsonl_store.py` / `inmemory_store.py` — 反序列化分支
- Test: `tests/session/test_pending_writes.py`

**实现要点:**

```python
async def _flush_pending_writes(self) -> None:
    while self._pending_writes:
        write = self._pending_writes[0]  # peek
        entry = self._pending_write_to_entry(write)
        await self._store.append_entry(self._session_id, entry)
        self._pending_writes.pop(0)  # 仅成功后 pop
```

- flush 中途失败：队头及后续保留，异常向上抛（或由调用方按 `"session"` 归一化）
- TurnEnd / AgentEnd / `_save_point` 已有调用点，**不要再加第三套调用**，只修实现
- Agent 侧 `_flush_pending_writes` 继续委托 harness

- [x] **Step 1.1** 写 `ActiveToolsChangeEntry` + store 反序列化
- [x] **Step 1.2** 实现 `_pending_write_to_entry` + 真 flush
- [x] **Step 1.3** 去掉 xfail；跑 `test_pending_writes`

**验证:**
```bash
pytest tests/session/test_pending_writes.py -v
```

---

### Task 2: Setter idle/busy 分岔（修 H2）

**Files:**
- Modify: `agent_core/session/session.py` — `set_model` / `set_thinking_level` / `set_tools` / `set_active_tools`
- Modify: `agent_core/core/agent.py` — standalone 路径对齐（无 store 时跳过 persist）

**实现要点:**

```python
async def set_model(self, model):
    # 1. validate
    previous = self._agent.state.model
    write = PendingSessionWrite(type="model_change", data={...})
    if self.phase == AgentHarnessPhase.IDLE:
        await self._store.append_entry(...)  # 立即
    else:
        self._pending_writes.append(write)
    self._agent.state.model = model  # commit after persist/enqueue
    await self._notify_listeners(ModelUpdate(...))
```

- persist 失败 → 不 commit 内存，抛 `AgentHarnessError("session", ..., cause=)`
- notify 失败 → 不回滚已 commit（对齐 TS）

- [x] **Step 2.1** 四个 setter 改为 idle/busy 分岔
- [x] **Step 2.2** 测试：idle 立即落盘；busy enqueue；persist 失败不改 model

**验证:** `tests/session/test_pending_writes.py` 中 idle/busy 用例全绿。

---

### Task 3: Active tools 进入 snapshot（修 H3）

**Files:**
- Modify: `agent_core/core/context.py` — `TurnSnapshot` 增加 `active_tool_names: list[str] | None`
- Modify: `agent_core/core/agent.py` — 维护 `_active_tool_names`；`create_turn_snapshot` 过滤 tools
- Modify: `agent_core/session/session.py` — `set_active_tools` / `set_tools` 更新 `_active_tool_names`
- Modify: `agent_core/core/loop.py` — `_save_point` / 应用 snapshot 时用 snapshot.tools（已是，确认）

**实现要点:**

- `set_tools(tools, active_tool_names=None)`：默认全部 active；校验重名与未知名
- `set_active_tools(names)`：只改 active 集合，不改 tool 注册表
- `create_turn_snapshot()`：`tools = [t for t in all_tools if t.name in active]`
- **当前 turn 进行中**改 active → 不影响 in-flight request；下一 save point 后生效

- [x] **Step 3.1** 状态字段 + snapshot 过滤
- [x] **Step 3.2** 集成测试：busy 中 set_active_tools → 第二 turn 工具列表变化

**验证:** lifecycle 测试中 active tools 用例绿。

---

### Task 4: Compact 语义打通（修 H4/H5）

**Files:**
- Modify: `agent_core/core/hooks.py` — 注册 `session_before_compact` reducer（支持 `cancel` / 可选自定义结果）
- Modify: `agent_core/session/session.py` — `_maybe_compact` 改为 `await self._agent.compact(...)` 或共享内部实现且设 COMPACTION phase
- Modify: `agent_core/core/agent.py` — cancel 时抛或返回与 TS 对齐：计划采用 **返回 `None` 表示 cancel**（手动 API）；auto 路径 cancel 则跳过

**Reducer 语义:**

```python
# 链式：任一 handler 返回 {"cancel": True} → 最终 cancel
# 可选：{"compaction": {...}} 跳过 LLM（若当前 compact_callback 支持则接入，否则本版只做 cancel）
```

- [x] **Step 4.1** 实现 reducer，单测 hook cancel
- [x] **Step 4.2** `_maybe_compact` 走 phase API
- [x] **Step 4.3** 确认 overflow compact 路径同样设 phase（或明确文档：overflow 仍走 callback，另开任务）

**验证:**
```bash
pytest tests/core/test_hooks.py tests/core/test_harness_lifecycle.py -k compact -v
```

---

### Task 5: 失败事件走 harness sink + 错误归一化（修 H6/H7）

**Files:**
- Modify: `agent_core/core/agent.py` — `_emit_run_failure` 与正常 emit 相同路由
- Modify: `agent_core/session/session.py` — 公开方法残留 `RuntimeError` → `AgentHarnessError`
- Modify: 调用点接入 `normalize_harness_error` / `normalize_hook_error`（prompt catch、hook notify）

**实现要点:**

```python
async def _emit_run_failure(...):
    async def _sink(evt):
        if self._harness is not None:
            await self._harness._handle_event(evt, context)
        else:
            await self._handle_event(evt, context)
    await _sink(MessageStart(...))
    ...
```

- listener/hook 失败：状态已 commit 的不回滚；向外抛 `code="hook"`（至少在 setter notify 路径）
- 本版不强制所有内部 `logger.warning` 改抛——优先公开 API 与 setter/persist 路径

- [x] **Step 5.1** failure sink 路由
- [x] **Step 5.2** normalize 接线（prompt / compact / setter persist）
- [x] **Step 5.3** 测试：有 harness 时 failure 后 store 含 error assistant；`AgentHarnessError.code` 断言

**验证:** lifecycle failure 用例绿；`pytest tests/core/test_agent.py -v` 无回归。

---

### Task 6: QueueUpdate await + Abort/Settled 字段对齐（修 H8/H9 部分）

**Files:**
- Modify: `agent_core/core/events.py` — `AbortEvent.cleared_steer` / `cleared_follow_up` 改为 `list`（消息）；保留 count 字段则双写需文档说明，**推荐直接改为 list**
- Modify: `agent_core/session/session.py` / `agent.py` — `_emit_queue_update` 改为 await；`abort_and_wait` 顺序按 §1.4
- Modify: `AgentEnd` 处理：flush → phase IDLE → notify AgentEnd → Settled

**注意:** 当前 `AgentEnd` 分支里 `Settled` 在 `_notify_listeners(evt)` **之前**就发了一次，且 phase 可能由 `_finish_run` 另行设置——实现时对照 §1.2 **理顺单点**，避免双重 Settled。

- [x] **Step 6.1** 理顺 agent_end → idle → Settled 单路径
- [x] **Step 6.2** QueueUpdate await
- [x] **Step 6.3** AbortEvent 载荷 + 顺序测试

**验证:** abort 顺序测试；全量 `pytest tests/core/ tests/session/ -v`

**关于 nextTurn:** 本版 **不实现** nextTurn 队列。`Settled.next_turn_count` 固定为 `0`，在事件 docstring 标注「reserved」。避免半吊子 API。

---

### Task 7: TurnSnapshot 扩展 + stream options（P1）

**Files:**
- Modify: `agent_core/core/context.py` — `TurnSnapshot.stream_options: dict | None`
- Modify: `agent_core/core/agent.py` / `session.py` — `get/set_stream_options`
- Modify: `agent_core/core/loop.py` / provider 调用点 — 从当前 snapshot 读 options（浅拷贝）
- Test: `tests/core/test_harness_stream.py`（新建）

**契约:**
- setter 立即改 harness config；不写 pending；无事件（对齐 TS）
- save point 后下一 provider 请求使用新 options
- credentials / abort signal **不**被 stream_options 覆盖

- [x] **Step 7.1** API + snapshot 字段
- [x] **Step 7.2** 测试 busy 中改 options → 第二 turn 生效、第一 turn 不变

**验证:** `pytest tests/core/test_harness_stream.py -v`

---

### Task 8: Provider Hook 管道（P1）

**Files:**
- Modify: `agent_core/core/hooks.py` — `BeforeProviderRequestHookEvent` / `BeforeProviderPayloadHookEvent` / `AfterProviderResponseHookEvent` + reducers
- Modify: `agent_core/core/loop.py` 或 harness 包装的 `stream_fn` — 请求前 patch options、payload transform、响应后 observe
- Modify: `agent_core/core/agent.py` — 把 hooks 链进 stream 包装

**Reducer:**
- `before_provider_request`: 链式 patch；支持显式删除字段（`None` 或 sentinel，二选一，测试钉死）
- `before_provider_payload`: 链式 transform
- `after_provider_response`: fire-and-forget 观察

- [x] **Step 8.1** 事件类型 + reducer
- [x] **Step 8.2** stream 包装接入
- [x] **Step 8.3** 与 Task 7 共用 `test_harness_stream.py`

**验证:** hook patch / 删除 / 链式 用例绿。

---

### Task 9: 职责收敛（P2，可独立 PR）

**目标:** 消除双份「真逻辑」，不是删除 Agent。

**Files:**
- Modify: `agent_core/core/agent.py` — 有 `_harness` 时，queues/pending/setters/`_handle_event` **只委托**，删除重复实现分支中的第二套状态机（保留方法作 facade）
- Modify: `agent_core/session/session.py` — 成为唯一写入 pending / Settled / persist 的地方
- Modify: Scene 层可选：`AgentSession` → 文档推荐 `AgentHarness` 名（别名已存在则只改文档/import）

**不做:** 让 Harness 直接调用 `run_agent_loop` 绕过 Agent（那是更大重构，单独立项）。

- [x] **Step 9.1** 列出 agent.py 中与 session.py 重复的方法表，逐个改为纯委托
- [x] **Step 9.2** 全量回归
- [x] **Step 9.3** 更新 `docs/development-log/YYYY-MM-DD.md` + 必要时改 `docs/agent-framework-design.md` 现状段

**验证:**
```bash
pytest tests/ -q
```

---

### Task 10: 文档与过时计划清理

**Files:**
- Modify: `docs/development-log/2026-07-17.md`（或当日）— 记录本修订与完成项
- Modify: `docs/agent-framework-optimization-plan-phase2.md` 文首 — 标注 Phase1/Harness 状态已过时，指向本 spec
- Modify: `docs/FEATURES.md` / `CHANGELOG.md` — 仅在对应 Task 完成后追加

- [x] **Step 10.1** 文首加「状态以 task-31c 修订版与代码为准」
- [x] **Step 10.2** 开发日志记录 P0/P1/P2 完成摘要

---

## 4. 依赖与推荐 PR 切分

```
Task 0 (红测骨架)
  ↓
Task 1 (flush) ──→ Task 2 (setter 分岔) ──→ Task 3 (active tools)
  ↓                      ↓
Task 4 (compact)    Task 5 (failure + normalize)
  ↓                      ↓
        Task 6 (Settled/Abort/QueueUpdate)
                 ↓
        ── P0 完成里程碑：合 PR-A ──
                 ↓
        Task 7 (stream options) ──→ Task 8 (provider hooks)
                 ↓
        ── P1 完成里程碑：合 PR-B ──
                 ↓
        Task 9 (职责收敛) → Task 10 (文档)
                 ↓
        ── P2 完成里程碑：合 PR-C ──
```

| PR | 包含 | 合并门槛 |
|----|------|----------|
| PR-A | Task 0–6 | `tests/core/test_harness_lifecycle.py` + `tests/session/test_pending_writes.py` 全绿；现有 core/session 无回归 |
| PR-B | Task 7–8 | stream/hook 新测全绿 |
| PR-C | Task 9–10 | 全量 `pytest`；文档更新 |

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| flush 与 TurnEnd/save_point 双重调用导致重复 persist | peek-pop 成功语义；第二次 flush 队列为空；测试断言 entry 不双写 |
| Settled 双发 | Task 6 单点理顺；测试 `count(Settled)==1` |
| AbortEvent 字段改 list 破坏调用方 | grep `AbortEvent` / `cleared_steer`；scene 层同步 |
| setter persist 失败与内存不一致 | persist→commit 顺序；失败单测 |
| listener 内 wait_for_idle 死锁 | P1 文档禁止 + 可选超时测试 |
| 扩大 scope 到树/durable | §0.3 拒绝 |

---

## 6. 完成定义（DoD）

P0（PR-A）完成当且仅当：

1. Pending writes 在 save point / agent_end 后可从 store 读回
2. idle/busy setter 行为符合 §1.3
3. `set_active_tools` 影响下一 turn 的工具列表
4. compact cancel 生效；auto-compact 走 COMPACTION phase
5. loop 抛错时错误消息经 harness 持久化
6. `abort_and_wait` 顺序为 Settled → AbortEvent
7. 无新的「只写不读」字段；`normalize_*` 至少在公开失败路径被调用

P1（PR-B）：stream options 经 save point 生效 + provider hooks 可 patch/删除字段。

P2（PR-C）：有 harness 时 Agent 内无第二套 pending/settled 真逻辑；文档与代码一致。

---

## 7. 快速命令

```bash
# P0 主测
pytest tests/core/test_harness_lifecycle.py tests/session/test_pending_writes.py -v

# 回归
pytest tests/core/ tests/session/ -v

# 全量
pytest -q
```

---

## 附录 A: 与原 Step 1–7 映射

| 原 Step | 本版处置 |
|---------|----------|
| 1 AgentHarnessError | 类型已有 → Task 5 接线 normalize |
| 2 事件类型 | 类已有 → Task 6 修字段/顺序 |
| 3 Setter + Pending | API 已有 → Task 1–3 修语义 |
| 4 Queue/Settled/Abort | API 已有 → Task 6 |
| 5 emitRunFailure | 流已有 → Task 5 修 sink |
| 6 Compact 一等公民 | API 已有 → Task 4 |
| 7 Provider Hooks | 未做 → Task 8（升为 P1，与 stream 同批） |
