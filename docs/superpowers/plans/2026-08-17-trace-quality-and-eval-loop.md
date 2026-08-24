# Trace 可信与产品评测闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 skill 激活进入 harness 事件总线，collector 写出带 `run_id` 的干净 trace；再让聊天 👍/👎 按 `run_id` 合并到主 trace，并可选打到 Langfuse Score。

**Architecture:** `AgentHarness.emit_event` 复用 `_handle_event`；`SkillRuntime` 只经此发出 `SkillStart`/`SkillEnd`。Collector 以 SkillStart + `skill_activations` 归因为主。Feedback 在 jsonl 上 append overlay、读取时合并。Langfuse Score 仅 scene 用 httpx，不引入 SDK。

**Tech Stack:** 现有 pytest-asyncio、AgentEvent、JsonlSkillEvolutionStore、FastAPI、共享 MessageBubble、Langfuse Public API（httpx）

**Spec:** `docs/superpowers/specs/2026-08-17-trace-quality-and-eval-loop-design.md`

**闸门：** Task 1–4（阶段 1）全部验收通过后，才开始 Task 5–8（阶段 2）。禁止在脏 jsonl 上开 scheduler / auto-apply。

---

## 文件结构

### 修改

| 文件 | 职责 |
|------|------|
| `agent_core/session/harness.py` | 公开 `emit_event` |
| `scene/skill_runtime.py` | SkillStart/End 只走 `emit_event` |
| `agent_core/skill_evolution/types.py` | `SkillEvolutionTrace.run_id` |
| `agent_core/skill_evolution/collector.py` | 记录 run_id；TurnEnd 读 `skill_activations`；feedback overlay |
| `agent_core/skill_evolution/store.py` | serialize `run_id`；`get_traces` 合并 feedback |
| `scene/http_sse/events.py` | `AgentStart` / `message.end` 带 `run_id` |
| `scene/h5/events.py` | 同上（若尚未有 run_id） |
| `scene/http_sse/server.py` / `scene/h5/server.py` | feedback 请求体支持 `run_id`；可选 Score POST |
| `scene/http_sse/static/src/stores/chat-store.ts` | `ChatMessage.runId` |
| `scene/http_sse/static/src/hooks/useSSE.ts` | 把 SSE `run_id` 写入当前助手消息 |
| `scene/h5/static/src/hooks/useSSE.ts` | 同上 |
| `scene/http_sse/static/src/components/shared/Icon.tsx` | 增加 `thumbs-up` / `thumbs-down` |
| `scene/http_sse/static/src/components/chat/MessageBubble.tsx` | 👍/👎 |
| `scene/http_sse/static/src/api/client.ts` | `submitRunFeedback` |
| `docs/FEATURES.md` / `docs/observability-and-quality-plan.md` / gap roadmap | 完成后勾选状态 |

### 新建

| 文件 | 职责 |
|------|------|
| `tests/session/test_harness_emit_event.py` | emit_event 到达 extension + subscriber |
| `tests/scene/test_skill_runtime_emit.py` | load_skill 激活走 harness 而非 Runtime 直发 |
| `scene/http_sse/langfuse_score.py` | 可选 Score HTTP，无 SDK |
| `tests/scene/test_langfuse_score.py` | httpx mock |
| `scripts/quarantine_legacy_evolution_traces.py` | 隔离脏 jsonl |

### 明确不改

- `demo/`
- 不新增 `langfuse` / `agentevals` 依赖
- 不改 `ENABLE_EVOLUTION_SCHEDULER` 默认值
- 不实现 Dataset / 回放（B4）

---

## Task 1: `AgentHarness.emit_event`

