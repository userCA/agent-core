---
name: dev-process-backend
description: "后端开发流程规范（Python/agent-core）—— dev-process-optimizer 的子 skill。预防：模块间重复代码、死字段、导入错误、静默异常、monkey-patching 回归。覆盖：core/ providers/ session/ tools/ 各层。"
---

# 后端开发流程规范（agent-core）

> 子 skill，架构/跨层问题先看 `dev-process-optimizer`。

防止重复犯错。每条规则都源于 `docs/mistake-log.md` 和 `docs/development-log/` 中记录的真实 bug。

---

## 修改前快速检查

```
□ 读过 docs/mistake-log.md —— 有没有匹配的历史模式？
□ 是否已有代码做了同样的事？Grep 搜索相似函数签名。
□ 如果要删除一个 import：grep 整个文件的所有引用（isinstance、字符串注解、动态访问）
□ 如果要新增字段：它被写入 AND 读取了吗？只写不读 = 死代码。
```

---

## 规则 1：去重 —— 一处定义，一处维护

**模式：** 两个模块里出现相同的函数签名 → 一定会分化。一处修了 bug，另一处烂掉。

**真实案例（2026-05-26）：** `_create_openai_converter` + `_user_content_to_openai` 在 `openai_provider.py`（53+18 行）和 `agent.py`（`_default_convert_to_llm` + `_user_content_to_openai`）中完全重复。删除了 provider 的副本，因为 Agent 在没有 provider 的 `create_message_converter` 时已会自动回退到默认实现。Anthropic 的 converter 保留了，因为它产出的是不同的格式（Anthropic-native content blocks）。

**检查清单：**
- 写 converter/helper/utility 之前：grep 搜索相似函数签名
- Provider 需要 `create_message_converter`？只有产出格式和 OpenAI 默认不同时才需要
- 同一逻辑出现在两处？合并到更底层的模块（越靠近 `core/` 越好）

---

## 规则 2：类型安全 —— 消灭 `getattr(config, "field", default)`

**模式：** `getattr(config, "field", default)` 是坏味道。说明字段类型是 `Any`，代码在防御字段可能不存在。

**真实案例（2026-05-26）：** `loop.py` 和 `tool_runner.py` 到处用 `getattr(config, "max_retries", 3)`。但 `AgentLoopConfig` 是 dataclass —— 所有字段始终存在。getattr 模式掩盖了拼写错误，也让 config 的实际接口不可见。

**修复：**
1. 在 `AgentLoopConfig` 中添加字段并给默认值
2. 所有地方改用 `config.field` 直接访问
3. 删除 `getattr` 兜底

**检查：** 在 `core/` 中 grep `getattr(config,`。应该为零。

---

## 规则 3：Hook 链式调用 —— Sync/Async 兼容

**模式：** Hook 可以是同步函数（返回 `dict | None`），也可以是异步函数（返回 `Awaitable[dict | None]`）。对同步函数使用 `await` 会崩溃。

**真实案例（2026-05-26）：** `_chain_before_hooks()` 最初直接用 `await hook(call_ctx)`。同步 hook 返回 `None` → `TypeError: object NoneType can't be used in 'await' expression`。

**修复：**
```python
result = hook(call_ctx)
if inspect.isawaitable(result):
    result = await result
```

**检查：** 每个 hook 链方法（`_chain_before_hooks`、`_chain_after_hooks`、`_chain_transform_hooks`）都必须使用 `inspect.isawaitable()`。

---

## 规则 4：Hook 元数据 —— 合并，不覆盖

**模式：** 多个 hook 向 `ToolContext` 注入元数据。如果最后一个 hook 覆盖而非合并，前面的 hook 注入的数据就丢了。

**真实案例（2026-05-22）：** `before_tool_call` 返回的 `inject_metadata` 通过 `update()` 合并进 `ToolContext.metadata`，允许多个 hook 注入不同 key（如 `aigc_auth` + `__tracing_span`）且互不冲突。

**检查：** 元数据注入必须是累加语义（`merged.update(result["inject_metadata"])`），而非替换。

---

## 规则 5：流式重试 —— 缓冲事件，只在最终 attempt 发射

**模式：** 重试 LLM 调用时，每次 attempt 都产生 `MessageStart`/流式 delta/`MessageEnd`。如果全部发射，agent 状态中会有重复消息。

**真实案例（2026-05-26）：** 第一版重试实现在每次 attempt 都 yield `MessageEnd` → `state.messages` 中出现重复 assistant 消息。修复方案是缓冲流中的所有事件，只在最终（成功或重试耗尽）attempt 时才 yield `MessageStart`/delta/`MessageEnd`。

**检查：** 重试循环内部绝对不能 yield 事件。缓冲，然后在循环 break 之后一次性 yield。

---

## 规则 6：Tool 结果 —— 同时同步到 Context 和 State

