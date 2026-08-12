# OTEL GenAI 属性对齐（Langfuse Dashboard 可验收）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 LLM 相关 span 属性改为 OpenTelemetry GenAI 语义约定，使任意 OTLP 后端（当前测试出口为 Langfuse）能正确展示 model / tokens / latency / user 维度；**不**引入 `langfuse` Python 包，**不**把厂商语义绑进 `agent_core/core`。

**Architecture:**  
- **数据面（agent_core）**：标准 OTEL span + `gen_ai.*` / `user.id` / `session.id`；测试期 **一次切干净**，删除自定义 `llm.*` / `latency_ms`。  
- **出口（scene）**：lifespan 优先 Langfuse OTLP/HTTP；未配置则回退 `configure_otel_exporter()`（console / 其它 OTLP）。  
- **验收 UI（当前）**：用 Langfuse Dashboard 验证；属性命名以 OTEL/业界约定为准，不依赖 Langfuse 私有前缀才能工作。

**Tech Stack:** `agent_core/observability.py`、`AgentHarness`、`scene/h5|http_sse`、pytest、`[otel]` extras

**背景:** 阶段 1 已能导出 trace 树；自定义 `llm.*` 不被 GenAI 映射，故 Model latencies / User consumption 等为空。  
**参考:** [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) · [Langfuse OTel property mapping](https://langfuse.com/integrations/native/opentelemetry)（仅作「出口如何读标准字段」的对照，不是数据面 API）

---

## 0. 定位：不是「只给 Langfuse 用」

```
agent_core 产 OTEL span（厂商无关）
        ↓
scene exporter 二选一：
  LANGFUSE_* 已配 → OTLP/HTTP → Langfuse（当前测试主路径）
  否则            → console / OTEL_EXPORTER=* → Jaeger 等
```

| 层 | 职责 | 禁止 |
|----|------|------|
| `agent_core/observability` | 标准 span + GenAI / 身份属性 | 硬依赖 `langfuse` 包；业务逻辑读 span |
| `scene` | 选 exporter、把 `uid` 注入 harness | 在 core loop 里写厂商字段 |
| Langfuse | **当前** Dashboard / 评测 UI | 不是唯一合法后端 |

仓库内 **没有** 其它模块消费 span 属性；结构化日志（`run_id` 等）独立。因此彻底改属性名在测试期安全。

---

## 1. 问题与成功标准

### 1.1 现状缺口

| 能力（后端无关） | Langfuse 面板表现 | 依赖字段 | 当前 | 结果 |
|------------------|-------------------|----------|------|------|
| Model + generation | Model latencies / Model 列 | `gen_ai.request.model`（及 span duration） | `llm.model` | 空 |
| Token usage | Tokens / consumption | `gen_ai.usage.input_tokens` / `output_tokens` | `llm.usage.*` | 空 |
| Per-user 聚合 | User consumption | `user.id` + usage | 无 | 空 |
| Cost | Cost | usage + 后端价目表 | model 不对 | 常空 |
| Session | Session 筛选 | `session.id` | ✅ | 可用 |

### 1.2 成功标准

**主验收（当前出口 = Langfuse）：** 一轮真实对话后：

1. `agent.llm_call` 显示 Model、Tokens（provider 有返回 usage 时）  
2. Dashboard → Model latencies 有该 model  
3. 带 `uid` 登录时 → User consumption 能按 uid 聚合  
4. run → turn → llm/tool 树不退化；单测全绿  

**架构验收：** span 属性以 `gen_ai.*` / `user.id` / `session.id` 为主；**不要求** `langfuse.*` 私有键才能出数（已有的 `langfuse.session.id` 别名可保留作兼容，见 D8）。

### 1.3 非目标

- 不引入 `langfuse` 包  
- 默认不上报完整 prompt/completion  
- 不保证第三方模型在 Langfuse 价目表有 USD（缺价时 tokens/latency 仍应有）  
- 不做 Score / Dataset（阶段 2）  
- 不改 loop 内 LLM 调用逻辑（usage 已写入 `_llm_trace` dict）

---

## 2. 决策锁定

| ID | 决策 | 说明 |
|----|------|------|
| D1 | **彻底改造，不双写** | 删除 `llm.*` / `latency_ms`；只保留 GenAI + 标准身份字段 |
| D2 | LLM span = generation | **靠** `gen_ai.request.model`（Langfuse：带 model 的 span → generation）。**不**强制写 `langfuse.observation.type` |
| D3 | `user.id` | header `uid` → harness → observe；空则不写 |
| D4 | 延迟 | **只**用 span start/end；删除 `latency_ms` |
| D5 | usage | **只** `gen_ai.usage.input_tokens` / `output_tokens` |
| D6 | 传播 | `user.id` / `session.id` 至少在 **run + llm**；tool hook 尽量带上 |
| D7 | stop_reason | 用 `gen_ai.response.finish_reasons`（字符串，有则写）；**不用** `llm.stop_reason` / 不为它新增 `langfuse.observation.metadata.*` |
| D8 | 厂商前缀 | **core 不新增** `langfuse.*`。已有 `langfuse.session.id`（与 `session.id` 别名）可保留，避免打断现有 session 筛选；新代码优先标准键 |
| D9 | 出口无关 | 属性命名不假设唯一后端；验收可用 Langfuse，实现按 OTEL GenAI |

### 2.1 为何不双写

测试期无下游读自定义 `llm.*`；双写只会让文档/测试/面板长期两套名字。一次切干净，验收更清晰。

### 2.2 目标属性清单（`agent.llm_call`）— 唯一真相

```text
# GenAI（数据面标准）
gen_ai.operation.name     = "chat"
gen_ai.system             = <provider>
gen_ai.request.model      = <model_id>

# usage（stream 结束后）
gen_ai.usage.input_tokens
gen_ai.usage.output_tokens

# 身份
user.id                   = <uid>          # 非空才写
session.id                = <session_id>
# 可选兼容（已有别名逻辑，非本任务新增依赖）:
# langfuse.session.id     = <session_id>

# finish（有则写）
gen_ai.response.finish_reasons = <stop_reason>   # 单值字符串即可

# 删除
# llm.* / latency_ms / langfuse.observation.type（不写）
```

### 2.3 `agent.run` 补充

```text
user.id
# 已有: session.id, agent.run_id, agent.provider, agent.model, skills.*
# generation 维度以 llm span 的 gen_ai.request.model 为准
```

---

## 3. 文件结构

| 文件 | 职责 |
|------|------|
| **Modify** `agent_core/observability.py` | `trace_llm_call` / `observe` / `agent_span_attributes` → GenAI + user；删旧键 |
| **Modify** `agent_core/session/harness.py` | 传入 `user_id`；`observability_user_id` |
| **Modify** `scene/h5/chat_assistant.py`、`scene/http_sse/chat_assistant.py` | `uid`/`owner` → harness |
| **Modify** `tests/core/test_observability.py` | 断言 gen_ai.*；断言无 llm.* / latency_ms |
| **Modify/Create** session 相关测试 | user_id 传到 observe |
| **Modify** `docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md` | 写明「OTEL 数据面 / Langfuse 出口」与属性表 |
| **Modify** `docs/FEATURES.md`、`docs/development-log/YYYY-MM-DD.md` | 状态 |

**不改：** `demo/`；`agent_core/core/loop.py` 仅继续填充 `_llm_trace` dict（键名仍是代码内 `input_tokens` 等，与 span 属性无关）。

---

## 4. 实施任务

### Task 1: `trace_llm_call` 切到 GenAI 属性

**Files:**
- Modify: `agent_core/observability.py`
- Test: `tests/core/test_observability.py`

- [ ] **Step 1: 写失败测试 — 有 gen_ai，无旧键，无强制 langfuse.observation.type**

```python
def test_trace_llm_call_sets_gen_ai_attributes(monkeypatch):
    from unittest.mock import MagicMock
    from agent_core import observability as obs
    from agent_core.observability import trace_llm_call

    monkeypatch.setattr(obs, "_otel_available", True)
    # ... mock SpanKind / Status / StatusCode / _get_tracer ...

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_span.return_value = mock_span
    monkeypatch.setattr(obs, "_get_tracer", lambda: mock_tracer)

    with trace_llm_call(
        provider="deepseek",
        model="deepseek-v4-flash",
        session_id="s1",
        run_id="run-1",
        user_id="u-42",
    ) as result:
        result["input_tokens"] = 10
        result["output_tokens"] = 20
        result["stop_reason"] = "stop"

    attrs = mock_tracer.start_span.call_args.kwargs["attributes"]
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "deepseek-v4-flash"
    assert attrs["gen_ai.system"] == "deepseek"
    assert attrs["user.id"] == "u-42"
    assert "llm.model" not in attrs
    assert "llm.provider" not in attrs
    assert "langfuse.observation.type" not in attrs  # 不写厂商 type
    mock_span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 10)
    mock_span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 20)
    mock_span.set_attribute.assert_any_call("gen_ai.response.finish_reasons", "stop")
    set_keys = [c.args[0] for c in mock_span.set_attribute.call_args_list]
    assert "llm.usage.input_tokens" not in set_keys
    assert "latency_ms" not in set_keys
```

- [ ] **Step 2:** `pytest tests/core/test_observability.py::test_trace_llm_call_sets_gen_ai_attributes -v`（期望失败）

- [ ] **Step 3: 实现** — `trace_llm_call(..., user_id="")` 按 §2.2 替换属性；删 `llm.*` / `latency_ms`；更新 docstring

- [ ] **Step 4:** `pytest tests/core/test_observability.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(observability): align llm spans with OTel gen_ai semantic conventions

EOF
)"
```

---

### Task 2: `observe()` / harness 传播 `user.id`

**Files:**
- Modify: `agent_core/observability.py`、`agent_core/session/harness.py`
- Test: `tests/core/test_observability.py` 或 `tests/session/test_harness_user_id_observe.py`

- [ ] **Step 1: user_id 优先级**（写进代码注释）  
  1) `observe(..., user_id=)` 2) `harness.observability_user_id` 3) `harness.owner`（若有）