**Files:**
- Modify: `agent_core/session/harness.py`
- Test: `tests/session/test_harness_emit_event.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from agent_core.core.events import SkillStart
from agent_core.core.state import AgentState
from agent_core.extensions.base import Extension
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore


class _Cap(Extension):
    name = "cap"

    def __init__(self):
        self.types = []

    async def on_event(self, ctx, evt):
        self.types.append(getattr(evt, "type", None))


@pytest.mark.asyncio
async def test_emit_event_reaches_extension_and_subscriber():
    cap = _Cap()
    harness = AgentHarness(
        provider=object(),
        auth_source=object(),
        store=InMemoryStore(),
        session_id="s1",
        initial_state=AgentState(system_prompt="", model=None, tools=[]),
        extensions=[cap],
    )
    await harness.start()
    seen = []
    harness.subscribe(lambda e: seen.append(e.type))
    await harness.emit_event(SkillStart(skill_name="demo", skill_description="d"))
    assert "skill_start" in cap.types
    assert "skill_start" in seen
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/session/test_harness_emit_event.py::test_emit_event_reaches_extension_and_subscriber -v
```

Expected: `AttributeError: emit_event`

- [ ] **Step 3: 最小实现**

在 `AgentHarness`（`harness.py`，lifecycle 方法附近）增加：

```python
async def emit_event(self, evt: AgentEvent) -> None:
    """Inject an event onto the same bus as the agent loop (extensions + subscribers)."""
    await self._handle_event(evt)
```

确认文件顶部已 import `AgentEvent`；若只在 TYPE_CHECKING 中引用，改为运行时 import。

- [ ] **Step 4: 测试通过**

```bash
pytest tests/session/test_harness_emit_event.py -v
```

Expected: PASS

---

## Task 2: SkillRuntime 只经 harness 发 SkillStart/End

**Files:**
- Modify: `scene/skill_runtime.py`
- Modify: `tests/scene/test_skill_runtime_path_read.py`
- Test: `tests/scene/test_skill_runtime_emit.py`

- [ ] **Step 1: 改 path_read 测试为订阅 harness（当前实现会红）**

`tests/scene/test_skill_runtime_path_read.py` 的 fixture 改为：

```python
@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("AGENT_SKILL_PATH_READ_ACTIVATION", "1")
    harness = AgentHarness(
        provider=object(),
        auth_source=object(),
        store=InMemoryStore(),
        session_id="s1",
        initial_state=AgentState(system_prompt="", model=None, tools=[]),
    )
    emitted: list[str] = []

    async def handler(evt):
        name = getattr(evt, "skill_name", None)
        if name:
            emitted.append(name)

    harness.subscribe(handler)
    rt = SkillRuntime([_skill()], harness, cwd="/tmp")
    return rt, emitted
```

新增 `tests/scene/test_skill_runtime_emit.py`：

```python
@pytest.mark.asyncio
async def test_emit_skill_start_does_not_call_bind_handlers_directly():
    harness = AgentHarness(
        provider=object(),
        auth_source=object(),
        store=InMemoryStore(),
        session_id="s1",
        initial_state=AgentState(system_prompt="", model=None, tools=[]),
    )
    direct = []
    bus = []
    rt = SkillRuntime([_skill()], harness, cwd="/tmp")
    rt.bind_handlers([lambda e: direct.append(e)])
    harness.subscribe(lambda e: bus.append(getattr(e, "type", None)))
    await rt._emit_skill_start(_skill(), source="load_skill")
    assert direct == []
    assert "skill_start" in bus
    assert harness.skill_activations == [("demo-skill", "load_skill")]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/scene/test_skill_runtime_path_read.py tests/scene/test_skill_runtime_emit.py -v
```

Expected: path_read 的 `emitted == []` 或 emit 测试 `direct` 非空

- [ ] **Step 3: 改 `scene/skill_runtime.py`**

`_emit_skill_start`：

```python
async def _emit_skill_start(self, skill: Skill, *, source: str) -> None:
    self._active_skills.add(skill.name)
    self.harness.record_skill_activation(skill.name, source)
    await self.harness.emit_event(
        SkillStart(skill_name=skill.name, skill_description=skill.description)
    )
```

`handle_turn_end`：对每个 active skill `await self.harness.emit_event(SkillEnd(skill_name=...))`，然后 `self._active_skills.clear()`。**不要**再遍历传入的 `handlers` 发事件（可保留参数以免调用方改签名，但忽略直发）。

