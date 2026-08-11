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

**修复（2026-06-02 更新）：**
1. 不要在 `execute` 内长时间轮询。改为快查（≤30s），完成则返回结果，否则返回 task_id
2. 额外提供独立的 `check_xxx_status` 工具让用户查询进度
3. `prompt_guidelines` 明确告知模型：只调用一次，不重试
4. 超时/未完成返回的是"可继续"的状态（含 task_id），不是错误

**检查清单：**
- 异步工具 `execute` 耗时 ≤30s（快查窗口）
- 提供独立的 `check_xxx_status` 工具用于查询进度
- 两个工具输出格式一致，前端可统一解析
- prompt_guidelines 告知模型不要重试
```

---

## 规则 17：Pydantic 模型新增字段 —— 所有构造处 + 测试断言同步更新

**模式：** 在 Pydantic 模型上新增了字段，但忘记了更新所有 `Model(...)` 构造调用处。构造处因为字段有默认值不会报错 → 该字段在生产环境中始终为空。

**真实案例（2026-06-03）：** `ToolResultMessage` 新增了 `tool_name: str | None = None`（#47），但 `tool_runner.py` 两处 `ToolResultMessage(...)` 构造没传 `tool_name`。SSE 实时流通过 `ToolExecutionEnd.tool_name` 正常，但 `/session` API 返回 `"tool_name": null` → 前端 history 加载时无法匹配工具块 → 视频不渲染（#70）。

**类似的案例（2026-06-02）：** 同一模型 `ToolResultMessage` 在 `session.py` 中持久化时缺少 `timestamp` 字段 → 反序列化校验失败 → 消息被静默丢弃（#47）。

**规则：**
1. 新增模型字段后，**grep 所有构造该模型的代码位置**，逐一确认是否需要填入新字段
2. 如果字段有默认值但实际场景中应该被填充 → 不改默认值，而是在所有构造处显式传入
3. 测试不仅要测"能构造"，还要**断言新字段的值**——只测 `msg.role == "tool_result"` 不够，必须 `assert msg.tool_name == expected`

**检查清单：**
- `rg "ModelName\(" --include "*.py" -n` 列出所有构造处
- 每个构造处：新字段是否需要显式传入？（有默认值 ≠ 不需要传）
- 每个构造处：对应的测试是否断言了新字段？
- 序列化测试：`model_dump(mode="json")` 后新字段是否出现在 dict 中？
```

---

## 规则 16：集成第三方 API —— 先本地验证响应字段

**模式：** 根据 API 文档写代码，但实际响应字段名和文档不一致。轮询等待 `video_url` 字段但 API 返回的是 `remixed_from_video_id` → 永远匹配不到。

**真实案例（2026-06-02）：** Agnes Video API 文档写返回 `video_url`，实际响应中是 `remixed_from_video_id`。工具轮询到 status=completed 但 `video_url` 为空 → 返回"未返回视频URL"。

**规则：** 集成新的第三方 API 前，先写一个最小的 curl/Python 脚本测试实际响应格式，确认字段名后再写正式代码。

**检查：**
- 新增 API 集成 → 先跑一遍本地测试脚本
- 验证所有需要读取的字段在实际响应中存在且格式正确
- 测试脚本提交到 `tests/` 或保存为注释供后续参考
```

---

## 规则 18：全局懒初始化 —— async 环境下必须加锁

**模式：** 模块级全局变量懒初始化（`_MODEL = None; if _MODEL is None: _MODEL = expensive_init()`）在 async 环境下可被多个协程并发访问。未加锁 → 双线程/双协程同时命中 `is None` → 重复初始化 → 资源泄漏或状态不一致。

**真实案例（2026-06-03）：** `knowledge/local_kb.py` 中 `_get_model()` 使用 `global _MODEL` + 无锁 laz y init。`add()` 和 `retrieve()` 可从不同 asyncio task 并发调用，双线程同时命中 `_MODEL is None` → `SentenceTransformer` 初始化两次。

**修复：**
```python
# 错误
_MODEL = None

def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = expensive_init()
    return _MODEL

# 正确
_MODEL = None
_MODEL_LOCK = threading.Lock()

def _get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:  # 双重检查
                _MODEL = expensive_init()
    return _MODEL
