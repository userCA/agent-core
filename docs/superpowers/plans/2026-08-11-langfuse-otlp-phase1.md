# Langfuse Scene 集成 Implementation Plan（阶段 1：OTLP 采数）

> **Implemented 2026-08-11** — Tasks 1–5 代码已合入；Task 6 文档已更新。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不把 Langfuse 绑进 `agent_core/core` 的前提下，让测试环境可通过 OTLP/HTTP 把已有 agent span 推到 Langfuse，并在 UI 中按 `run_id` / `session.id` 看到完整 run→turn→llm/tool 树。

**Architecture:** `agent_core/observability.py` 扩展 OTLP/HTTP exporter + `configure_langfuse_otel_from_env()`；`AgentHarness._execute_turn` 统一生成 `run_id` 并用 `observe()` 包住整次 run（补齐 G1，同时覆盖 `prompt`/`continue_` 与 http_sse/h5，避免双份 chat_assistant 接线）；scene lifespan 优先启用 Langfuse，否则回退现有 console/gRPC OTEL。阶段 1 **零** `langfuse` Python 包依赖。

**Tech Stack:** OpenTelemetry API/SDK、`opentelemetry-exporter-otlp-proto-http`、现有 `observe`/`trace_turn`/`trace_llm_call`、pytest

**Spec:** `docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md`  
**总策略:** `docs/observability-and-quality-plan.md`

**范围：** 仅阶段 1（OTLP 采数验证）。阶段 2（Score/Dataset/反馈）不在本计划任务内，见文末「后续」。

---

## 文件结构

### 修改

| 文件 | 职责 |
|------|------|
| `agent_core/observability.py` | OTLP/HTTP + headers；`configure_langfuse_otel_from_env`；span 补 `session.id` / metadata |
| `agent_core/session/turn_runtime.py` | `build_loop_config` 接受并写入 `run_id` |
| `agent_core/session/harness.py` | `_execute_turn`：生成 `run_id`、传 config、`observe()` 包裹 |
| `scene/http_sse/server.py` | lifespan：Langfuse 优先，否则 `configure_otel_exporter()` |
| `scene/h5/server.py` | 同上 |
| `pyproject.toml` | extras `[otel]` |
| `tests/core/test_observability.py` | HTTP/Langfuse 配置与属性单测 |
| `tests/session/test_harness_observe_run_id.py` | harness `run_id` 与 AgentStart 一致（新建） |
| `docs/observability-and-quality-plan.md` | 阶段 1 完成后更新状态 |
| `docs/FEATURES.md` | 勾选 Langfuse OTLP |
| `docs/development-log/YYYY-MM-DD.md` | 提交时摘要 |

### 明确不改

- `agent_core/core/loop.py`（已有 turn/llm span；不引入厂商语义）
- 不新增 `langfuse` 包依赖
- 不做 Score / 反馈 API / 前端 👍👎（阶段 2）
- 不做 `LANGFUSE_CAPTURE_CONTENT` 全文上报（阶段 1 MVP 仅元数据）

### 相对 Spec 的实现微调（已锁定）

Spec §5.4 写在 `chat_assistant` 外包 `observe()`。本计划改为在 **`AgentHarness._execute_turn`** 接线，原因：

1. `http_sse` 与 `h5` 共用，避免双份逻辑  
2. `continue_()` 同样进入 `_execute_turn`，不会漏 span  
3. `run_id` 在构建 `AgentLoopConfig` 前生成并下传，杜绝双 ID  
4. 仍属 session/observability 层，不违反「core 不绑 Langfuse」

---

## Task 1: Langfuse Basic Auth 与 `configure_langfuse_otel_from_env`（先测后实现）

**Files:**
- Modify: `agent_core/observability.py`
- Test: `tests/core/test_observability.py`

- [x] **Step 1: 写失败测试 — auth header 与开关行为**

在 `tests/core/test_observability.py` 追加：

