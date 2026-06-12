# CLAUDE.md

本文件为 Claude Code 在此仓库中工作提供指引。

## 项目概览

`agent-core` 是一个通用 Python agent 框架，提供流式 LLM 交互、工具执行、会话持久化、上下文压缩和扩展钩子等库级运行时能力。它**不是**一个服务 —— 使用者在它之上构建自己的运行时（FastAPI、CLI、notebook 等）。

本代码库是 `demo/` 中 TypeScript 的 `pi-mono` 架构的 Python 重实现。**`demo/` 是只读的 TypeScript 参考材料——绝不编辑或导入。**

`docs/design.md` 是本代码库的权威设计文档。`docs/development-log.md` 和 `docs/mistake-log.md` 记录最近的决策和过去的陷阱——做重要修改前先查阅，避免重复已解决的错误。

## 开发命令

```bash
# 可编辑安装，含测试依赖
pip install -e ".[test]"

# 运行全部测试
pytest

# 运行单个测试文件
pytest tests/core/test_agent.py

# 运行单个测试
pytest tests/core/test_agent.py::test_prompt_basic

# 详细输出
pytest -v

# 运行特定模块的测试
pytest tests/tools/
```

- 测试使用 `pytest-asyncio`，`asyncio_mode = "auto"`（在 `pyproject.toml` 中配置）。
- `tests/conftest.py` 提供 `FakeProvider`，是 `ModelProvider` 的测试替身，可产出预设的 `StreamEvent` 序列。

## 本地验证

### 启动后端

```bash
# 构建前端（scene/http_sse/static/）
cd scene/http_sse/static && npm run build && cd -

# 启动后端（默认 8001，可通过 PORT 环境变量修改）
PORT=8001 python -m scene.http_sse.server
```

浏览器打开 `http://localhost:8001` 即可交互验证。

**注意：前端是 H5 移动端页面**（`src/main.tsx` 入口加载的是 `src/h5/App.tsx`），不是桌面 Web 页面。在桌面浏览器打开时，UI 会以移动端视口宽度展示。

### 前端开发

```bash
cd scene/http_sse/static && npm run dev   # Vite 开发服务器，默认 http://localhost:5173
```

Vite 开发服务器已配置代理将 `/skills`、`/chat`、`/capabilities` 等 API 请求转发到 `http://localhost:8001`。开发时前端 `npm run dev` + 后端 `python -m scene.http_sse.server` 同时运行。

**H5 / 桌面切换**：`main.tsx` 通过 URL 参数 `?mode=` 控制入口：
- `http://localhost:5173` → 默认 H5 移动端
- `http://localhost:5173?mode=desktop` → 桌面 Web 端（侧边栏布局）
- `http://localhost:5173?mode=h5` → 显式 H5

前端技术栈：
- React 18 + TypeScript + Zustand
- 双入口：`src/h5/App.tsx`（H5 移动端）和 `src/desktop/App.tsx`（桌面 Web 端）
- 组件在 `src/components/` 中 H5/桌面共享
- 纯 CSS，无 UI 框架
- 路由用 Zustand 状态机（`activePage` / `h5ActiveTab`），无 React Router

## 架构

### 包布局