```

**检查：** grep `global` + `is None` 模式在 `agent_core/` 中——每个都需要加锁或改为单线程保证。

---

## 规则 19：Python 实现 JS 位运算 → 每步掩码 32-bit

**模式：** JavaScript 的位运算隐式做 32-bit 整数截断（`>>> 0`、`Math.imul`）。Python 的整数是无限精度的，同样的 `*` / `^` / `>>` 不会溢出，也不会截断。

**真实案例（2026-06-05）：** `companion/bones.py` 中实现 mulberry32 PRNG。Python 版 `t = (a ^ (a >> 15)) * (1 | a)` 的 `t` 远超 32-bit → 后续 `t ^ (t >> 7)` 产生巨大整数 → `int(rng() * len(arr))` 的 `rng()` 返回远大于 1 的值 → `IndexError`。

**修复：** 每个乘法/异或/加法后加 `& 0xFFFFFFFF`：
```python
# 错误
t = (a ^ (a >> 15)) * (1 | a)

# 正确
t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
```

**检查：** 任何从 JS 移植到 Python 的算法，检查是否依赖 32-bit 隐式截断。

---

## 规则 20：Library 层不可 import Extension 层

**模式：** `agent_core/companion/` 是领域库（library），`agent_core/extensions/` 是消费者（extension）。library 不应 import extension 中的类型——会导致循环依赖。

**真实案例（2026-06-05）：** `companion/guide.py` 导入了 `extensions/companion.py` 的 `CompanionBubble`。但 `extensions/companion.py` 也导入了 `companion/` 的其他模块 → 循环依赖风险。

**修复：** 共享类型下沉到 library 内的 `types.py`，两边都从 library 导入：
```
companion/types.py  ←  extensions/companion.py  (import CompanionBubble)
                    ←  companion/guide.py        (import CompanionBubble)
```

**检查：** 
- `agent_core/companion/` 中的任何文件不应 import `agent_core/extensions/` 
- 发现 → 共享类型下沉到 `companion/types.py`

---

## 规则 21：Scene 层不创建 Library 的内部依赖

**模式：** Scene 层（`chat_assistant.py`）创建 library 的内部依赖实例（如 `InMemoryMemoryStore`），然后注入给 library 的类。这暴露了 library 的实现细节给上层。

**真实案例（2026-06-05）：** `chat_assistant.py` 创建 `InMemoryMemoryStore()` 注入 `CompanionExtension`。chat_assistant 不应该知道 companion 用什么存储。

**修复：** Library 类内置默认实现，上层只需决定"是否用"而非"怎么用"：
```python
# 错误 — scene 层知道 companion 用 InMemoryMemoryStore
companion_mem = InMemoryMemoryStore()
extensions.append(CompanionExtension(uid, callback, memory_store=companion_mem))

# 正确 — scene 层只传 callback，companion 自己创建默认存储
extensions.append(CompanionExtension(uid, callback))
```

**检查：** Scene 层中不应出现 library 内部依赖的 import（`InMemoryMemoryStore`、`CompanionMemory` 等）。

---

## 规则 22：传输格式转换放 domain 扩展模块，不放 HTTP handler

**模式：** HTTP handler（`server.py`）内实现 domain 类型的格式转换函数。格式逻辑和路由逻辑混在一起。

**真实案例（2026-06-05）：** `server.py` 中有 `_companion_event_to_sse()` 函数，处理 `CompanionEvent` / `CompanionBubbleEvent` → SSE dict 的转换。server.py 变成两件事的杂乱混合：路由 + 格式。

**修复：** 格式转换函数放在 domain 扩展模块（`extensions/companion.py` 的 `companion_event_to_sse()`），server.py 只 import 并调用：
```python
# server.py — 只做路由，不定义格式
from agent_core.extensions.companion import companion_event_to_sse
yield _format_sse(companion_event_to_sse(cevt))
```

**检查：** `server.py` 中不应有 "从 domain 对象到 SSE dict" 的转换函数体。应该 import 并调用。
```

---

## 规则 23：有生命周期状态的 Extension 必须注册后台衰减任务

**模式：** Extension 持有随时间变化的状态（如情绪 FSM），但状态衰减/清理只在 `on_event()` 回调中触发。用户长时间不操作时无事件产生 → 状态永远不衰减。

**真实案例（2026-06-05）：** CompanionExtension 的 EmotionFSM.check_decay() 仅在 TurnEnd 时调用。发消息后猫 HAPPY，之后无人互动 → HAPPY 永远不衰减到 NEUTRAL。修复：on_before_agent_start 中用 `asyncio.ensure_future()` 启动后台 loop，每 10s 检查 idle 时间并触发衰减推送；AgentEnd 时取消任务。