- [ ] **Step 2: 失败测试** — `observe(..., user_id="u1")` 时 run span attributes 含 `user.id`

- [ ] **Step 3: 实现** — run + tool hook 带 `user.id`；harness `_execute_turn` 传入

- [ ] **Step 4:** 跑相关 pytest

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(observability): propagate user.id on run and llm spans

EOF
)"
```

---

### Task 3: Scene 把请求 `uid` 接到 harness

**Files:** `scene/h5/chat_assistant.py`、`scene/http_sse/chat_assistant.py`（必要时 manager）

- [ ] **Step 1:** 确认 `owner`/`companion_uid` 是否已进 harness；否则 `harness.observability_user_id = owner`

- [ ] **Step 2:** h5 + http_sse 对称接线

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(scene): wire request uid into harness observability user.id

EOF
)"
```

---

### Task 4: 文档与验收

**Files:** Langfuse 设计 spec、FEATURES、development-log

- [ ] **Step 1:** Spec 增补「数据面 = OTEL GenAI；出口 = Langfuse 可选」+ §2.2 属性表  
- [ ] **Step 2:** FEATURES 勾选「OTEL GenAI 属性对齐（Dashboard 可验收）」  
- [ ] **Step 3:** 本地用 Langfuse 做出口验收（清单见下）  
- [ ] **Step 4: Commit docs**