```python
import base64
import os

from agent_core.observability import (
    build_langfuse_otlp_headers,
    configure_langfuse_otel_from_env,
)


def test_build_langfuse_otlp_headers():
    headers = build_langfuse_otlp_headers("pk-lf-test", "sk-lf-secret")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")
    raw = base64.b64decode(headers["Authorization"].split(" ", 1)[1]).decode()
    assert raw == "pk-lf-test:sk-lf-secret"
    assert headers["x-langfuse-ingestion-version"] == "4"


def test_configure_langfuse_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    assert configure_langfuse_otel_from_env() is False


def test_configure_langfuse_enabled_missing_keys_returns_false(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert configure_langfuse_otel_from_env() is False


def test_configure_langfuse_enabled_with_keys_calls_http_exporter(monkeypatch):
    """When keys present, should attempt otlp_http configure (may no-op if OTEL missing)."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-y")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")

    called: dict = {}

    def fake_configure(*, exporter=None, endpoint=None, headers=None, service_name="agent-core"):
        called["exporter"] = exporter
        called["endpoint"] = endpoint
        called["headers"] = headers
        return True

    monkeypatch.setattr(
        "agent_core.observability.configure_otel_exporter",
        fake_configure,
    )
    assert configure_langfuse_otel_from_env() is True
    assert called["exporter"] == "otlp_http"
    assert called["endpoint"] == "http://localhost:3000/api/public/otel"
    assert called["headers"]["x-langfuse-ingestion-version"] == "4"
```

- [x] **Step 2: 跑测试确认失败**

```bash
pytest tests/core/test_observability.py::test_build_langfuse_otlp_headers \
  tests/core/test_observability.py::test_configure_langfuse_disabled_by_default \
  tests/core/test_observability.py::test_configure_langfuse_enabled_missing_keys_returns_false \
  tests/core/test_observability.py::test_configure_langfuse_enabled_with_keys_calls_http_exporter -v
```

Expected: FAIL（`ImportError` / 函数未定义）

- [x] **Step 3: 实现最小 API（尚可不真正装 HTTP exporter）**

在 `agent_core/observability.py` 增加：

```python
def build_langfuse_otlp_headers(public_key: str, secret_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "x-langfuse-ingestion-version": "4",
    }


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def configure_langfuse_otel_from_env(*, service_name: str = "agent-core") -> bool:
    """If LANGFUSE_ENABLED and keys set, configure OTLP/HTTP to Langfuse. Else False."""
    if not _env_flag("LANGFUSE_ENABLED"):
        return False
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not pk or not sk:
        logger.warning(
            "LANGFUSE_ENABLED but LANGFUSE_PUBLIC_KEY/SECRET_KEY missing; skip"
        )
        return False
    base = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    endpoint = f"{base}/api/public/otel"
    headers = build_langfuse_otlp_headers(pk, sk)
    ok = configure_otel_exporter(
        exporter="otlp_http",
        endpoint=endpoint,
        headers=headers,
        service_name=service_name,
    )
    if ok:
        logger.info("Langfuse OTEL exporter configured: %s", endpoint)
    return ok
```

并扩展 `configure_otel_exporter` 签名，暂时对未知 `otlp_http` 返回 False + warning（下一 Task 补全）。需要 `import base64`。

先把签名改成：

```python
def configure_otel_exporter(
    exporter: str | None = None,
    *,
    service_name: str = "agent-core",
    endpoint: str | None = None,
    headers: dict[str, str] | None = None,
) -> bool:
```

现有 `console` / `otlp`（gRPC）分支保持；新增：

```python
    elif exporter == "otlp_http":
        logger.warning("otlp_http not implemented yet")
        return False
```

（Task 2 替换为真实现。若希望本 Task 测试里 fake 已 patch `configure_otel_exporter`，则 `configure_langfuse_otel_from_env` 的成功路径不依赖真 HTTP。）

- [x] **Step 4: 再跑 Step 1 的测试**

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add agent_core/observability.py tests/core/test_observability.py
git commit -m "$(cat <<'EOF'
feat(observability): add Langfuse env config helpers for OTLP/HTTP