**模式：** Tool 结果追加到 `context.messages`（每轮临时）。如果不持久化到 `state.messages`，下一轮就消失了。

**真实案例（2026-05-14）：** `ToolResultMessage` 只追加到 `context.messages`，没同步到 `self.state.messages`。第二轮对话中上一轮的 `tool_use` 没有对应的 `tool_result` → Anthropic 拒绝请求 → HTTP 400。

**修复：** `agent.py` 的 `_handle_event` 必须在 `TurnEnd` 时将 `evt.tool_results` 追加到 `self.state.messages`。

**检查：** 每个写 `context.messages` 的地方，都要考虑 `state.messages` 是否也需要同样的数据。

---

## 规则 7：API 迁移 —— 找出所有消费者

**模式：** 从内部字段（`agent._before_tool_call`）迁移到公共方法（`agent.add_before_tool_call_hook()`）时，需要找到所有访问点。测试代码经常直接访问内部字段。

**真实案例（2026-05-26）：** 把 `_before_tool_call` 从单个 callable 改为 list-based hook 链。`test_aigc_creation.py` 直接访问了 `agent._before_tool_call` → 测试挂了。`AgentSession` 用了 `agent._before_tool_call = ...` monkey-patching → 需要改为 `add_*_hook()`。

**检查清单：**
- grep 搜索旧字段/模式名 → 覆盖整个仓库
- 检查 tests/ —— 最容易被漏掉的消费者
- 检查 session/、extensions/ —— 它们组合 Agent
- 检查 scene/ —— 它们构造 Agent 实例

---

## 规则 8：错误处理 —— 先日志，再存储

**模式：** `except Exception: self.state.error_message = str(exc)` 静默吞错。用户看不到任何提示。

**真实案例（2026-05-14）：** Agent 运行失败但终端没有任何提示。修复：存储错误前加上 `logging.getLogger(__name__).exception("Agent run failed")`。

**检查：** `core/` 中的每个 `except Exception` 至少要有 `logger.debug()` 级别的日志。

---

## 规则 9：死代码 —— 同时检查写路径和读路径

**模式：** 一个字段被写入但从未被读取 = 死代码。它会迷惑读者，还可能被人误用。

**真实案例（2026-05-26）：**
- `_primary_transform` 在 `__init__` 中赋值，在 `_chain_transform_hooks` 中作为回退。但 `transform_context` 同时也加入了 `_transform_hooks` 列表。当 hooks 列表为空时 `_primary_transform` 为 None，当非空时它已在列表中。回退路径永远不可达。
- `AgentLoopConfig` 上的 `mutation_queue` 从未被任何消费者设置 —— `getattr(config, "mutation_queue", None)` 永远返回 None。

**检测方法：** 对任意字段，回答两个问题：
1. 在哪里写入？（grep `self._field_name =`）
2. 在哪里读取？（grep `self._field_name`，排除赋值语句）

如果问题 2 只返回写入点，它就是死的。

---

## 规则 10：配置链路 —— 追踪完整链条

**模式：** 构造参数 → Agent 字段 → AgentLoopConfig 字段 → loop 使用。链条上任何一环断了，配置就被静默忽略。

**真实案例（2026-05-26）：** `max_retries` 添加到了 `Agent.__init__` 和 `AgentLoopConfig`，但 loop.py 中有局部变量遮蔽了 config。修复：直接从 config 读取。

**检查：** 新增配置项时，端到端追踪：
```
Agent.__init__(max_retries=3)
  → self._max_retries = max_retries
  → AgentLoopConfig(max_retries=self._max_retries)
  → loop.py: max_retries = config.max_retries
```

---

## 规则 11：模块级 Logger —— 文件顶部定义一次

**模式：** `logging.getLogger(__name__)` 在函数/分支内部重复定义。每次调用创建相同的 logger 对象，浪费且暗示"logger 是局部资源"。

**真实案例（2026-05-27）：** `loop.py` 的 retry 分支和 overflow 分支各写了一次 `_log = logging.getLogger(__name__)`。这两个分支在同一个 while 循环内，logger 应该是一个模块级常量。

**修复：**
```python
# 文件顶部，所有 import 之后
_log = logging.getLogger(__name__)
```

**检查：** grep `logging.getLogger(__name__)` 在 `core/` 中。每个文件里只应出现一次（模块级别）。

---

## 规则 12：Provider 格式转换 —— 属于 providers/，不属于 core/

**模式：** 消息格式转换函数放在 core/ 中的 agent.py 或 loop.py。这些函数知道 OpenAI/Anthropic wire format 细节，是 provider 层的关注点，不应污染核心运行时。

**真实案例（2026-05-27）：**
- `_tools_to_provider_format` 在 `loop.py` 中 → 移至 `providers/base.py`（和 `ModelProvider.stream()` 协议放在一起）
- `_default_convert_to_llm` + `_user_content_to_openai` 在 `agent.py` 中（~60 行）→ 移至 `providers/message_converter.py`