ChatAssistant 的 `bind_handlers` 仍用于其它用途则可留；SkillStart 不再用它。

- [ ] **Step 4: 测试通过**

```bash
pytest tests/scene/test_skill_runtime_path_read.py tests/scene/test_skill_runtime_emit.py tests/tools/test_load_skill.py -v
```

Expected: PASS

---

## Task 3: Collector 写入 `run_id` + `skill_activations` 兜底

**Files:**
- Modify: `agent_core/skill_evolution/types.py`
- Modify: `agent_core/skill_evolution/store.py`（`_trace_to_dict` / `_trace_from_dict`）
- Modify: `agent_core/skill_evolution/collector.py`
- Test: `tests/skill_evolution/test_collector_attribution.py`

- [ ] **Step 1: 写失败测试**

在 `test_collector_attribution.py` 追加：

```python
async def test_agent_start_run_id_written_on_trace():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    collector.register_skills([_skill("demo")])

    class FakeState:
        system_prompt = (
            "<available_skills>\n"
            '  <skill name="demo">d</skill>\n'
            '  <skill name="other">d</skill>\n'
            "</available_skills>"
        )
        messages = [type("U", (), {"role": "user", "content": "hello"})()]
        skill_activations = [("demo", "load_skill")]

    class FakeHarness:
        state = FakeState()
        skill_activations = [("demo", "load_skill")]

    ctx = ExtensionContext(session_id="s1", harness=FakeHarness(), store=store)
    await collector.on_event(ctx, AgentStart(run_id="run-abc123def456"))
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))
    traces = await store.get_traces()
    assert len(traces) == 1
    assert traces[0].skill_name == "demo"
    assert traces[0].run_id == "run-abc123def456"
    assert traces[0].user_query == "hello"


async def test_no_activation_and_multiple_skills_writes_nothing():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    collector.register_skills([_skill("a"), _skill("b")])

    class FakeState:
        system_prompt = (
            "<available_skills>\n"
            '  <skill name="a">d</skill>\n'
            '  <skill name="b">d</skill>\n'
            "</available_skills>"
        )
        messages = []

    class FakeHarness:
        state = FakeState()
        skill_activations = []

    ctx = ExtensionContext(session_id="s1", harness=FakeHarness(), store=store)
    await collector.on_event(ctx, AgentStart(run_id="run-x"))
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))
    assert await store.get_traces() == []
```

`types.py` 的 `SkillEvolutionTrace` 增加 `run_id: str = ""` 之后，旧测试若构造 dataclass 无需改位置参数。

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/skill_evolution/test_collector_attribution.py::test_agent_start_run_id_written_on_trace -v
```

Expected: `AttributeError: run_id` 或 `len(traces)==0`

- [ ] **Step 3: 实现**

`SkillEvolutionTrace` 增加字段 `run_id: str = ""`。store 读写该键。

Collector：

- `__init__` 增加 `self._active_run_id = ""`
- `AgentStart` 分支：`self._active_run_id = evt.run_id or ""`（保留现有清 buffer）
- `_resolve_skill_names_for_turn` 在 `_turn_active_skills` 为空时：

```python
activations = getattr(ctx.harness, "skill_activations", None) or []
names = [n for n, _src in activations if n]
if names:
    for name in names:
        self._activate_skill(name)
    return sorted(set(names))
```

然后才走 injected / single available。

- `_handle_turn_end` 构造 trace 时传 `run_id=self._active_run_id`。

- [ ] **Step 4: 测试通过**

```bash
pytest tests/skill_evolution/test_collector_attribution.py tests/skill_evolution/test_collector_steps.py tests/skill_evolution/test_types.py -v
```

Expected: PASS

---

## Task 4: 隔离脏 jsonl + analyze 跳过 TextContent

**Files:**
- Create: `scripts/quarantine_legacy_evolution_traces.py`
- Modify: `agent_core/skill_evolution/agent.py`（读 trace 时跳过脏 query）
- Test: `tests/skill_evolution/test_agent.py` 或新建 `tests/skill_evolution/test_dirty_trace_skip.py`

- [ ] **Step 1: 写跳过逻辑的单测**

```python
def test_is_legacy_user_query():
    from agent_core.skill_evolution.agent import is_legacy_user_query
    assert is_legacy_user_query("[TextContent(type='text', text='hi')]")
    assert not is_legacy_user_query("帮我生成视频")