EOF
)"
```

---

## Task 2: 实现 `otlp_http` exporter

**Files:**
- Modify: `agent_core/observability.py`
- Test: `tests/core/test_observability.py`
- Modify: `pyproject.toml`（`[otel]` extras）

- [x] **Step 1: 写失败/行为测试 — otlp_http 分支可调用（可 mock SDK）**

```python
def test_configure_otel_exporter_otlp_http_sets_provider(monkeypatch):
    """Smoke: otlp_http path imports HTTP exporter or returns False cleanly."""
    from agent_core import observability as obs

    # If OTEL not installed, expect False without raise
    if not obs._otel_available:
        assert obs.configure_otel_exporter(
            exporter="otlp_http",
            endpoint="http://localhost:3000/api/public/otel",
            headers={"Authorization": "Basic xxx"},
        ) is False
        return

    # With OTEL: either configures True, or False if http exporter missing — never raise
    result = obs.configure_otel_exporter(
        exporter="otlp_http",
        endpoint="http://localhost:3000/api/public/otel",
        headers={"Authorization": "Basic xxx", "x-langfuse-ingestion-version": "4"},
    )
    assert result in (True, False)
```

- [x] **Step 2: 跑测试**

```bash
pytest tests/core/test_observability.py::test_configure_otel_exporter_otlp_http_sets_provider -v
```

- [x] **Step 3: 实现 `otlp_http` 分支**

在 `configure_otel_exporter` 的 `elif exporter == "otlp_http":` 中：

```python
        elif exporter == "otlp_http":
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)
            ep = endpoint or os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://localhost:4318",
            )
            # HTTP exporter expects base or traces endpoint; Langfuse uses .../api/public/otel
            exporter_kwargs: dict[str, Any] = {"endpoint": ep}
            if headers:
                exporter_kwargs["headers"] = headers
            otlp_exporter = OTLPSpanExporter(**exporter_kwargs)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            trace.set_tracer_provider(provider)
            logger.info("OTEL exporter configured: otlp_http -> %s", ep)
            return True
```

注意：

- 用 **HTTP** proto，不是 gRPC  
- `ImportError` 时 warning 并 `return False`（提示安装 `opentelemetry-exporter-otlp-proto-http`）  
- 保留原有 `otlp` gRPC 分支给 Jaeger  

- [x] **Step 4: `pyproject.toml` 增加 extras**

```toml
otel = [
    "opentelemetry-api>=1.27",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
    "opentelemetry-exporter-otlp-proto-grpc>=1.27",
]
```

并把 `otel` 并入 `all` 列表（可选但推荐）。

- [x] **Step 5: 跑 observability 相关测试**

```bash
pytest tests/core/test_observability.py -v
```

Expected: PASS

- [x] **Step 6: Commit**

```bash
git add agent_core/observability.py tests/core/test_observability.py pyproject.toml
git commit -m "$(cat <<'EOF'
feat(observability): support OTLP/HTTP exporter for Langfuse

EOF
)"
```

---

## Task 3: Span 属性补齐（G4）

**Files:**
- Modify: `agent_core/observability.py`（`observe` / `_make_tracing_before_hook` / `trace_turn` / `trace_llm_call`）
- Test: `tests/core/test_observability.py`

- [x] **Step 1: 写测试 — 公共属性 helper**

```python
from agent_core.observability import agent_span_attributes


def test_agent_span_attributes_include_session_aliases():
    attrs = agent_span_attributes(session_id="sess-1", run_id="run-abc")
    assert attrs["agent.session_id"] == "sess-1"
    assert attrs["agent.run_id"] == "run-abc"
    assert attrs["session.id"] == "sess-1"
    assert attrs["langfuse.session.id"] == "sess-1"
    assert attrs["langfuse.trace.metadata.run_id"] == "run-abc"
```

- [x] **Step 2: 跑测确认失败**

```bash
pytest tests/core/test_observability.py::test_agent_span_attributes_include_session_aliases -v
```

- [x] **Step 3: 实现 helper 并接到所有 span 创建点**

```python
def agent_span_attributes(*, session_id: str = "", run_id: str = "", **extra: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "agent.session_id": session_id,
        "agent.run_id": run_id,
        "session.id": session_id,
        "langfuse.session.id": session_id,
        "langfuse.trace.metadata.run_id": run_id,
    }
    attrs.update({k: v for k, v in extra.items() if v is not None and v != ""})
    return attrs
