# Langfuse Scene 集成设计（轨 B）

> 日期：2026-08-11  
> 状态：阶段 1 已落地，阶段 2 待实施  
> 范围：`scene/` 可选接入 Langfuse；**禁止**将 Langfuse SDK / 厂商语义写入 `agent_core/core`  
> 背景决策：需要质量评测闭环（打分 / 坏 case / prompt 对照），测试期即开始采数验证  
> 选定路径：**两阶段** — 先 OTLP 采数，再薄 SDK/API 补 Score/Dataset  
> 关联：`docs/observability-and-quality-plan.md`、`agent_core/observability.py`、`docs/design.md` §观察性、`docs/reference/agent_protocol.md` §9

---

## 1. 目标与非目标

### 1.1 目标

1. **测试期可采数**：本地 / 联调跑一轮对话后，Langfuse UI 能看到与日志同 `run_id` 的 Trace 树  
2. **架构不绑死厂商**：core 继续只产出标准 OTEL span + `AgentEvent`；Langfuse 是 scene 出口之一  
3. **为评测闭环铺路**：阶段 2 可接 Score、Dataset、反馈 API，而不重做埋点  
4. **默认可关**：未配置密钥 / 开关时，行为与今日一致（无额外网络、无硬依赖崩溃）

### 1.2 非目标

- 不在 `agent_core/core`（或 `agent_core` 硬依赖）中引入 `langfuse` 包  
- 不把 Langfuse 当作唯一调试手段（轨 A：结构化日志 + replay + console/Jaeger 仍独立可用）  
- 阶段 1 不做完整 Prompt Management / 自动化评测流水线  
- 不为「面板好看」全量 dump 用户隐私内容（默认元数据 + 截断；全量需显式开关）

---

## 2. 架构边界（硬约束）

```
agent_core（数据面，厂商无关）
  AgentEvent + OTEL spans:
    agent.run → agent.turn → agent.llm_call | agent.tool_call.*
  身份字段: run_id / session_id / turn_index
  度量字段: usage / latency_ms / stop_reason / system_prompt_hash
        ↓
scene/http_sse + scene/h5（组装出口）
  阶段 1: OTLP/HTTP → Langfuse `/api/public/otel`
  阶段 2: 薄封装 Score / Dataset / 反馈 API（可选 langfuse SDK）
        ↓
人：定义成功标准、验收真实路径、审查坏 case
```

| 层级 | 职责 | 禁止 |
|------|------|------|
| `agent_core` | 标准事件 / OTEL span；无 SDK 时 no-op | 绑定 Langfuse 或其他 SaaS 为硬依赖；厂商字段泄漏进 core API |
| `scene/` | 开关、exporter 组装、auth header、可选 SDK、反馈路由 | 把评测 UI 逻辑塞回 loop |
| 测试环境 | 用真实密钥或自建 Langfuse 验证采数 | 把密钥写进仓库 |

**原则**：先标准 span，后选 UI。Langfuse v4 本身是 OTEL-native，与本方案一致。

---

## 3. 现状与缺口

### 3.1 已有（轨 A）

| 能力 | 位置 | 状态 |
|------|------|------|
| `trace_llm_call` / `trace_turn` | `agent_core/core/loop.py` | ✅ |
| `observe()` run span + tool hooks | `agent_core/observability.py` | ✅ 实现存在 |
| `run_id` / 结构化日志 | `logging_config` + loop | ✅ |
| `RunReplayRecorder` | `scene/http_sse/replay.py` | ✅ 可选 |
| `configure_otel_exporter()` | scene lifespan | ✅ console / otlp(gRPC) |

### 3.2 阶段 1 必须补的缺口

| ID | 缺口 | 影响 |
|----|------|------|
| **G1** | scene **从未调用** `observe()` | 无顶层 `agent.run` span；tool hook 未挂，工具 span 缺失或无父子关系 |
| **G2** | 现有 OTLP 走 **gRPC** | Langfuse 目前只收 **OTLP/HTTP**（JSON 或 protobuf），gRPC 不可用 |
| **G3** | 无 Langfuse Basic Auth / `x-langfuse-ingestion-version` 组装 | 无法认证或实时摄入延迟 |
| **G4** | Trace 级属性（`session.id` / `langfuse.session.id` 等）未按 Langfuse 过滤约定传播到每个 span | UI 按 session 筛选不可靠 |

轨 B 代码现状：仓库内 **零** `langfuse` 引用。

---

## 4. 两阶段计划

### 阶段 1 — OTLP 采数验证（现在做）

**成功标准**：任意一次测试对话后，不改业务代码二次埋点，能在 Langfuse 中打开与日志 `run_id=...` 对应的 Trace，并看到：

```
agent.run
 ├─ agent.turn (turn_index=0)
 │   ├─ agent.llm_call   (usage, latency_ms, model)
 │   └─ agent.tool_call.* (若有工具)
 └─ agent.turn ...
```

### 阶段 2 — Score / Dataset / 反馈（阶段 1 验收后再做）