```
agent_core/
├── core/           # 纯运行时 — 无 IO 依赖
│   ├── agent.py    # agent_loop 的状态化包装
│   ├── loop.py     # 核心异步生成器: 流式 LLM → 执行工具 → 循环
│   ├── events.py   # AgentEvent 区分联合类型
│   ├── state.py    # AgentState Pydantic 模型
│   ├── context.py  # AgentContext / AgentLoopConfig 值对象
│   ├── messages.py # UserMessage, AssistantMessage, ToolResultMessage
│   ├── content.py  # TextContent, ImageContent, ToolCallContent
│   ├── tool_runner.py   # 工具执行 (并行 / 顺序)
│   ├── queue.py    # PendingMessageQueue 用于 steering / follow-up
│   └── human_input.py   # HITL (人机对话) 门控
├── providers/      # LLM 提供者适配器
│   ├── base.py     # ModelProvider Protocol
│   ├── message_converter.py  # 默认 OpenAI 格式消息转换
│   ├── registry.py # ModelRegistry: provider → 适配器 + 认证
│   ├── openai_provider.py   # OpenAI / OpenAI 兼容端点
│   ├── anthropic_provider.py
│   └── auth.py     # AuthSource (静态 / 环境变量 / 动态)
├── tools/          # 工具抽象及内置工具
│   ├── base.py     # Tool Protocol, ToolResult, ToolDefinition, ToolRegistry, ToolContext
│   ├── http_tool.py
│   ├── operations.py        # FileOperations / BashOperations Protocols (注入用于沙箱)
│   ├── operations_local.py  # 上述 Protocol 的本地实现
│   ├── mutation_queue.py    # FileMutationQueue: 按路径 asyncio.Lock 用于写入/编辑
│   ├── render.py            # ToolRenderer Protocol + RenderedOutput
│   ├── truncate.py          # 文本截断工具 (head/tail/lines/bytes)
│   ├── music.py             # TextToMusicTool — 示例长时间运行工具
│   └── local/               # 文件系统工具: read, write, edit, ls, find, grep, bash, confirm
├── session/        # 会话持久化
│   ├── store.py    # SessionStore Protocol + SessionEntry 类型
│   ├── session.py  # AgentSession: 组合 Agent + Store + Extensions
│   ├── jsonl_store.py
│   └── inmemory_store.py
├── compaction/     # 上下文窗口压缩
│   ├── compactor.py
│   └── strategies.py
├── extensions/     # 扩展/钩子系统
│   └── base.py     # Extension Protocol + ExtensionRunner
├── resources/      # 资源加载 (skills, prompts, themes, context files)
│   ├── loader.py        # ResourceLoader 入口
│   ├── skills.py        # Skill 发现 (~/.pi/agent/skills/, ./.pi/skills/)
│   ├── prompts.py       # 提示词模板加载
│   ├── context_files.py # AGENTS.md / CLAUDE.md / etc. 解析
│   ├── themes.py        # 终端主题资源
│   ├── extensions.py    # Extension manifest 加载
│   ├── diagnostics.py   # 资源验证/报告
│   └── types.py
├── skills/         # 占位包 — 内置 skill 存放于此
├── prompts/        # 系统提示词构建
│   └── builder.py  # SystemPromptBuilder
└── logging_config.py    # 日志配置辅助函数供宿主使用
```

### 关键架构决策

**异步优先。** 所有公共 API 是协程或异步生成器。核心循环 (`agent_core/core/loop.py`) 是纯异步生成器，产出 `AgentEvent` 对象。`Agent` (`agent_core/core/agent.py`) 是围绕它的薄状态化包装。

**分层单向依赖。** `core` 无 IO 依赖。`session` 依赖 `core`。`extensions` 依赖 `core` 并接入 `session`。绝不在层间引入循环依赖。

**事件驱动流。** agent 循环产出 `AgentEvent` 区分联合类型 (`agent_core/core/events.py`)。消费者通过 `Agent.subscribe(listener)` 订阅。监听器可为同步或异步 — 框架两者都处理。

**消息队列。** `Agent` 维护两个 `PendingMessageQueue` 实例：
- `steering` — 运行中注入的消息（如用户中断）
- `follow_up` — 运行完成后排队的消息
每个队列支持 `"one-at-a-time"`（默认）和 `"all"` 两种模式。

**工具执行模式。** `AgentLoopConfig.tool_execution` 控制一个 turn 内的多个工具调用是 `"parallel"`（默认，通过 `asyncio.gather`）还是 `"sequential"`（逐个执行，含中间 `ToolExecutionUpdate` 事件）。

**人机对话。** 工具可抛出 `RequiresHumanInput` (`agent_core/core/human_input.py`) 暂停执行并发出 `HumanInputRequired` 事件。当 `Agent.provide_human_input()` 以匹配的 `tool_call_id` 被调用时，工具恢复执行。

**提供者抽象。** `ModelProvider` 是一个 Protocol (`agent_core/providers/base.py`)。所有提供者产出统一的 `StreamEvent` 流。`ModelRegistry` 将提供者名称映射到适配器实例，并通过 `AuthSource` 解析认证。

**会话持久化。** `AgentSession` (`agent_core/session/session.py`) 组合 `Agent` + `SessionStore` + 可选的 `Compactor` + `Extension`。它将每个 `MessageEnd` 事件持久化为 `MessageEntry`，并在上下文达到阈值时自动触发压缩。

**系统提示词构建。** `SystemPromptBuilder` (`agent_core/prompts/builder.py`) 从基础提示词、活跃工具、指南、上下文文件和 skills 动态组装系统提示词。Skills 从 `~/.pi/agent/skills/` 和 `./.pi/skills/` 中发现。

### Scene 层

`scene/` 目录包含基于 `agent_core` 构建的可运行应用：

