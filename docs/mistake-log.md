# 错题本

> 记录修改时引入的回归问题，防止重复犯错。

---

## 规则 1：修改显示逻辑时，必须区分"数据源"和"显示源"

**发生时间**：2026-05-14

**问题描述**：修复 `<think>` 标签闪现时，导致思考内容丢失、最终答案不输出。

**根因**：
- `displayedText` 是打字机显示用的累计文本（被 `getDisplayableText` 过滤后）
- `currentText` 是原始累计文本（包含 `<think>` 标签）
- `extractThinkSteps()` 原本从 `displayedText` 提取 think 块
- 为了让 think 标签不进打字机队列，引入了 `lastQueuedDisplayable`，只把过滤后的字符 enqueue
- 结果：`displayedText` 不再包含 `<think>` 标签 → `extractThinkSteps()` 搜不到 think 块 → 思考内容丢失
- 更严重：`lastQueuedDisplayable` 和 `displayedText` 的同步逻辑有缺陷，当 think 块跨 delta 时，`displayedText` 中残留了 think 标签的部分字符（如 `<`），导致最终答案被错误截断

**修复过程**：
1. 第一版：将 `extractThinkSteps()` 改为从 `currentText` 提取 → 思考内容恢复了，但...
2. 第二版：移除 `lastQueuedDisplayable` 逻辑，回到原始 `enqueueType(data.text)` → 最终答案恢复输出

**教训**：
- **显示过滤（`getDisplayableText`）只做渲染层过滤，不做数据源过滤**。打字机队列应该接收原始文本，`renderFinalContent` 时再过滤。
- **引入中间状态（如 `lastQueuedDisplayable`）时，必须验证它和所有依赖变量的同步关系**。`displayedText`、`currentText`、`typeQueue`、`lastQueuedDisplayable` 四者之间的同步极其容易出错。
- **修改前先画数据流图**：`currentText`（原始）→ `typeQueue`（原始）→ `displayedText`（原始）→ `getDisplayableText`（过滤）→ DOM。不要在中途插入过滤层。

---

## 规则 2：替换代码块时必须精确匹配边界

**发生时间**：2026-05-14

**问题描述**：回退 `lastQueuedDisplayable` 逻辑时，替换字符串遗漏了闭合 `}`，导致 JS 语法错误。

**根因**：`old_string` 没有包含 `}` 结尾，替换后产生了 `enqueueType(data.text); else if`。

**教训**：
- **替换代码块时，old_string 必须包含完整的语句/块边界**（从 `} else if` 到下一个 `} else if` 的完整内容）。
- **替换后立即运行语法检查**（IDE diagnostics 或 linter），不要依赖手动审查。

---

## 规则 3：修复 A 问题时，必须验证 B/C/D 功能是否仍然正常

**发生时间**：2026-05-14

**问题描述**：
- 修复 think 闪现 → 丢失思考内容（B 功能坏了）
- 修复思考内容丢失 → 最终答案不输出（C 功能坏了）

**根因**：每次修改只验证了当前修复的问题，没有回归验证其他功能。

**教训**：
- **每轮修改后必须完整走一遍测试场景**：
  1. 普通文本对话（无 think、无工具）
  2. 有 think 无工具
  3. 有 think 有工具
  4. 多轮对话（第二轮是否正常）
- **不要在一次对话中连续修复多个问题而不验证**。修好一个，测一个，再修下一个。

---

## 规则 4：不要过度优化边缘问题而引入核心风险

**发生时间**：2026-05-14

**问题描述**：`<think>` 字符在打字过程中短暂闪现（边缘问题），为了消除这个闪现，引入了复杂的 `lastQueuedDisplayable` 同步逻辑，最终破坏了核心功能（最终答案输出）。

**教训**：
- **边缘问题（如字符级闪现）如果不能用简单方案解决，应该暂时接受**。宁可让用户看到 `<` 闪一下，也不能让整段答案消失。
- **复杂方案必须通过"如果出错的代价是什么"来评估**。闪现的代价 = 视觉瑕疵；答案消失的代价 = 功能不可用。

## 规则 8：Pydantic 模型新增字段 → grep 所有构造处 + 测试断言新字段

**发生时间**：2026-06-02, 2026-06-03

**问题描述**：#47 `ToolResultMessage` 新增 `tool_name` 字段，但 `tool_runner.py`（两处）和 `session.py` 构造时漏传。字段有默认值 `None` → 不漏报错 → 运行时值始终为空 → 前端按 `tool_name` 匹配失败。

**同样的问题**：#47 同期，同一模型的 `timestamp` 在 `session.py` 持久化 dict 中缺失，导致 `deserialize_message` 校验失败，消息被静默丢弃。

**教训**：
- 新增字段后，**grep 所有构造处**：`rg "ModelName\(" --include "*.py" -n`
- 字段有默认值 **≠** 不需要显式传入。默认值是兜底，调用方应传入正确值
- 测试必须 **断言新字段的值**，不能只测 `role == "tool_result"`

---

## 规则 9：持久化路径必须用绝对路径，禁止依赖启动时的 cwd

**发生时间**：2026-06-03

**问题描述**：重启服务器后，历史会话全部消失。

**根因**：
- `SessionManager` 的 `session_store_dir` 默认是相对路径 `"./sessions"`
- `server.py` 只传了 `cwd=os.getcwd()`，没显式指定 `session_store_dir`
- 当服务器从 `scene/http_sse/static` 启动时，`"./sessions"` 指向 `static/sessions/`（不存在）
- 之前的历史会话在项目根目录 `sessions/`（200+ 文件），完全找不到
- 同样的问题此前已出现过，当时通过"确保从项目根目录启动"暂时解决，但没有根除

**教训**：
- **任何持久化目录（数据库、文件存储、日志）在初始化时必须解析为绝对路径**，禁止依赖 `os.getcwd()`
- **启动脚本中必须显式传入存储路径**：`session_store_dir=os.path.join(PROJECT_ROOT, "sessions")`
- 不要因为"当前启动方式是对的"就省略绝对路径转换，不同启动方式（`python -m`、IDE runner、systemd、Docker）cwd 各不相同

---

## 规则 10：迭代自定义容器前验证 `__iter__` 返回什么

**发生时间**：2026-06-03

**问题描述**：`for name, tool in tool_registry:` 导致 `ValueError: too many values to unpack`，服务端 SSE 连接崩溃（`ERR_INCOMPLETE_CHUNKED_ENCODING`），前端只看到 "network error"。

**根因**：
- `ToolRegistry.__iter__` 返回 `iter(self._tools)` — dict 的 key 迭代，每次给一个字符串
- `for name, tool in ...` 把字符串（如 `"read"`）解包成单个字符 `'r','e','a','d'`
- 4 个字符解包到 2 个变量 → `ValueError`

**教训**：
- **写 `for a, b in obj` 前先确认 `obj` 的 `__iter__` 返回什么**。dict 迭代 → key；iter(key, value) 需要 `.items()` 或类似方法
- 同样适用于自定义 `__iter__` 的类 — `grep "__iter__"` 确认返回结构
- **不可达的代码路径可能只是你还没触发**。本例中 `enabled_tools` 非 None 才触发，coder persona 恰好有白名单，之前测试可能用的 general（无白名单）绕过了