```

替换：

- `observe()` 的 `agent.run` attributes → `agent_span_attributes(..., provider=..., model=..., system_prompt_hash=...)`  
  保留原 key：`agent.provider` / `agent.model` / `agent.system_prompt_hash`  
- tool before-hook attributes  
- `trace_turn` / `trace_llm_call` 的 session/run 字段（llm 另加 `llm.*` / `agent.turn_index`）

空 `session_id`/`run_id` 时仍写入空字符串即可（与现状一致），或仅在非空时写入 `session.id` / langfuse 键——推荐：**非空才写 alias 键**，避免污染：

```python
def agent_span_attributes(*, session_id: str = "", run_id: str = "", **extra: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "agent.session_id": session_id,
        "agent.run_id": run_id,
    }
    if session_id:
        attrs["session.id"] = session_id
        attrs["langfuse.session.id"] = session_id
    if run_id:
        attrs["langfuse.trace.metadata.run_id"] = run_id
    attrs.update({k: v for k, v in extra.items() if v is not None and v != ""})
    return attrs
```

测试相应改为：有值时断言 alias。

- [x] **Step 4: 跑测试**

```bash
pytest tests/core/test_observability.py -v
```

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add agent_core/observability.py tests/core/test_observability.py
git commit -m "$(cat <<'EOF'
feat(observability): propagate session.id aliases for Langfuse filters

EOF
)"
```

---

## Task 4: Harness 统一 `run_id` + `observe()`（G1）

**Files:**
- Modify: `agent_core/session/turn_runtime.py`（`build_loop_config` 增加 `run_id: str = ""`）
- Modify: `agent_core/session/harness.py`（`_execute_turn`）
- Create: `tests/session/test_harness_observe_run_id.py`

- [x] **Step 1: 写测试 — AgentStart.run_id 非空、两次 prompt 不同、可被 harness 预生成固定**

创建 `tests/session/test_harness_observe_run_id.py`（模式对齐 `tests/session/test_session.py`）：

```python
import pytest

from agent_core.core.events import AgentStart
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model


def _scripted_harness(session_id: str = "observe-1") -> tuple[AgentHarness, FakeProvider]:
    provider = FakeProvider()
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id=session_id,
        initial_state=AgentState(model=fake_model()),
    )
    return harness, provider


def _queue_text_reply(provider: FakeProvider) -> None:
    provider.queue_script([
        StreamTextDelta(text="hi"),
        StreamMessageEnd(
            usage={"input_tokens": 1, "output_tokens": 1},
            stop_reason="stop",
            provider="fake",
            model="fake-1",
        ),
    ])


@pytest.mark.asyncio
async def test_harness_prompt_emits_agent_start_with_run_id():
    harness, provider = _scripted_harness()
    _queue_text_reply(provider)
    await harness.start()

    seen: list[str] = []
    harness.subscribe(
        lambda e: seen.append(e.run_id) if isinstance(e, AgentStart) else None
    )
    await harness.prompt("hello")

    assert len(seen) == 1
    assert seen[0].startswith("run-")
    assert len(seen[0]) == len("run-") + 12


@pytest.mark.asyncio
async def test_harness_prompt_run_ids_differ_across_turns():
    harness, provider = _scripted_harness("observe-2")
    _queue_text_reply(provider)
    _queue_text_reply(provider)
    await harness.start()

    seen: list[str] = []
    harness.subscribe(
        lambda e: seen.append(e.run_id) if isinstance(e, AgentStart) else None
    )
    await harness.prompt("one")
    await harness.prompt("two")
    assert seen == [seen[0], seen[1]]
    assert seen[0] != seen[1]


@pytest.mark.asyncio
async def test_harness_uses_pregenerated_run_id(monkeypatch):
    from agent_core import observability as obs
    from agent_core.session import harness as harness_mod

    fixed = "run-fixed012345"
    monkeypatch.setattr(obs, "generate_run_id", lambda: fixed)
    # harness imports generate_run_id inside _execute_turn — patch both modules if needed
    monkeypatch.setattr(harness_mod, "generate_run_id", lambda: fixed, raising=False)

    harness, provider = _scripted_harness("observe-3")
    _queue_text_reply(provider)
    await harness.start()

    seen: list[str] = []
    harness.subscribe(
        lambda e: seen.append(e.run_id) if isinstance(e, AgentStart) else None
    )
    await harness.prompt("hello")
    assert seen == [fixed]
```