**规则：** 任何包含 provider 特定格式逻辑（`role: "tool"`、`tool_calls` 结构、Anthropic content blocks）的代码，属于 `providers/`。agent/loop 只通过 `ConvertToLlm` callable 调用它，不知道内部细节。

**检查：** grep `"role"` 在 `agent_core/core/` 中。应该只在 `agent_core/core/messages.py`（消息模型定义）和测试中出现。其他文件中的 `"role"` 字符串是泄漏的 provider 格式细节。

---

## 修改后验证

```
□ pytest tests/ —— 全量测试，不只是你改的那个
□ git diff —— 每一行改动都能追溯到任务目标
□ grep 旧模式名 —— 有没有遗漏的消费者？
□ AgentLoopConfig 字段 —— 都被用到了吗？（检查 loop.py、tool_runner.py）
□ 更新 docs/development-log.md（功能缺口/设计债务表）
□ 更新 docs/mistake-log.md（如果是 bug 修复）
```

---

## 规则 13：持久化消息 —— dict 字段必须和 Pydantic 模型对齐

**模式：** `MessageEntry` 保存的 dict 手动构造，和 `ToolResultMessage` 等 Pydantic 模型的必填字段不对齐。`deserialize_message` 校验失败 → `_restore_messages` `except Exception: pass` 静默丢弃消息。用户看到的是"历史消息不完整"，但服务端没有任何错误日志。

**真实案例（2026-06-02）：** `_persist_tool_result` 保存的 dict 缺少 `timestamp` 字段（`ToolResultMessage` 必填），`tool_name` 字段（模型不认识的 extra field，`model_dump` 不输出）。前端加载历史时 tool_result 消息消失，widget 无法重建。

**修复：**
1. `messages.py`: `ToolResultMessage` 新增 `tool_name: str | None = None`，`timestamp: float = Field(default_factory=time.time)`
2. `session.py`: 持久化 dict 写入 `"timestamp": time.time()`

**检查清单：**
- 新增消息持久化时，对照 `AgentMessage` 联合类型的对应模型字段，逐一确认
- dict 的 key 必须在模型中有对应字段（否则序列化时丢失）
- 模型的必填字段必须在 dict 中提供（否则反序列化失败）
- 测试：写入 store → 重启服务 → 加载历史，确认所有消息类型都能还原

---

## 规则 14：缓存键比较 —— 可选参数 None ≠ 不相等

**模式：** `get_or_create` 等缓存方法接收可选参数（`provider_name: str | None = None`）。当参数为 None 时，表示调用方不关心该维度——不应参与缓存匹配的相等比较。把 None 和实际值比较（`None != "minimax"`）会误判"不匹配"，触发不必要的重建。

**真实案例（2026-06-02）：** `/human-input` 端点调用 `manager.get_or_create(session_id)` 未传 provider/model，旧逻辑把 `None` 和 assistant 创建时的 `"minimax"` 比较 → `None != "minimax"` → dispose + 重建 → 正在等待人工输入的 agent loop 被销毁 → `provide_human_input` 永远返回 false。

**修复：** 只有当参数显式传入（非 None）且和当前值不同时，才触发重建。
```python
# 错误
if current_provider != (provider_name or os.environ.get("AGENT_PROVIDER")):
    rebuild()

# 正确
if provider_name is not None and current_provider != provider_name:
    rebuild()
```

**检查：** 缓存方法的比较逻辑中，None 必须视为 wildcard（跳过比较），不能当作一个合法的配置值参与相等判断。

---

## 规则 15：异步长耗时工具 —— 进度上报 + 超时返回状态而非报错

**模式：** 工具执行耗时 >30s（如视频生成轮询），期间 agent loop 阻塞，SSE 无任何事件发送。前端表现为"卡死"。超时后如果返回错误，agent loop 的重试逻辑会触发模型重新调用工具 → 重复创建任务。

**真实案例（2026-06-02）：** `generate_video` 工具轮询最多 600s，期间零反馈。SSE 有 600s timeout。超时后返回 error → 模型看到错误可能重试 → 重复创建视频任务。

**修复：**
1. 轮询期间通过 `ctx.on_update` 定期（如每 15s）上报进度
2. 超时不报错，返回 task_id 和"仍在处理中"状态，让用户后续查询
3. `prompt_guidelines` 明确告知模型：不要重复调用此工具
4. `tool_timeout` 设置为轮询时长 + buffer，不与 SSE timeout 重叠

**检查清单：**
- 异步工具的 `timeout_seconds` < SSE timeout（600s）- 至少留 60s buffer
- 轮询期间有进度上报（`ctx.on_update`）
- 超时返回的是"可继续"的状态（含 task_id），不是错误
- prompt_guidelines 告知模型不要重试
```
