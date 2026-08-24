# Langfuse 观测链路设计文档（可独立复现）

> 版本：1.0
> 日期：2026-08-24
> 定位：一份**与任何具体代码仓库无关**的设计文档。只要你的应用在自行编排「LLM 调用 + 工具调用」（Agent 循环），就可以只凭本文实现并接入 Langfuse 观测。核心设计（span 命名、属性、OTLP 映射、配置约定）保持一致即可。
> 适用语言/框架：不限（本文示例用 Python 伪代码，模式可平移到任意语言）；前提是应用能接入 OpenTelemetry。

---

## 1. 设计目标与非目标

### 1.1 目标

1. **一条用户消息 / 一次任务，在 Langfuse 里长成完整 Trace 树**：`run → turn → llm_call / tool_call`，能回答「卡在第几轮、哪个 LLM 调用、哪个工具」。
2. **可插拔**：不装 OTEL 依赖、不配置密钥时，业务零影响（无网络、不崩溃、无额外日志噪音）。
3. **一条数据血脉**：本地结构化日志与 Langfuse 面板用同一个 `run_id` 互搜互跳，调试与评测共用同一套埋点。
4. **为质量闭环预留出口**：打分（Score）、坏 case 归档、prompt 对照都可以在同一条链路上补，无需重做埋点。

### 1.2 非目标

- 不把 `langfuse` SDK 作为硬依赖写进核心层；采数优先走**标准 OpenTelemetry**。
- 不做完整 Prompt 管理 / 自动化评测流水线。
- 默认不上报用户内容（隐私）；全量内容必须显式开关。

---

## 2. 架构原则（三层边界）

| 层 | 职责 | 硬约束 |
|----|------|--------|
| **数据面**（框架 / 核心逻辑） | 只产出标准 OTEL span + 业务事件；span 属性遵循 OTel GenAI 语义约定 | 不 import `langfuse`；无 OTEL 依赖时全部 no-op；不把厂商语义泄漏进公共 API |
| **组装面**（应用 / 部署层） | 读取 `LANGFUSE_*` 环境变量、配置 exporter、暴露用户反馈 API | 厂商接入只在这一层发生；开关默认关 |
| **人** | 定义成功标准、跑真实路径验收、审查坏 case | 不只看「面板好看」 |

三条经过实测验证的硬约束：

1. **core 不绑 Langfuse SDK**：曾出现「SDK 补发 generation + OTLP span」双通道，导致同一 LLM 调用在面板出现**两条同名 span**。结论：只保留 OTLP 一条链路。
2. **观测必须可选**：未配置时行为与未装 OTEL 完全一致。
3. **默认不抓内容**：默认只上报元数据；prompt/响应文本要显式开 `LANGFUSE_CAPTURE_CONTENT=1`。

---

## 3. 链路总览（一图流）

```
用户消息 / 任务
    │
    ▼
应用运行入口（每任务调用一次）
    ├─ 生成 run_id（单一生成点）
    ├─ run 级包裹 → agent.run 顶层 span + 挂工具 hook + 订阅 turn 事件
    │     │
    │     ▼  Agent 循环（多轮执行）
    │     ├─ TurnStart 事件 → agent.turn span（事件驱动，不侵入循环控制流）
    │     │     ├─ LLM 流式调用包裹 → agent.llm_call span（映射为 generation）
    │     │     │     流结束后回填 usage / stop_reason / TTFT / completion
    │     │     └─ 工具执行 before/after hook → agent.tool_call.{name} span
    │     └─ TurnEnd 事件 → agent.turn span 结束
    │
    └─ 运行结束 → agent.run span 结束（附 skill/prompt 版本等汇总属性）
        │
        ▼  启动期已配置（组装面）
OTLP/HTTP exporter → {LANGFUSE_BASE_URL}/api/public/otel/v1/traces
    （Basic Auth + x-langfuse-ingestion-version: 4）
        │
        ▼
Langfuse（云 / 自托管 v4）
    └─ 每个 run 一个 Trace：agent.run
            └─ agent.turn*
                  ├─ agent.llm_call（generation，含 usage/cost/TTFT）
                  └─ agent.tool_call.*（span）

可选闭环：用户在 UI 点赞/点踩 → 反馈 API → POST {base}/api/public/scores
    （数值分数，metadata 带 run_id，与 Trace 关联）
```

---