说明：`test_harness_uses_pregenerated_run_id` 在 Task 4 Step 4 接线前，若 loop 仍自己 `generate_run_id`，可能失败或仍过——以「harness 调用 `observability.generate_run_id` 并写入 config」为通过标准。实现时优先 `from agent_core.observability import generate_run_id` 放在 harness 模块顶层或 `_execute_turn` 内，并保证 monkeypatch 命中同一符号。

- [x] **Step 2: 跑测**

```bash
pytest tests/session/test_harness_observe_run_id.py -v
```

Expected：前两个可能已因 loop 自生成而 PASS；第三个在 harness 预生成接线前可能 FAIL（`seen != [fixed]`），接线后 PASS。

- [x] **Step 3: 改 `build_loop_config`**

`agent_core/session/turn_runtime.py`：

1. 函数签名增加 `run_id: str = ""`  
2. `AgentLoopConfig(..., session_id=host.session_id, run_id=run_id)`

`harness.py` 调用处传入 `run_id=run_id`。

- [x] **Step 4: 改 `_execute_turn` 包裹 `observe`**

在 `agent_core/session/harness.py` 的 `_execute_turn` 中，于 `_do_run` 内、构建 config 之后、`run_agent_loop` 之前：

```python
from agent_core.observability import generate_run_id, observe

# 在 _do_run 开头（snapshot/context 之后、build_loop_config 之前）:
run_id = generate_run_id()
# build_loop_config(..., run_id=run_id)

model = snapshot.model  # 或 config.model
provider_name = getattr(model, "provider", "") if model else ""
model_id = getattr(model, "id", "") if model else ""

with observe(
    self,
    session_id=self._session_id,
    run_id=run_id,
    provider_name=provider_name,
    model_id=model_id,
    system_prompt=context.system_prompt or "",
):
    assistants = await run_agent_loop(...)
```

注意：`observe` 是同步 contextmanager；整段 `run_agent_loop` 必须在 `with` 内。异常路径同样应在 `with` 内，以便 run span 标记 ERROR。

若 `build_loop_config` 在 `with` 外调用，确保传入同一 `run_id`。

- [x] **Step 5: 跑相关测试**

```bash
pytest tests/session/test_harness_observe_run_id.py tests/core/test_observability.py tests/core/test_agent.py -v
```

Expected: PASS（修复因 hook 注册/移除导致的失败）

- [x] **Step 6: Commit**

```bash
git add agent_core/session/turn_runtime.py agent_core/session/harness.py tests/session/test_harness_observe_run_id.py
git commit -m "$(cat <<'EOF'
feat(session): wrap harness turns with observe() and stable run_id

EOF
)"
```

---

## Task 5: Scene lifespan 优先启用 Langfuse

**Files:**
- Modify: `scene/http_sse/server.py`（lifespan 中 OTEL 配置段）
- Modify: `scene/h5/server.py`（同上）

- [x] **Step 1: 替换 lifespan 配置逻辑**

将：

```python
from agent_core.observability import configure_otel_exporter
configure_otel_exporter()
```

改为：

```python
from agent_core.observability import (
    configure_langfuse_otel_from_env,
    configure_otel_exporter,
)

# Langfuse OTLP/HTTP first; else console/otlp-gRPC via OTEL_EXPORTER
if not configure_langfuse_otel_from_env():
    configure_otel_exporter()
```

两处 server 保持一致。

- [x] **Step 2: 语法/导入检查**

```bash
python -c "from scene.http_sse.server import app; from scene.h5 import server"
```