**成功标准**：差评可落到同 `run_id` 的 Score；坏 case 可进 Dataset；可按 `system_prompt_hash` / prompt 版本筛选对照。

---

## 5. 阶段 1 详细设计

### 5.1 环境变量约定

| 变量 | 含义 | 示例 |
|------|------|------|
| `LANGFUSE_ENABLED` | 总开关（默认关） | `1` |
| `LANGFUSE_PUBLIC_KEY` | pk | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | sk | `sk-lf-...` |
| `LANGFUSE_BASE_URL` | 实例根 URL | `https://cloud.langfuse.com` 或 `http://localhost:3000` |
| `LANGFUSE_CAPTURE_CONTENT` | 是否上报截断后的 input/output 文本（默认 `0`，仅元数据） | `0` / `1` |
| 兼容既有 | `OTEL_EXPORTER` / `OTEL_EXPORTER_OTLP_ENDPOINT` | 仍可用于 Jaeger；与 Langfuse 互斥或由配置函数统一裁决 |

**推荐裁决顺序**（scene lifespan）：

1. 若 `LANGFUSE_ENABLED=1` 且密钥齐全 → 配置 OTLP/HTTP → `{BASE_URL}/api/public/otel`，并注入 Auth headers  
2. 否则回退现有 `configure_otel_exporter()`（console / otlp-gRPC / 无）

密钥 **不得** 入库；仅环境变量或本地 `.env`（gitignore）。

### 5.2 Auth Header

Langfuse OTLP 使用 Basic Auth：

```text
Authorization: Basic base64(pk:sk)
x-langfuse-ingestion-version: 4
```

组装落在 scene 配置函数（或 `observability.py` 的可选 HTTP exporter 分支），**不要**把 pk/sk 语义泄漏进 loop。

官方参考：`https://{host}/api/public/otel`（traces 子路径 `/v1/traces` 按 HTTP exporter 要求设置）。

### 5.3 Exporter 改造

扩展 `agent_core/observability.configure_otel_exporter`（或新增 `configure_langfuse_otel_exporter` 由 scene 调用）：

- 新增协议选项：`otlp_http`（protobuf 优先）  
- 支持自定义 headers  
- 保持「未安装 opentelemetry-* 时 no-op + warning」  
- **不**把 `langfuse` 包列为依赖；阶段 1 仅需：
  - `opentelemetry-api`
  - `opentelemetry-sdk`
  - `opentelemetry-exporter-otlp-proto-http`

可选：在 `pyproject.toml` extras 增加 `[otel]` / `[observability]`，文档写明安装命令。

### 5.4 接线 `observe()`（G1）

> **实现注记（2026-08-11）**：实际接线在 `AgentHarness._execute_turn`（非 `chat_assistant`），见 `docs/superpowers/plans/2026-08-11-langfuse-otlp-phase1.md`「相对 Spec 的实现微调」。http_sse 与 h5 共用 harness，`continue_()` 同样覆盖，避免双份逻辑与双 `run_id`。

原设计（`chat_assistant` 外层）示意如下；**已落地路径以 harness 为准**：

在 `scene/http_sse/chat_assistant.py` 与 `scene/h5/chat_assistant.py` 的 **每次 user turn / prompt 路径** 外层：

```python
from agent_core.observability import observe, generate_run_id

run_id = generate_run_id()  # 或 harness/loop 已生成则复用
with observe(
    harness,
    session_id=session_id,
    run_id=run_id,
    provider_name=...,
    model_id=...,
    system_prompt=system_prompt_text or "",
):
    await harness.prompt(...)
```

要求：

- `run_id` 与 `AgentStart.run_id`、结构化日志、`RunReplayRecorder` 一致（优先单一生成点，向下传递，避免双 ID）  
- `observe()` 仅在 OTEL 可用时有副作用；不可用时透传  
- 不在 `loop.py` 内引入 scene/Langfuse 概念

### 5.5 Span 属性约定（便于 Langfuse 过滤）

在现有 `agent.*` 属性之外，阶段 1 至少保证 **每个 span** 带上：

| 属性 | 来源 |
|------|------|
| `agent.run_id` | 已有 |
| `agent.session_id` | 已有 |
| `session.id` 或 `langfuse.session.id` | 与 `agent.session_id` 同值（便于 UI 过滤） |
| `langfuse.trace.metadata.run_id` | 同 `run_id`（可选但推荐） |
| `llm.provider` / `llm.model` / usage / `latency_ms` | llm span 已有 |

`system_prompt_hash` 挂在 `agent.run`（已有）。默认 **不上报** 完整 system prompt / 用户原文；`LANGFUSE_CAPTURE_CONTENT=1` 时才允许截断写入（实现可放阶段 1.1 或阶段 2，阶段 1 MVP 可只做元数据）。

### 5.6 阶段 1 文件变更清单（指导开发）