**验收命令（出口示例）：**

```bash
PORT=8001 .venv/bin/python -m scene.h5.server
# 登录带 uid，发一条触发 LLM 的消息
# Langfuse: agent.llm_call → Model/Tokens；Dashboard → Model latencies / User consumption
```

可选：`OTEL_EXPORTER=console` 且关掉 Langfuse，确认 stdout span 仍是 `gen_ai.*`（证明非绑死 Langfuse）。

---

## 5. 测试矩阵

| 场景 | 期望 |
|------|------|
| OTEL 未安装 | no-op，无异常 |
| 有 usage | `gen_ai.usage.*` 存在 |
| 无 user_id | 不写 `user.id`，其余 gen_ai 仍在 |
| 有 user_id | run + llm 均有 |
| 旧键 | **无** `llm.*` / `latency_ms` |
| 厂商键 | **无新增** `langfuse.observation.type`；不依赖其才能出 generation |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 某后端对 `gen_ai.request.model` 识别弱 | 以 OTEL 约定为准；Langfuse 映射表已支持 |
| Cost 仍为 0 | 后端价目表缺模型；tokens/latency 仍验收 |
| Provider 不回 usage | tokens 空；latency 仍有 |
| 已有 `langfuse.session.id` 别名 | 保留，不扩大；新逻辑不依赖 |

---

## 7. 排期

| Task | 预估 |
|------|------|
| 1 GenAI llm | 0.5–1h |
| 2 user.id + harness | 0.5h |
| 3 scene uid | 0.5h |
| 4 文档 + 验收 | 0.5h |

约半天。

---

## 8. 起步命令

```bash
pip install -e ".[test,otel]"
pytest tests/core/test_observability.py -v
pytest tests/session/test_harness_observe_run_id.py -v
```

实施以 **§0 定位**、**§2 决策**、**§4 勾选** 为准；与口头冲突时先改本文再改代码。