## 4. 核心数据模型：Trace 树与身份

### 4.1 Span 树（**必须保持一致的命名**）

```
agent.run                       (SpanKind.INTERNAL)   ← 一个 Trace 的根
 └─ agent.turn                  (INTERNAL, 属性 agent.turn_index=N)
     ├─ agent.llm_call          (SpanKind.CLIENT)     ← Langfuse 映射为 generation
     └─ agent.tool_call.{name}  (INTERNAL)            ← name 为工具名
```

- `agent.run`：一次用户消息 / 一次任务的端到端执行，只创建一次。
- `agent.turn`：Agent 循环里的一轮（一次 LLM 调用 + 可能的工具执行）。**推荐事件驱动**：订阅业务层 `TurnStart`/`TurnEnd` 事件来创建/结束 span，并把 turn span 设为当前 context（`trace.set_span_in_context` + `context.attach`），这样其内部的 LLM/工具 span 自动成为子节点，且不侵入循环控制流、覆盖所有分支（包括强制收尾的轮次）。
- `agent.llm_call`：每次 LLM 流式调用一个 span。
- `agent.tool_call.{name}`：每次工具调用一个 span。

### 4.2 身份字段

| 字段 | 生成规则 | 用途 |
|------|----------|------|
| `run_id` | `run-{uuid4().hex[:12]}`（如 `run-a1b2c3d4e5f6`） | 一次任务的唯一身份；日志 ↔ 事件 ↔ 面板互搜的锚点 |
| `session_id` | 会话 id（业务已有） | 按会话筛选 |
| `user_id` | 用户 id（业务已有） | 按用户筛选 |
| `system_prompt_hash` | system prompt 的 SHA-256 前 12 位 | prompt 版本对照 |

### 4.3 run_id 贯穿约定（硬约束）

- **单一生成点**：在任务入口生成一次，向下传给所有 span / 事件 / 日志上下文；任何组件不得自行再生成。
- 每个 span 都写 `langfuse.trace.metadata.run_id`（见 §7.1），保证面板内可按 run_id 检索。
- 业务事件（如任务开始事件）带 `run_id`，让实时 UI 也能拿到同一身份。

---

## 5. 配置与环境变量（设计约定）

| 变量 | 含义 | 默认 | 示例 |
|------|------|------|------|
| `LANGFUSE_ENABLED` | 总开关 | `0` | `1` |
| `LANGFUSE_PUBLIC_KEY` | pk | 无 | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | sk | 无 | `sk-lf-...` |
| `LANGFUSE_BASE_URL` | Langfuse 实例根 URL（不含 `/api`） | `https://cloud.langfuse.com` | `http://localhost:3000` 或内网地址 |
| `LANGFUSE_CAPTURE_CONTENT` | 是否上报截断后的 input/output 文本 | `0` | `0` / `1` |
| 兼容既有 | `OTEL_EXPORTER` / `OTEL_EXPORTER_OTLP_ENDPOINT` | — | 用于 Jaeger 等本地后端；与 Langfuse 互斥 |

**判定逻辑**（组装面实现）：

- `LANGFUSE_ENABLED` 非真 → 不配置 Langfuse。
- 开关开但 pk/sk 缺失 → 打 warning，**不崩溃**。
- 开关开且密钥齐全 → 配置 OTLP/HTTP exporter，endpoint 为 `{LANGFUSE_BASE_URL}/api/public/otel/v1/traces`。

---

## 6. 接入点设计（4 个必选 + 2 个可选）

> 以下用 Python 伪代码给出**接口形状**，函数名可自选；**必须保持一致的是 span 名与属性**（见 §7）。每个接入点对应你项目里的一个真实位置（如何定位见 §12）。

### 6.1 启动期：配置 exporter（必选）

在应用启动 / lifespan 处调用一次：

```python
# 组装面：Langfuse 优先，否则回退本地 console / Jaeger
if not configure_langfuse_otel_from_env():
    configure_otel_exporter()   # 读取 OTEL_EXPORTER：console / otlp(gRPC) / otlp_http
```

`configure_langfuse_otel_from_env()` 内部：

1. 按 §5 判定是否启用；
2. 设置全局 `TracerProvider`（resource 含 `service.name`）；
3. 挂 `BatchSpanProcessor(OTLPSpanExporter(endpoint=..., headers=...))`；
4. 请求头：