```

Analyze 循环里对 legacy query `continue`，并计入 `skipped_legacy`。

- [ ] **Step 2: 实现 `is_legacy_user_query` + analyze 跳过**

```python
def is_legacy_user_query(query: str) -> bool:
    q = query or ""
    return "[TextContent" in q or "ImageContent(" in q
```

脚本 `scripts/quarantine_legacy_evolution_traces.py`：

```python
"""Rename dirty evolution jsonl so new runs start clean. Never deletes."""
from pathlib import Path
import os
base = Path(os.path.expanduser("~/.agent-core"))
src = base / "skill-evolution-traces.jsonl"
dst = base / "skill-evolution-traces.jsonl.legacy-20260731"
if src.exists() and not dst.exists():
    src.rename(dst)
    print(f"moved {src} -> {dst}")
else:
    print("skip", "src_exists", src.exists(), "dst_exists", dst.exists())
```

不要在库 import 时自动 rename（避免测试误伤开发者文件）。在 `docs/skill-self-evolution.md` 加一句：阶段 1 验收前先跑该脚本。

- [ ] **Step 3: 跑测试**

```bash
pytest tests/skill_evolution/test_dirty_trace_skip.py tests/skill_evolution/test_agent.py -v
```

Expected: PASS

- [ ] **Step 4: 阶段 1 手工验收**

```bash
# 隔离脏文件（本地一次）
python scripts/quarantine_legacy_evolution_traces.py
PORT=8001 python -m scene.http_sse.server
# 对话：先让模型 load_skill，再做该 skill 的任务
# 断言新 jsonl 行：skill 单一、query 纯文本、含 run_id
```

阶段 1 未通过前 **停止**，不要开始 Task 5。

---

## Task 5: SSE 下发 `run_id` 到 ChatMessage

**Files:**
- Modify: `scene/http_sse/events.py`
- Modify: `scene/h5/events.py`（若 message.end 无 run_id）
- Modify: `scene/http_sse/static/src/api/types.ts`
- Modify: `scene/http_sse/static/src/stores/chat-store.ts`
- Modify: `scene/http_sse/static/src/hooks/useSSE.ts`
- Modify: `scene/h5/static/src/hooks/useSSE.ts`（若 H5 独立处理 message.end）
- Test: `tests/scene/test_http_sse.py` 或现有 events 测试

Harness 在一次 run 内把 `run_id` 放到何处给 MessageEnd？**不要改 loop 的 MessageEnd 模型**（避免 core 膨胀）。Scene 转换层用闭包记住最近一次 `AgentStart.run_id`：

- [ ] **Step 1: 给 `agent_event_to_sse_frames` 增加可选 `run_id` 参数，或小型 stateful converter**

推荐最小改动：在 `scene/http_sse/server.py` 的 SSE 订阅处已能看见事件流。若 converter 无状态，则：

1. 转换 `AgentStart` → `{"event": "agent_start", "run_id": evt.run_id}`  
2. `MessageEnd` 帧增加 `"run_id": <last>` —— last 由 server handler 捕获。

不要把 last_run_id 做成模块全局。用 handler 闭包：

```python
last_run_id = {"v": ""}

async def _handler(evt):
    if isinstance(evt, AgentStart):
        last_run_id["v"] = evt.run_id or ""
    payload = agent_event_to_sse_json(evt)
    if payload and payload.get("event") == "message_end":
        payload["run_id"] = last_run_id["v"]