（若 h5 导入路径不同，用项目惯用方式：`python -m scene.http_sse.server` 的 import 烟测即可。）

- [x] **Step 3: Commit**

```bash
git add scene/http_sse/server.py scene/h5/server.py
git commit -m "$(cat <<'EOF'
feat(scene): prefer Langfuse OTLP exporter when enabled

EOF
)"
```

---

## Task 6: 文档与验收清单

**Files:**
- Modify: `docs/observability-and-quality-plan.md`
- Modify: `docs/FEATURES.md`
- Modify: `docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md`（状态 → 阶段 1 已落地）
- Create/Append: `docs/development-log/2026-08-11.md`（或当日日期）

- [ ] **Step 1: 更新 FEATURES 表**

在可观测性相关行追加：

| Langfuse OTLP（轨 B 阶段 1） | ✅ 完成 | `configure_langfuse_otel_from_env` + harness `observe()`；零 langfuse 包 |

- [ ] **Step 2: 更新 observability-and-quality-plan 状态**

改为：轨 B 阶段 1（OTLP）已实施；阶段 2 待定。链接本 plan。

- [ ] **Step 3: Spec 状态行**

`状态：阶段 1 已落地，阶段 2 待实施`

并在 §5.4 注记：实际接线在 `AgentHarness._execute_turn`（见本 plan 微调说明）。

- [ ] **Step 4: development-log 摘要**

记录文件列表、类型（feat）、关联规则（观测边界 / 不绑 core）。

- [ ] **Step 5: 手工验收（需密钥，不自动化）**

```bash
pip install -e ".[test,otel]"

export LANGFUSE_ENABLED=1
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_BASE_URL=https://cloud.langfuse.com   # 或自建

PORT=8001 python -m scene.http_sse.server
```

操作：

1. 浏览器发一条会触发工具的消息  
2. 日志中复制 `run_id=run-...`  
3. Langfuse Traces 按 session / metadata.run_id 查找  
4. 确认树：`agent.run` → `agent.turn` → `agent.llm_call` / `agent.tool_call.*`  
5. （可选）`ENABLE_RUN_REPLAY=1` 对照本地 JSON 同 `run_id`

勾选 Spec §5.7 验收清单。

- [ ] **Step 6: Commit docs**

```bash
git add docs/FEATURES.md docs/observability-and-quality-plan.md \
  docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md \
  docs/development-log/
git commit -m "$(cat <<'EOF'
docs: mark Langfuse OTLP phase-1 as implemented

EOF
)"
```

---

## 并行与顺序约束

```
Task 1 → Task 2 → Task 3
              ↘
               Task 4（依赖 observe 属性稳定，建议在 Task 3 后）
Task 5 可在 Task 2 完成后开始（仅 lifespan）
Task 6 最后（全部代码合入 + 手工验收后）
```

禁止：未完成 Task 2 HTTP exporter 就宣称「已接通 Langfuse」。

---

## Spec 覆盖自检

| Spec 项 | 对应 Task |
|---------|-----------|
| G1 observe 未接线 | Task 4 |
| G2 OTLP HTTP | Task 2 |
| G3 Basic Auth + ingestion-version | Task 1 |
| G4 session.id 传播 | Task 3 |
| 环境变量裁决 | Task 1 + 5 |
| pyproject extras | Task 2 |
| 单测不依赖真网 | Task 1–4 |
| 手工真连验收 | Task 6 |
| core 不引入 langfuse 包 | 全程遵守 |
| 阶段 2 Score/Dataset | **不在本计划** |

---

## 后续（阶段 2，另开 plan）

当阶段 1 验收清单全部勾选后，再开 `docs/superpowers/plans/YYYY-MM-DD-langfuse-scores-feedback.md`，覆盖：

- B3 反馈 API → Score（关联 `run_id`）  
- B2 可选截断 content（`LANGFUSE_CAPTURE_CONTENT`）  
- B4 Dataset / 坏 case 流程  
- 仅在 scene extras 引入 `langfuse` SDK（若 REST 不足）