```
Authorization: Basic base64("{public_key}:{secret_key}")
x-langfuse-ingestion-version: 4
```

### 6.2 run 级包裹（必选）

包裹**一次任务的完整执行**。职责：创建 `agent.run` span、挂工具 hook、订阅 turn 事件、退出/异常时清理（卸 hook、退订、补 end 所有未关闭的 turn/tool span）。

```python
with trace_run(
    session_id=session_id,
    run_id=run_id,                 # 由生成点传入，内部不得再生成
    user_id=user_id,
    provider=provider,
    model=model,
    system_prompt=system_prompt,
):
    await run_agent_loop(...)      # 你的主循环
```

异常时把 `agent.run` 置为 ERROR 并 re-raise。

### 6.3 LLM 调用包裹（必选）

包裹**每次 LLM 流式调用**。产出 `agent.llm_call` generation span。流结束后调用方把用量数据填进返回的 **mutable dict**，由包裹函数统一写 span 属性：

```python
with trace_llm_call(
    provider=model.provider,
    model=model.id,
    session_id=session_id,
    run_id=run_id,
    turn_index=turn_count,
    user_id=user_id,
    prompt=last_user_text,          # 仅用于 CAPTURE_CONTENT=1 时写 gen_ai.prompt
) as trace:
    async for upd in stream_llm(...):
        ...
    trace.update(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        stop_reason=assistant.stop_reason,
        first_token_time=assistant.first_token_time,   # 流式场景：收到首 token 的时间戳
        completion=assistant_text,
    )
```

要点：

- **每个调用点都要包**：包括首次流式尝试与重试尝试；纯文本分支同样要包。
- `trace` 是可变 dict；`trace_llm_call` 在 `finally` 中统一写属性（即使中途异常也写已回填的部分），异常时置 ERROR 并 re-raise。
- prompt 文本默认不落 span；只有 `LANGFUSE_CAPTURE_CONTENT=1` 才写（截断）。

### 6.4 run_id 身份贯穿（必选）

- 任务入口调用 `generate_run_id()`，得到 `run-xxxxxxxxxxxx`。
- 向下传递到：run 包裹、turn 事件订阅、每个 LLM/工具 span、业务事件（`run_id` 字段）、结构化日志上下文。
- 结构化日志建议用 contextvars（协程隔离）给每条日志带 `[session_id|run_id|turn]`，与 Langfuse 面板互搜。

### 6.5 工具调用 span（推荐）

如果应用有工具执行器，通过 before/after hook 包一层：

```python
# before：创建 agent.tool_call.{name} span，记录 tool.name / tool.call_id
# after ：按 is_error 置 ERROR，写 tool.output / tool.error，然后 end
```

实现注意：before/after 收到的调用上下文**不是同一个对象**，不能靠上下文传 span；用 `{run_id}:{tool_call_id}` 字典把 before 创建的 span 和 after 配对，结束时弹出并 end。

### 6.6 用户反馈打分（可选闭环）

用 HTTP 客户端（不需要 langfuse SDK）POST 到 Langfuse Public API：

```
POST {LANGFUSE_BASE_URL}/api/public/scores
Authorization: Basic base64("{pk}:{sk}")
Content-Type: application/json

{
  "name": "user-feedback",
  "value": 1.0,                    # 👍=1.0 / 👎=0.0
  "dataType": "NUMERIC",
  "comment": "用户留言",
  "metadata": {"run_id": "run-..."},
  "sessionId": "sess-..."           # 可选
}
```

未配置 `LANGFUSE_*` 时静默跳过（返回 False），**本地反馈流程不受影响**。

---

## 7. Span 与属性规格（**必须保持一致**）

### 7.1 公共身份属性（每个 span 都写）

| 属性 | 值 |
|------|----|
| `session.id` | 会话 id（OTel 语义） |
| `langfuse.session.id` | 同上（Langfuse 过滤约定） |
| `langfuse.trace.metadata.run_id` | `run-xxxxxxxxxxxx`（与日志互搜关键） |
| `user.id` | 用户 id |

### 7.2 agent.run（顶层）

| 属性 | 说明 |
|------|------|
| `agent.provider` / `agent.model` | LLM 身份 |
| `agent.system_prompt_hash` | SHA-256 前 12 位，prompt 版本对照 |
| `agent.skills.activated` / `agent.skills.sources` | （可选）技能/能力激活汇总，运行结束后写入 |

