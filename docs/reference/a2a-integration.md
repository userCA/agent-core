# 远端 Agent 接入（标准 A2A 协议）— v1

第一版实现：把远端 A2A agent 以 **Agent-as-Tool** 的方式接入 `agent_core`，与本地
sub-agent（`delegate_task`）共用同一套编排事件流。

## 新增模块

| 文件 | 作用 |
|---|---|
| `agent_core/tools/a2a_client.py` | A2A 传输层：Agent Card 发现、`message/send`、`tasks/get`、`tasks/cancel`、`tasks/resubscribe`(SSE) |
| `agent_core/tools/a2a_tool.py` | 一个远端 agent = 一个 `Tool`；含配置解析与 `register_a2a_tools` |
| `agent_core/multi_agent/types.py` | `AgentProfile` 新增 `transport/endpoint/auth_token_env/timeout_seconds` |
| `agent_core/multi_agent/sub_agent_runner.py` | `run_single` 按 `transport` 分发：`local` 走本地 harness，`a2a` 走 A2A 客户端 |

## 协议映射

| A2A 对象 | agent_core 对象 |
|---|---|
| Agent Card（`/.well-known/agent-card.json`） | `A2AAgentCard` / `ToolDefinition` |
| `message/send` + `tasks/get` 轮询 | `A2AAgentTool.execute()` |
| Task 状态机（working/completed/failed/canceled/input-required） | `ToolResult.details["delegation"]["status"]` |
| `tasks/cancel` | `ToolContext.signal`（abort） |
| Message / Artifact 文本 | `ToolResult.content` + `details["task"]` |
| 状态增量 | `ToolContext.on_update`（`delegation/remote_task_update` 事件） |

## 配置

解析链（`load_a2a_agent_configs`）：

1. `<cwd>/.pi/a2a/agents.json`
2. `<cwd>/.a2a.json`
3. 环境变量 `A2A_AGENTS`（JSON 列表，或兼容格式 `name:url[:token_env[:timeout]]`）

```json
// .pi/a2a/agents.json
{
  "agents": [
    {"name": "research_agent", "url": "https://a2a.example.com", "token_env": "RESEARCH_AGENT_TOKEN", "timeout_seconds": 120}
  ]
}
```

## 用法

### 1. 作为独立工具注册（与 MCP 类似）

```python
from agent_core.tools import ToolRegistry, register_a2a_tools

registry = ToolRegistry()
count = register_a2a_tools(registry)          # 读配置，每个 agent 注册一个 Tool
tool = registry.get("research_agent")
```

### 2. 接入多 agent 编排（推荐）

远端 agent 与本地 sub-agent 对编排器完全透明，`delegate_task` 的
single/parallel/chain 均可用：

```python
from agent_core.multi_agent import AgentProfile, MultiAgentHarnessOptions, create_multi_agent_harness

options = MultiAgentHarnessOptions(
    profiles=[
        AgentProfile(
            name="research_agent",
            description="负责资料检索与调研的远端 agent",
            system_prompt="(remote)",
            transport="a2a",
            endpoint="https://a2a.example.com",
            auth_token_env="RESEARCH_AGENT_TOKEN",
            timeout_seconds=120,
        ),
        # 本地 sub-agent 不变，transport 默认 "local"
    ],
)
```

## 行为说明（v1）

- 一次工具调用 = 一个 A2A Task：`message/send` 创建，随后轮询 `tasks/get`
  直到终态（completed/failed/canceled/rejected），超时抛 `A2AError`。
- `input-required` 会停止轮询并以 `input_required` 状态返回（v1 不做多轮续聊）。
- `ToolContext.signal` 被置位时发送 `tasks/cancel`，结果状态为 `aborted`。
- `tasks/resubscribe` SSE 订阅已实现（`A2AClient.subscribe`），v1 的
  `run_task` 默认走轮询，后续可切换为订阅模式。
- 配置中 URL 含端口时请使用 JSON 配置格式（兼容格式对 `:8080` 这类结尾有歧义）。
- 远端 agent 必须静态配置（白名单），不要在 prompt 里传 URL，避免 SSRF。