- `scene/cli/` — 交互式终端聊天 (`python -m scene.cli.cli`)
- `scene/http_sse/` — FastAPI 服务器，SSE 流式传输 (`python -m scene.http_sse.server`)
- `scene/voice_ws/` — WebSocket 语音聊天服务器

`scene/cli/chat_assistant.py` 和 `scene/http_sse/chat_assistant.py` 是高级 `ChatAssistant` 包装器，负责组装 provider、工具、skills 和会话存储。

## 测试模式

- 使用 `tests/conftest.py` 中的 `FakeProvider` 来脚本化提供者行为，无需网络调用。
- `FakeProvider.queue_script([...])` 排入一个 `StreamEvent` 对象序列；每次调用 `stream` 按顺序消耗一个脚本。
- agent 循环的测试通常订阅事件、调用 `agent.prompt()`，然后对捕获的事件做断言。

## 可选依赖

框架使用 extras 标记可选集成：

- `[mongo]` — `motor` for MongoDB session store
- `[mcp]` — `mcp` SDK for MCP tool servers
- `[openai]` — `openai` SDK
- `[anthropic]` — `anthropic` SDK
- `[test]` — `pytest`, `pytest-asyncio`, `respx`
- `[all]` — 以上全部

## 编码规范

**权衡：** 这些规范偏向谨慎优先于速度。对于简单任务，自行判断。

### 1. 先思考再编码

**不要假设。不要隐藏困惑。暴露权衡。**

在实现之前：
- 明确陈述你的假设。不确定就问。
- 如果有多种理解方式，都列出来 — 不要默默选一个。
- 如果有更简单的做法，说出来。需要时提出异议。
- 如果有不清楚的地方，停下来。说清楚困惑所在。问。

### 2. 简单优先

**用最少代码解决问题。不写投机代码。**

- 不写没被要求的功能。
- 不为单次使用的代码添加抽象。
- 不被要求的"灵活性"或"可配置性"不写。
- 不为不可能发生的场景添加错误处理。
- 如果写了 200 行但 50 行就够了，重写。

问自己："一个高级工程师会说这里过度设计吗？"如果是，简化。

### 3. 精准变更

**只改必须改的。只清理自己造成的混乱。**

在编辑现有代码时：
- 不"改进"相邻的代码、注释或格式。
- 不重构没坏的东西。
- 匹配现有风格，即使跟你的方式不同。
- 如果注意到无关的死代码，提出来 — 不直接删。
- 严格把控测试用例质量。不得为跑通测试而修改或伪造测试用例。测试失败应追溯到代码实现的问题，而非调整测试来迎合代码。

当你的修改产生孤儿代码时：
- 删除由你修改导致不再使用的导入/变量/函数。
- 不删除原本就存在的死代码，除非被明确要求。

检验标准：每行变更都应可追溯到用户的请求。

### 4. 目标驱动执行

**定义成功标准。循环直至验证通过。**

把任务转化为可验证的目标：
- "加上校验" → "为非法输入写测试，然后让测试通过"
- "修 bug" → "写一个可复现的测试，然后让测试通过"
- "重构 X" → "确保重构前后测试均通过"

多步骤任务先陈述简要计划：
```
1. [步骤] → 验证: [检查项]
2. [步骤] → 验证: [检查项]
3. [步骤] → 验证: [检查项]
```

强成功标准让你可以独立迭代。弱标准（"让它跑通"）需要持续澄清。

## 开发流程 Skill

在 `.claude/skills/` 下有 4 个开发优化 skill，触发条件:

| 用户关键词 | 加载 Skill |
|-----------|-----------|
| "优化" / "设计有没有问题" / "审查" 且涉及前后端 | `dev-process-optimizer` (跨层) |
| 同上，但纯后端 | `dev-backend-optimizer` |
| 同上，但纯前端桌面 | `dev-frontend-optimizer` |
| 同上，但涉及 H5 移动端（`src/h5/`） | `dev-process-h5` |
| 单文件修 bug / 改文案 | 不加载 |

处理完成后: 真正新发现的反模式按附录模板追加到对应 skill 末尾。现有规则已覆盖的不追加。

## 提交前检查

**每次提交前按顺序完成三步**，不跳过:

1. **更新 changelog** — 在 `docs/development-log/YYYY-MM-DD.md` 记录变更摘要（文件、类型、关联规则）
2. **检查 skill 是否需要更新** — 对照变更模式与已有规则，现有规则已覆盖则不追加
3. **提交** — 按 Conventional Commits 格式写 commit message

此规则对所有提交生效。兜底: 说"收尾"或 `/finish` 手动触发同流程。