### 7.3 agent.turn

| 属性 | 说明 |
|------|------|
| `agent.turn_index` | 第几轮（从 1 开始） |

### 7.4 agent.llm_call（generation）

| 属性 | 说明 |
|------|------|
| `gen_ai.operation.name=chat` | OTel GenAI 语义约定 |
| `gen_ai.system` / `gen_ai.request.model` | provider / model |
| `agent.turn_index` | 第几轮 |
| `langfuse.observation.type=generation` | **Langfuse 映射为 generation 的关键**（§8） |
| `gen_ai.usage.input_tokens` / `output_tokens` | token 用量 |
| `gen_ai.response.finish_reasons` | stop_reason |
| `langfuse.observation.usage_details` | JSON `{"input":N,"output":M}`（自托管 v4.x 兼容，§8） |
| `gen_ai.response.first_token_time` / `langfuse.observation.completion_start_time` | TTFT（ISO 8601 时间） |
| `gen_ai.prompt` / `gen_ai.completion` | **仅** `LANGFUSE_CAPTURE_CONTENT=1`，各截断 2000 字符 |

### 7.5 agent.tool_call.{name}

| 属性 | 说明 |
|------|------|
| `tool.name` / `tool.call_id` | 工具身份 |
| `tool.input` | 仅 `LANGFUSE_CAPTURE_CONTENT=1`（json 序列化参数） |
| `tool.output` / `tool.error` | 仅 `LANGFUSE_CAPTURE_CONTENT=1`（文本截断 2000） |

---

## 8. Langfuse OTLP 映射要点（最容易踩坑）

Langfuse 的 `/api/public/otel/v1/traces` 把 OTLP span 映射到自己的数据模型，以下均为实测确认：

1. **只走 OTLP/HTTP**：gRPC 不可用。endpoint 必须是完整 traces 路径，exporter 类型必须是 `otlp_http`。
2. **认证头**：`Authorization: Basic base64("{pk}:{sk}")` + `x-langfuse-ingestion-version: 4`。
3. **generation 映射靠显式属性**：仅 `gen_ai.*` 在部分自托管版本不会映射为 generation/usage/cost。必须额外写：
   - `langfuse.observation.type=generation`
   - `langfuse.observation.usage_details`（JSON）
   - `langfuse.observation.completion_start_time`（TTFT 所需）
4. **不要用无效属性名**：如 `langfuse.observation.model` 与 SDK 常量不一致（应为 `langfuse.observation.model.name`），面板不认。model 统一走 `gen_ai.request.model`。
5. **一个 Trace 一棵树**：同一次 run 的所有 span 共享同一 OTLP trace_id（由 `agent.run` 的 context 向下传播），Langfuse 按 trace_id 聚成一个 Trace；`run_id` 写进 `langfuse.trace.metadata.run_id` 便于检索。
6. **杜绝双通道**：不要在 OTLP 之外再用 langfuse SDK 补发 generation，否则同一调用出现两条同名 span（实测踩过）。

---

## 9. 关闭 / 降级行为

| 场景 | 行为 |
|------|------|
| 未装 opentelemetry | 所有包裹函数直接透传（yield），全 no-op |
| `LANGFUSE_ENABLED=0` 或未设 | 不配 Langfuse；可回退本地 exporter（console / Jaeger） |
| 开关开、密钥缺失 | 打 warning，不崩溃 |
| 网络 / 后端失败 | BatchSpanProcessor 内部记录失败，**不阻塞业务** |
| `LANGFUSE_CAPTURE_CONTENT=0`（默认） | 只上报元数据，不写 prompt/响应文本 |

本地调试出口（与 Langfuse 并行）：结构化日志（`[session_id|run_id|turn]`）+ console exporter + 可选 JSON 回放文件。即使完全不接 Langfuse，也应能 5 分钟内讲清一次失败任务的因果链。

---

## 10. 验收清单

接入完成后逐条打勾：

- [ ] `LANGFUSE_ENABLED` 未开：行为与未装 OTEL 一致，无网络请求
- [ ] 开关开、密钥缺失：启动打 warning 不崩溃
- [ ] 开关开、密钥正确：一次**含工具调用**的任务后，Langfuse UI 可见完整父子树：
      `agent.run → agent.turn → (agent.llm_call + agent.tool_call.*)`