| 文件 | 变更 |
|------|------|
| `agent_core/observability.py` | OTLP/HTTP exporter + headers；可选 `configure_langfuse_from_env()`；span 属性补 `session.id` |
| `scene/http_sse/server.py` | lifespan：Langfuse 开关优先配置 exporter |
| `scene/h5/server.py` | 同上 |
| `scene/http_sse/chat_assistant.py` | prompt 路径包 `observe()`；统一 `run_id` |
| `scene/h5/chat_assistant.py` | 同上 |
| `pyproject.toml` | 可选 extras `[otel]` 含 http exporter |
| `tests/core/test_observability.py` | HTTP exporter 配置单测（mock，无真网）；observe 属性断言 |
| `docs/observability-and-quality-plan.md` | 标记轨 B 阶段 1 状态 / 链到本规格 |
| `docs/FEATURES.md` | 阶段 1 完成后勾选 |

### 5.7 阶段 1 验收清单

- [ ] `LANGFUSE_ENABLED` 未开时：行为与现状一致  
- [ ] 开启后缺密钥：启动 warning，不崩溃  
- [ ] 开启且密钥正确：一次含工具调用的对话，Langfuse UI 可见完整父子树  
- [ ] 日志中 `run_id=xxx` 与 Trace metadata / span attribute 可互搜  
- [ ] `ENABLE_RUN_REPLAY=1` 时本地 JSON 与 Langfuse 同 `run_id`  
- [ ] 单元测试不依赖真实 Langfuse；可选手工验收脚本/文档步骤  

### 5.8 本地验证步骤（开发用）

```bash
# 依赖
pip install -e ".[test]"
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

# 环境（云或自建 Langfuse >= 3.22）
export LANGFUSE_ENABLED=1
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_BASE_URL=https://cloud.langfuse.com   # 或 http://localhost:3000

# 启动
PORT=8001 python -m scene.http_sse.server
# 浏览器发一条会触发工具的消息，打开 Langfuse Traces 按 session / run_id 查找
```

---

## 6. 阶段 2 设计大纲（不阻塞阶段 1）

| ID | 任务 | 落点 | 说明 |
|----|------|------|------|
| **B2** | 上报摘要、tool 成败、usage、prompt hash/版本标签 | scene 组装 | 仍默认可截断 |
| **B3** | 反馈 API：👍/👎 → Langfuse Score，关联 `run_id` | `scene/http_sse` HTTP + 前端轻量入口 | 可用 REST，不一定立刻上完整 SDK |
| **B4** | Score → 坏 case Dataset；prompt 改动后对照回放 | 脚本 + 流程 | 质量改进有对照 |
| **B-SDK** | 若 REST 不够，再引入可选 `langfuse` extras，仅 scene 使用 | `scene/` + optional dep | **禁止**进入 core |

阶段 2 开始条件：阶段 1 验收清单全部勾选，且团队确认需要打分闭环（而非只要看板）。

---

## 7. 风险与对策

| 风险 | 对策 |
|------|------|
| gRPC exporter 误配到 Langfuse | 文档与代码路径显式 `otlp_http`；Langfuse 模式强制 HTTP |
| 双 `run_id` | 单一生成点 + 向下传；测试断言 AgentStart / span / replay 一致 |
| 隐私泄漏 | 默认 `CAPTURE_CONTENT=0`；CI/文档强调 |
| 与现有 Jaeger OTLP 冲突 | lifespan 裁决：Langfuse 优先或互斥，禁止 silently 双 exporter 除非明确 fan-out |
| Langfuse UI 映射不全（非 GenAI 语义约定） | 先保证自定义 `agent.*` 可读；阶段 2 再按需对齐 GenAI semconv / langfuse 属性 |
| 「只为采数」拖进 SDK 大改造 | 严格两阶段；阶段 1 零 langfuse 包 |

---

## 8. 实施顺序（禁止并行大干）

```
1. observability: OTLP/HTTP + headers + Langfuse-from-env
2. scene lifespan 接线开关
3. chat_assistant（http_sse + h5）observe() + run_id 统一
4. 单测（配置 / 属性 / 开关）
5. 手工：真连 Langfuse 跑一条工具链对话验收
6. 更新 observability-and-quality-plan / FEATURES / development-log
── 阶段 1 完成闸门 ──
7. 阶段 2：Score API → 前端反馈 → Dataset 流程
```

---

## 9. 决策记录

| 日期 | 决策 |
|------|------|
| 2026-08-11 | **不**在 `agent_core/core` 接入 Langfuse |
| 2026-08-11 | 需要轨 B 质量能力；测试期即开始采数 |
| 2026-08-11 | 采用两阶段：OTLP 验证 → 再 Score/Dataset |
| 2026-08-11 | 本规格指导后续代码开发；实现前以本文件为验收依据 |

---

## 10. 参考

- `docs/observability-and-quality-plan.md` — 双轨总策略  
- `agent_core/observability.py` — 现有 OTEL API  
- Langfuse OTEL 文档：`/api/public/otel`、Basic Auth、`x-langfuse-ingestion-version: 4`、仅 HTTP  
- `docs/reference/agent_protocol.md` §9 — Trace / Event / State 三类观测  
