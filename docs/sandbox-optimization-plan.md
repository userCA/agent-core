# 沙箱服务接入 — 优化方案

> 对照 pi-mono bash 工具与 Kimi 沙箱设计，当前项目 bash/文件工具的差距分析与优化方案。
> **状态：已实施 (2026-06-02)**，以下为实施后的最终架构。

---

## 实施总结

### 已完成的变更 (6 改 3 新增，9 个文件)

| 文件 | 操作 | 内容 |
|------|------|------|
| `agent_core/tools/operations.py` | **改** | `BashOperations.execute()` 增加 `on_data`/`signal` 参数；`BashResult` 增加 `full_output_path`/`truncation_info`；新增 `SandboxQuota`/`SandboxBackend` |
| `agent_core/tools/operations_local.py` | **改** | `LocalBashOperations.execute()` 支持 `on_data` 流式回调 + `signal` 取消 + 进程树杀灭 + 超时保留部分输出 + `start_new_session=True` |
| `agent_core/tools/local/bash.py` | **改** | 传入 `on_data`/`signal` 到 backend + `truncate_head` 截断 + `commandPrefix`/`spawnHook` + 超大输出写临时文件 |
| `agent_core/tools/local/__init__.py` | **改** | `create_all_tools`/`create_coding_tools`/`create_read_only_tools` 增加 `file_ops`/`bash_ops` 参数 |
| `agent_core/tools/__init__.py` | **改** | 新增 `SandboxBackend`/`SandboxQuota` 导出 |
| `agent_core/tools/sandbox_docker.py` | **新** | `DockerSandboxBackend` — 同时实现 `SandboxBackend` + `FileOperations` + `BashOperations`，含路径三区模型和配额落实 |
| `agent_core/tools/sandbox_policy.py` | **新** | `SandboxPolicyExtension` — 配额分配 + 危险命令拦截（`on_before_tool_call` hook） |
| `agent_core/tools/sandbox_healing.py` | **新** | `SelfHealingExtension` — 即时修复（pip install）+ 增强错误提示（`on_after_tool_call` hook） |
| `tests/tools/local/test_bash.py` | **改** | `FakeBashOps` 适配新参数 `on_data`/`signal` |

### 未改动

`core/loop.py`、`core/agent.py`、`core/events.py`、`base.py`、`tool_runner.py`、所有 provider、session **零改动**。

### 实施中修正的问题

1. **去掉 `ToolContext.sandbox_backend`** — 工具在构造时绑定后端，不需要运行时通过 context 切换。后端路由在组装工具时决定。
2. **去掉 `tool_runner.py` 改动** — 自愈策略改为两阶段：即时修复（`pip install`）通过 `on_after_tool_call` 注入增强错误信息；LLM 在下一轮自然重试。不阻塞 tool_runner。
3. **`truncate_head` 而非 `truncate_tail`** — 当前 `truncate.py` 中 `truncate_head` 保留末尾，`truncate_tail` 保留开头。bash 输出需要末尾（最新内容）。
4. **进程树杀灭平台适配** — Linux 用 `os.kill(-pid, SIGKILL)`（杀进程组），macOS 用 `pkill -P` + `kill`。
5. **`start_new_session=True`** — `create_subprocess_shell` 启用新会话，使进程组隔离生效。
6. **signal + timeout 同时存在时的超时处理** — `asyncio.wait` 增加 `timeout` 参数并在无任务完成时抛出 `TimeoutError`。

---

## 一、当前状态 (实施前)

### 1.1 已有优势（无需改动）

- `FileOperations` / `BashOperations` Protocol 接口已预留 "Allows local, SSH, or container backends"
- 每个工具构造函数接受 `file_ops` / `bash_ops` 参数，可通过依赖注入切换后端
- `ToolContext` 已有 `on_update` 回调、`signal` 取消事件、`metadata` 字典
- `tool_runner.py` 的 `ToolExecutionUpdate` 流式事件机制已就绪
- `Extension` 的 `on_before_tool_call` / `on_after_tool_call` 可用于策略与自愈
- `truncate.py` 已有基础截断函数

### 1.2 关键差距 (已全部解决)

| # | 差距 | 解决方式 |
|---|------|---------|
| 1 | Bash 流式输出 | `BashOperations.execute()` 增加 `on_data`；`LocalBashOperations` 逐块回调 |
| 2 | AbortSignal 传递 | `execute()` 增加 `signal` 参数，bash tool 传入 `ctx.signal` |
| 3 | 进程树杀灭 | `_kill_process_tree()` 平台适配 + `start_new_session=True` |
| 4 | 输出截断 + 临时文件 | BashTool 集成 `truncate_head` + tempfile |
| 5 | 超时后部分输出 | `LocalBashOperations` 超时后返回已捕获的 partial_stdout |
| 6 | `commandPrefix` | BashTool `__init__` 支持 `command_prefix` 参数 |
| 7 | `spawnHook` | BashTool `__init__` 支持 `spawn_hook` 参数 |

---

## 二 ~ 六 (实施细节见上方"实施总结")

---

## 组装示例

```python
from agent_core.tools.sandbox_docker import DockerSandboxBackend
from agent_core.tools.sandbox_policy import SandboxPolicyExtension
from agent_core.tools.sandbox_healing import SelfHealingExtension
from agent_core.tools.local import create_all_tools
from agent_core.tools.operations import SandboxQuota

# 沙箱后端
docker_be = DockerSandboxBackend(
    image="python:3.11-slim",
    quota=SandboxQuota(cpu_cores=1.0, memory_mb=1024, timeout_seconds=120),
)
await docker_be.start()

# 工具注入沙箱后端
tools = create_all_tools(
    file_ops=docker_be,
    bash_ops=docker_be,
)

# 策略 + 自愈扩展
policy = SandboxPolicyExtension()
healing = SelfHealingExtension(bash_ops=docker_be)

# 组装 Agent（其他 provider/store 等省略）
agent = Agent(
    tool_registry=registry,  # 包含上述工具
    extensions=[policy, healing],
)
```