**规则：**
1. Extension 中有随时间衰减/变化的状态 → 必须注册后台 asyncio task
2. 后台任务在 `on_before_agent_start` 中启动，在 AgentEnd 时取消
3. 后台任务 sleep interval 应适中（5-15s）
4. 只在状态实际变化时才推送更新，避免无效 SSE 流量

---

## 规则 24：库模块需要 LLM 调用时走 ModelProvider，不直接 import SDK

**模式：** `agent_core/` 内的模块直接 `import openai` / `import anthropic`，创建独立的 client 实例。绕过 agent_core 的 ModelProvider + AuthSource 体系 → 认证配置不一致 → 相同的 API key 环境变量在两处独立维护。

**真实案例（2026-06-05）：** `companion/naming.py` 用 `openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` 直接调 LLM 命名。server.py 的 hatch endpoint 又独立创建 `OpenAIProvider + AuthSource` 注入。认证逻辑散落在两处。

**修复：** naming 模块改为接受注入的 ModelProvider + AuthSource，通过 `provider.stream()` 调用。server 启动时一次性注入 `configure_naming(provider, auth)`，模块内部不 import openai。

**规则：**
1. `agent_core/` 内任何需要 LLM 调用的模块 → 接受注入的 ModelProvider，不直接 import SDK
2. Provider 的创建和认证在 scene 层/lifespan 中完成，注入到库模块
3. 库模块只通过 `provider.stream()` / `provider.list_models()` 等协议方法访问

---

## 规则 25：Adapter 不静默吞异常 —— 让调用方决定

**模式：** Adapter/外部服务调用层用 `except Exception: logger.warning(...)` 包裹所有操作。调用方不知道操作失败，继续执行 → 数据丢失或功能静默失效。

**真实案例（2026-06-10）：**
- `OpenVikingMemoryStore.remember()` 用 `try/except: logger.warning` 包裹 → 写入失败时 `MemoryExtension` 不知 → 整轮对话的记忆丢失
- `Mem0MemoryStore.remember()` / `recall()` / `forget()` 同样模式
- `forget()` 的 `PermissionDeniedError` 被吞掉 → 调用方以为 session 已删除
- 修复：移除所有 `try/except`，异常直接传播。`MemoryExtension` 层统一处理（记录日志 + 回退）

**规则：**
1. Adapter 层不吞异常 —— 异常直接抛出给调用方
2. 调用方（Extension/Scene）决定如何处理：日志、回退、重试
3. `except Exception: logger.warning()` 只有在显式回退策略时才能用（如 `recall` 失败 → 返回空 `[]` 作为"无记忆"的语义），且必须在文档中说明回退行为
4. 同一 Protocol 的所有 adapter 实现必须保持相同的错误传播语义

**检查：** grep `except Exception:` 在 `adapters/` 中。每个出现处必须有明确的回退语义说明。

---

## 规则 26：Rule ID 多格式兼容 —— 统一用 `_extract_rule_number` helper

**模式：** 代码中规则 ID 有两种格式并存——英文 `rule_14` 和中文 `规则 14`。直接对 ID 字符串做 `split('_')[1]` 在中文格式下 IndexError。

**真实案例（2026-06-11）：** `validation.py:231` 的 `_apply_proposal` modify 路径用 `target_rule.split('_')[1]` 提取规则编号。当 `target_rule="规则 14"` 时，`split('_')` 返回 `["规则 14"]`，`[1]` 越界。修复：抽取 `_extract_rule_number` 方法，统一处理两种格式。

**规则：**
1. 涉及 rule ID 的解析/反引用操作，始终使用共享 helper 函数，不得手动 split
2. Helper 必须同时处理 `rule_N` → `N` 和 `规则 N` → `N` 两种输入
3. 新增 ID 格式时只改 helper，不改调用方

---

## 规则 27：布尔三态参数 —— `None` ≠ `False`

**模式：** 可选 Boolean 参数（`was_helpful: bool | None = None`）有三态：`True`（明确是）、`False`（明确否）、`None`（未指定）。用 `ExecutionOutcome.SUCCESS if was_helpful else ExecutionOutcome.FAILURE` 会把 `None` 错误归入 `False` 分支。

**真实案例（2026-06-11）：** `collector.py:228` 的 `record_user_feedback`——`was_helpful=None` 时 trace 被标记 FAILURE，污染分析数据。修复：显式判断 `is True` / `is False` / else 用 PARTIAL。