```

http_sse 与 h5 的 SSE 组装处各改一处（禁止只改一端）。

- [ ] **Step 2: 前端**

`ChatMessage` 增加 `runId?: string`。`useSSE` 在 `agent_start` 记下 `currentRunId`，在 `message.end` 写入正在收尾的 assistant 消息。

H5 `useSSE` 同样处理（H5 规范：共享 store 时改一处即可；若 H5 自己的 hook 复制了 switch，必须同步改，禁止漏改）。

- [ ] **Step 3: 后端单测** — 构造 `AgentStart(run_id="run-1")` + `MessageEnd`，断言帧含 `run_id`。

```bash
pytest tests/scene/test_http_sse.py tests/scene/test_h5_events.py -v
```

（若无 h5 events 测试，加在 `tests/scene/test_http_sse.py` 同类文件。）

---

## Task 6: Feedback overlay 按 `run_id` 合并

**Files:**
- Modify: `agent_core/skill_evolution/collector.py` `record_user_feedback`
- Modify: `agent_core/skill_evolution/store.py` `get_traces`
- Modify: `scene/http_sse/server.py` / `scene/h5/server.py` `EvolutionFeedbackRequest`
- Test: `tests/skill_evolution/test_store.py`

- [ ] **Step 1: 失败测试**

```python
@pytest.mark.asyncio
async def test_get_traces_merges_feedback_overlay():
    store = InMemorySkillEvolutionStore()
    main = SkillEvolutionTrace(
        trace_id="t1", skill_name="demo", user_query="q", run_id="run-1"
    )
    await store.save_trace(main)
    overlay = SkillEvolutionTrace(
        trace_id="t1-feedback",
        skill_name="",
        run_id="run-1",
        user_feedback="thumbs down",
        human_signal={"vote": "dislike"},
        execution_details={"type": "feedback", "original_run_id": "run-1"},
    )
    await store.save_trace(overlay)
    traces = await store.get_traces(skill_name="demo")
    assert len(traces) == 1
    assert traces[0].human_signal["vote"] == "dislike"
```

- [ ] **Step 2: `get_traces` 实现合并**

对 InMemory 与 Jsonl **同一函数**（模块级 `_merge_feedback_overlays(traces)`）：

- `execution_details.type == "feedback"` 的行不单独返回  
- 按 `original_trace_id` 或 `original_run_id` / `run_id` 匹配主行，填 `user_feedback` 与 `human_signal`

`record_user_feedback` 增加 `run_id: str | None = None`；写 overlay 时带上 `original_run_id`。允许 `trace_id=""` 仅用 `run_id`。

`EvolutionFeedbackRequest`：

```python
class EvolutionFeedbackRequest(BaseModel):
    trace_id: str | None = Field(default=None, max_length=200)
    run_id: str | None = Field(default=None, max_length=64)
    feedback: str = Field(default="", max_length=4000)
    was_helpful: bool | None = None

    @model_validator(mode="after")
    def _need_id(self):
        if not self.trace_id and not self.run_id:
            raise ValueError("trace_id or run_id required")
        return self