- [ ] LLM 调用显示为 generation，usage/cost 正确；TTFT 有值
- [ ] 日志 `run_id=xxx` 与 Langfuse 面板可互搜
- [ ] 默认不抓 prompt/响应原文；开 `LANGFUSE_CAPTURE_CONTENT=1` 后可见截断内容
- [ ] 单测不依赖真实 Langfuse（mock exporter / 只断言属性与开关降级）
- [ ] （可选）点 👍/👎 后，Langfuse 出现 `user-feedback` Score 且关联 `run_id`

---

## 11. 常见坑与对策

| 坑 | 现象 | 对策 |
|----|------|------|
| SDK + OTLP 双通道 | 同一 LLM 调用面板两条同名 span | 只留 OTLP 一条链路 |
| 属性名写错 | generation/usage/cost 不显示 | 用 §7/§8 的白名单属性 |
| 用 gRPC 配 Langfuse | 数据上不去 | 强制 `otlp_http` + `/api/public/otel/v1/traces` |
| 工具 after-hook 拿不到 before 的 span | 工具 span 永不 end | 用 `{run_id}:{tool_call_id}` 字典配对 |
| hook 注册后不清理 | 跨任务累积、span 重复 | run 包裹 finally 中卸 hook + 退订 + 补 end pending span |
| 异常中断 turn | 缺 TurnEnd → turn span 泄漏 | 新 TurnStart 前先关 stale turn span；run 包裹收尾兜底 |
| 自托管 v4 不认 `gen_ai.usage.*` | usage 为空 | 额外写 `langfuse.observation.usage_details` JSON |
| 无 run_id 统一语义 | 日志/事件/面板对不上 | 单一生成点向下传（§4.3） |

---

## 12. 实施清单（在你的项目里怎么落地）

| # | 要做什么 | 在你项目里找哪个位置 |
|---|----------|----------------------|
| 1 | 加 `opentelemetry-api/sdk` + `opentelemetry-exporter-otlp-proto-http` 可选依赖 | 依赖管理文件（放 optional extra） |
| 2 | 实现 `configure_langfuse_otel_from_env()`（§5/§6.1） | 进程启动 / 框架 lifespan |
| 3 | 实现 run 级包裹 `trace_run()`（§6.2/§7.2） | 每次「用户消息/任务」的处理入口 |
| 4 | 实现 LLM 包裹 `trace_llm_call()`（§6.3/§7.4） | 所有 LLM 流式调用点（含重试分支） |
| 5 | 实现 `generate_run_id()` 与身份传递（§6.4） | 任务入口生成，贯穿事件/日志/SSE |
| 6 | （推荐）工具 hook（§6.5/§7.5） | 工具执行器的 before/after 回调 |
| 7 | 默认只采元数据，内容显式开关 | 全局常量 `LANGFUSE_CAPTURE_CONTENT` |
| 8 | （可选）反馈 API → Score（§6.6） | 用户反馈/打分的接口处 |
| 9 | 单测 mock 掉网络，只断言属性/开关/降级 | 测试里 mock OTLP exporter，断言 span 属性 |

完成第 2–5 项即可在 Langfuse 看到与 §4.1 相同的 Trace 树；第 8 项补齐打分闭环。

---

## 13. 参考

- Langfuse 官方 OTLP 接入文档：endpoint `/api/public/otel/v1/traces`、Basic Auth、`x-langfuse-ingestion-version: 4`、仅 HTTP
- OpenTelemetry GenAI semantic conventions（`gen_ai.*` 属性族）
- OpenTelemetry OTLP/HTTP exporter 用法（你所用语言 SDK 的文档）

---

## 附录 A：已验证结论（与仓库无关的实测知识）

本设计的核心链路已在一套真实生产代码（Python asyncio + Agent 循环 + 工具调用）中验证：

- Langfuse v4 自托管对 OTLP/HTTP 的映射行为与云版基本一致；`gen_ai.*` 到 usage/cost 的自动映射**并非所有版本都可靠**，因此保留 `langfuse.observation.usage_details` 兜底。
- 事件驱动的 turn span（订阅 TurnStart/TurnEnd）能覆盖包括 max_turns 强制收尾在内的全部分支，且不侵入循环代码。
- 单通道 OTLP（不叠加 SDK）在面板中每个 LLM 调用只出现一条 generation。
- 打分链路用 Public API + Basic Auth 即可，无需引入 langfuse SDK。