**规则：**
1. Boolean 可选参数必须三路判断：`if x is True:` / `elif x is False:` / `else:`
2. 禁止 `if x:` 隐含 fallthrough——它会把 `None` 当 `False`

---

## 规则 28：Event 字段验证 —— 以 `events.py` 实际类定义为准，不以测试 mock 为准

**模式：** 测试文件中 `FakeTurnEnd` 等 mock 可能定义了实际类不存在的字段（如 `state`）。在业务代码中访问 `evt.state` 时，`TurnEnd` 实际只有 `message` + `tool_results`，不存在 `.state` → AttributeError 或在 Pydantic 模型上静默返回 `None`。

**真实案例（2026-06-11）：** `collector.py:134` 的 `on_turn_end` 访问 `evt.state.error_message`——`TurnEnd` 实际定义在 `agent_core/core/events.py:50` 只有 `message` + `tool_results`。该地址在测试 mock `FakeTurnEnd` 中碰巧存在，测试通过但生产环境永远无法触发真实逻辑。

**规则：**
1. 访问 Event 字段前，打开 `agent_core/core/events.py` 确认类的实际字段定义
2. 测试 mock 必须尽量贴近真实类——不能随意添加真实类不存在的字段
3. 如果测试需要额外字段，审查这是否意味着真实类缺了字段（应补到 events.py），而非仅加到 mock

---

## 规则 29：复合分数比较 —— 分子分母同公式

**模式：** 比较两个加权分数时，如果分子用的是复合公式（如 `confidence * len(source_traces)`），分母也必须用同公式计算的总分，不能混用裸原始值。

**真实案例（2026-06-11）：** `agent.py:390` 的 `_resolve_conflicts`——`score = p.confidence * len(p.source_traces)` 是复合分，但阈值比较用的是 `score / best.confidence < 0.5`，分母是裸 confidence。正确应为 `score / best_score`。导致 confidence=0.5、1 条 trace 的 proposal 被错误认为与 confidence=0.9、3 条 trace 的"足够接近"（0.56 vs 正确的 0.19）。

**规则：**
1. 使用复合/加权分数时，所有比较运算中的分母必须用同一公式
2. 变量命名区分裸值和复合值（`confidence` vs `score`），降低混用风险

---

## 规则 30：Tracing hook —— before/after 不能共享 call_ctx 引用

**模式：** `tool_runner` 对 before-hook 和 after-hook 传入**不同的 dict**。在 before-hook 里写入 `call_ctx["__tracing"]` 后，after-hook 读不到，span 永不 `end()`，OTEL/Langfuse 工具链 Trace 树残缺或泄漏。

**真实案例（2026-08-11）：** `observe()` 的 `_make_tracing_before_hook` 把 span 存在 before 的 `call_ctx`；`_make_tracing_after_hook` 在新 dict 上取 `__tracing` 恒为 `None`。修复：模块级 `_pending_tool_spans`，key 为 `{run_id}:{tool_call_id}`；after-hook 按 `tool_call.id` pop 并 end；`observe()` finally 清理孤儿 span。

**规则：**
1. 跨 before/after 传递 tracing 状态时，**禁止**假设同一 `call_ctx` 对象
2. 用稳定业务 key（`run_id` + `tool_call.id`）关联 span
3. run 结束时清理未 pop 的 pending span（并行 tool 时 key 必须含 run_id）

---

## 规则 31：Hook 注册必须可撤销 —— `remove_*` 不能是 no-op

**模式：** context manager（如 `observe()`）在 `finally` 里调用 `remove_before_tool_call_hook`，若 remove 是空实现，每次 user turn 都会 `add` 新 hook 而不移除，导致重复 span / 重复副作用。

**真实案例（2026-08-11）：** `harness_config.remove_before_tool_call_hook` / `remove_after_tool_call_hook` 原为 `pass`。`register_legacy_tool_call` 未返回 `hooks.on()` 的 unsubscribe。修复：register 返回 unsub；add 时存 `id(hook) → unsub`；remove 时 pop 并调用。

**规则：**
1. 凡 `add_*_hook` 必须有对称且有效的 `remove_*_hook`
2. `register_legacy_*` 必须返回 `AgentHooks.on()` 的 unsubscribe callable
3. 写 context manager 包 hook 时，用测试断言：注册两次 remove 一次后 handler 数量不增长