```

http_sse 与 h5 **两份** server 同步改（禁止只改一端）。

- [ ] **Step 3:**

```bash
pytest tests/skill_evolution/test_store.py tests/skill_evolution/test_collector_attribution.py -v
```

Expected: PASS

---

## Task 7: MessageBubble 👍/👎

**Files:**
- Modify: `scene/http_sse/static/src/components/shared/Icon.tsx`（**先改 IconName**）
- Modify: `scene/http_sse/static/src/components/chat/MessageBubble.tsx` + `.css`
- Modify: `scene/http_sse/static/src/api/client.ts`
- Modify: `scene/http_sse/static/src/stores/chat-store.ts`（可选 `feedback` 本地状态防重复提交）

H5 与桌面共享 `components/`，**不要**在 `src/h5/` 再做一套。

- [ ] **Step 1: Icon**

从 `lucide-react` 增加 `ThumbsUp`, `ThumbsDown`。`IconName` 联合类型增加 `'thumbs-up' | 'thumbs-down'`，`ICON_MAP` 同步。未进联合类型的名字禁止使用。

- [ ] **Step 2: API**

```ts
export async function submitRunFeedback(body: {
  run_id: string;
  was_helpful: boolean;
  feedback?: string;
}): Promise<{ ok: boolean }> {
  const resp = await fetch('/skills/evolution/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error('feedback failed');
  return resp.json();
}
```

路径已在 `vite.config.ts` 的 `/skills` 代理下，**不要**新开 `/runs`。

- [ ] **Step 3: UI**

仅 `role==='assistant'` 且 `message.runId` 存在时渲染两个按钮。点击后本地记录 vote，避免连点。无 `runId` 的历史消息不显示按钮（不要用 session 里「最后一条 run」猜测，避免串票）。

CSS 放在 `MessageBubble.css`，不要写进 H5 全局。H5：不要让该按钮订阅 companion-store。

---

## Task 8: Scene Langfuse Score（无 SDK）+ 文档收尾

**Files:**
- Create: `scene/http_sse/langfuse_score.py`
- Modify: feedback 路由调用它（h5 可 import 同一模块，禁止复制）
- Test: `tests/scene/test_langfuse_score.py`
- Modify: `docs/FEATURES.md`、`docs/observability-and-quality-plan.md`、`docs/skill-evolution-gap-and-roadmap.md`、`docs/development-log/2026-08-17.md`

- [ ] **Step 1: 测试 — 无密钥不抛；有密钥则 POST**

```python
import pytest
from scene.http_sse.langfuse_score import submit_user_score

@pytest.mark.asyncio
async def test_submit_user_score_noop_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert await submit_user_score(run_id="run-1", session_id="s1", value=1) is False

@pytest.mark.asyncio
async def test_submit_user_score_posts(monkeypatch, respx_mock=None):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.invalid")
    # 用 httpx mock：断言 JSON 含 metadata.run_id / sessionId，value 为 1 或 0
```

Score JSON 锁定最小字段（实施时对照当时 Langfuse Public API，若字段名微调只改这一文件）：

```python
{
  "name": "user-feedback",
  "value": 1,  # like=1 dislike=0
  "dataType": "NUMERIC",
  "sessionId": session_id,
  "metadata": {"run_id": run_id},
  "comment": comment or "",
}
```

失败只打 log，**不**让 feedback HTTP 变 5xx。

- [ ] **Step 2: feedback 路由**

`record_user_feedback` 成功后 `await submit_user_score(...)`。h5/server 调用同一函数。

- [ ] **Step 3: 文档**

- FEATURES：Langfuse 阶段 2 最小打分 ✅；Dataset 仍 ❌  
- observability-and-quality-plan：B3 最小落地，B4 仍待定  
- gap roadmap 变更记录指向本 spec  
- development-log 记阶段 1/2 摘要  

- [ ] **Step 4: 全量相关测试**

```bash
pytest tests/session/test_harness_emit_event.py \
  tests/scene/test_skill_runtime_path_read.py \
  tests/scene/test_skill_runtime_emit.py \
  tests/skill_evolution/ \
  tests/scene/test_langfuse_score.py \
  tests/scene/test_http_sse.py -v
```

Expected: 全绿。再手工：隔离 jsonl → 对话 load_skill → 新 jsonl 干净 → 点 👍 → overlay 合并 →（可选）Langfuse 见 Score。

---

## 验收对照（Spec §4）

| Spec | Task |
|------|------|
| load_skill 恰好 1 条干净 trace | 2+3 |
| 未激活不写 trace | 3 |
| `/skill:` / path_read | 2（现有 path_read 测试 + emit） |
| 脏 jsonl 隔离 | 4 |
| 气泡 👍 带 run_id | 5+7 |
| 主 trace 合并 human_signal | 6 |
| Langfuse Score 可关 | 8 |
| 不引入 agentevals / SDK | 全文不改 pyproject 主依赖 |

---

## 后续（本计划结束后另开 spec，禁止塞进本次）

- B4：Score → Dataset → 改 prompt 回放  
- 自写 trajectory matcher（strict / subset）挂 Scene golden  
- 干净数据跑满 7 天后再考虑默认打开 evolution scheduler  
- `force=True` accept 的产品策略收紧（UI 去掉 force）
