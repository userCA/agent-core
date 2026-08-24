"""A2A remote-agent tool adapter — wrap a remote agent as a Tool.

Each configured remote A2A agent becomes one :class:`Tool`: the LLM sees a
``prompt`` parameter, and ``execute()`` maps the call onto an A2A task
(``message/send`` → poll ``tasks/get`` → optional ``tasks/cancel``).

Progress is pushed through ``ToolContext.on_update`` using the same
``{"type": "delegation", ...}`` event shape the local multi-agent harness
uses, so remote agents are drop-in interchangeable with local sub-agents.

Config resolution order (``load_a2a_agent_configs``):
    1. ``<cwd>/.pi/a2a/agents.json``
    2. ``<cwd>/.a2a.json``
    3. ``A2A_AGENTS`` env var (JSON list or ``name:url[:token_env]`` entries)
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.a2a_client import A2AClient, A2AError, A2ATask
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolResult

__all__ = [
    "A2AAgentConfig",
    "A2AAgentTool",
    "build_a2a_tools",
    "load_a2a_agent_configs",
    "parse_a2a_agents",
    "register_a2a_tools",
]


@dataclass
class A2AAgentConfig:
    """Static config for one remote A2A agent."""

    name: str
    url: str
    description: str | None = None
    token_env: str | None = None
    timeout_seconds: float = 120.0
    poll_interval: float = 2.0


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

def parse_a2a_agents(raw: str | None) -> list[A2AAgentConfig]:
    """Parse ``A2A_AGENTS`` into configs.

    Supports a JSON list of objects or the legacy pipe-separated format
    ``name:url[:token_env[:timeout_seconds]]``.
    """
    if not raw or not raw.strip():
        return []
    raw = raw.strip()
    # JSON list form
    if raw.lstrip().startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        configs: list[A2AAgentConfig] = []
        for item in data:
            if not isinstance(item, dict) or not item.get("name") or not item.get("url"):
                continue
            configs.append(
                A2AAgentConfig(
                    name=str(item["name"]),
                    url=str(item["url"]),
                    description=str(item["description"]) if item.get("description") else None,
                    token_env=str(item["token_env"]) if item.get("token_env") else None,
                    timeout_seconds=float(item.get("timeout_seconds", 120.0)),
                    poll_interval=float(item.get("poll_interval", 2.0)),
                )
            )
        return configs

    # legacy pipe-separated: name:url[:token_env[:timeout]]
    # URLs may contain ":" (scheme/port), so only the tail is inspected for
    # the optional token_env / timeout suffixes. Use the JSON form for URLs
    # with ambiguous numeric ports.
    configs = []
    for spec in raw.split("|"):
        name, _, rest = spec.partition(":")
        name = name.strip()
        rest = rest.strip()
        if not name or not rest:
            continue
        timeout: float | None = None
        token_env: str | None = None
        m = re.match(r"^(.*):([0-9]+(?:\.[0-9]+)?)$", rest)
        if m and 0 < float(m.group(2)) <= 3600:
            timeout = float(m.group(2))
            rest = m.group(1)
        m = re.match(r"^(.*):([A-Za-z_][A-Za-z0-9_]*)$", rest)
        if m and not m.group(1).endswith(("http:", "https:")):
            token_env = m.group(2)
            rest = m.group(1)
        cfg = A2AAgentConfig(name=name, url=rest)
        if token_env:
            cfg.token_env = token_env
        if timeout is not None:
            cfg.timeout_seconds = timeout
        configs.append(cfg)
    return configs


def load_a2a_agent_configs(cwd: str = "") -> list[A2AAgentConfig]:
    """Load A2A agent configs from file (``.pi/a2a/agents.json`` or ``.a2a.json``),
    falling back to the ``A2A_AGENTS`` env var."""
    search_dir = cwd or os.getcwd()

    for rel in (os.path.join(".pi", "a2a", "agents.json"), ".a2a.json"):
        path = os.path.join(search_dir, rel)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            items = data.get("agents")
            if isinstance(items, list):
                return parse_a2a_agents(json.dumps(items, ensure_ascii=False))
        elif isinstance(data, list):
            return parse_a2a_agents(json.dumps(data, ensure_ascii=False))

    return parse_a2a_agents(os.environ.get("A2A_AGENTS", ""))


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class A2AAgentTool(Tool):
    """A remote A2A agent exposed as an agent_core Tool."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        base_url: str,
        token_env: str | None = None,
        token: str | None = None,
        client: A2AClient | None = None,
        timeout_seconds: float = 120.0,
        poll_interval: float = 2.0,
    ) -> None:
        self._name = name
        self._client = client or A2AClient(
            base_url,
            token_env=token_env,
            token=token,
            timeout=timeout_seconds,
            poll_interval=poll_interval,
        )
        self.definition = ToolDefinition(
            name=name,
            description=description or f"调用远端 A2A agent {name} 执行任务",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "要交给远端 agent 的任务描述，尽量具体、自包含",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "可选的任务元数据，随任务一起发送给远端 agent",
                    },
                },
                "required": ["prompt"],
            },
            prompt_snippet=f"{name} $ARGUMENTS — 委托任务给远端 A2A agent",
            timeout_seconds=timeout_seconds,
        )

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        prompt = str(params.get("prompt") or "")
        metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
        if not prompt.strip():
            return ToolResult(
                content=[TextContent(text="错误：缺少 prompt 参数")],
                details={
                    "delegation": {
                        "type": "delegation",
                        "phase": "end",
                        "agent": self._name,
                        "status": "failed",
                        "error_message": "missing prompt",
                    }
                },
            )

        async def _progress(task: A2ATask) -> None:
            if ctx.on_update is None:
                return
            res = ctx.on_update(
                ToolResult(
                    content=[TextContent(text="")],
                    details={
                        "delegation": {
                            "type": "delegation",
                            "phase": "remote_task_update",
                            "agent": self._name,
                            "task_id": task.id,
                            "status": task.state,
                            "summary": (task.output_text() or task.status_message() or "")[:200],
                        }
                    },
                )
            )
            if inspect.isawaitable(res):
                await res

        try:
            task = await self._client.run_task(
                prompt,
                ctx=ctx,
                metadata=metadata,
                on_progress=_progress,
            )
        except A2AError as exc:
            return ToolResult(
                content=[TextContent(text=f"远端 agent 调用失败: {exc}")],
                details={
                    "delegation": {
                        "type": "delegation",
                        "phase": "end",
                        "agent": self._name,
                        "status": "failed",
                        "error_message": str(exc),
                    }
                },
                display={"type": "delegation_error", "error": str(exc)},
            )

        return _task_to_result(self._name, task)


def _task_to_result(name: str, task: A2ATask) -> ToolResult:
    state = task.state
    if state == "completed":
        text = task.output_text() or "(远端 agent 未返回文本)"
        return ToolResult(
            content=[TextContent(text=text)],
            details={
                "delegation": {
                    "type": "delegation",
                    "phase": "end",
                    "agent": name,
                    "task_id": task.id,
                    "status": "completed",
                },
                "task": task.model_dump(mode="json"),
            },
            display={"type": "delegation", "status": "completed", "agent": name},
        )
    if state in ("failed", "rejected"):
        msg = task.status_message() or task.output_text() or f"远端 agent 任务状态: {state}"
        return ToolResult(
            content=[TextContent(text=f"远端 agent 任务失败: {msg}")],
            details={
                "delegation": {
                    "type": "delegation",
                    "phase": "end",
                    "agent": name,
                    "task_id": task.id,
                    "status": "failed",
                    "error_message": msg,
                },
                "task": task.model_dump(mode="json"),
            },
            display={"type": "delegation_error", "error": msg, "agent": name},
        )
    if state == "canceled":
        return ToolResult(
            content=[TextContent(text="远端 agent 任务已取消")],
            details={
                "delegation": {
                    "type": "delegation",
                    "phase": "end",
                    "agent": name,
                    "task_id": task.id,
                    "status": "aborted",
                },
                "task": task.model_dump(mode="json"),
            },
            display={"type": "delegation", "status": "aborted", "agent": name},
        )
    # input-required / unknown non-terminal
    msg = task.status_message() or "远端 agent 需要更多输入"
    return ToolResult(
        content=[TextContent(text=f"远端 agent 需要更多输入: {msg}")],
        details={
            "delegation": {
                "type": "delegation",
                "phase": "end",
                "agent": name,
                "task_id": task.id,
                "status": "input_required",
                "error_message": msg,
            },
            "task": task.model_dump(mode="json"),
        },
        display={"type": "delegation", "status": "input_required", "agent": name},
    )


# ---------------------------------------------------------------------------
# Build / register
# ---------------------------------------------------------------------------

def build_a2a_tools(configs: list[A2AAgentConfig]) -> list[A2AAgentTool]:
    return [
        A2AAgentTool(
            name=cfg.name,
            description=cfg.description or f"调用远端 A2A agent {cfg.name} 执行任务",
            base_url=cfg.url,
            token_env=cfg.token_env,
            timeout_seconds=cfg.timeout_seconds,
            poll_interval=cfg.poll_interval,
        )
        for cfg in configs
    ]


def register_a2a_tools(registry: ToolRegistry, *, cwd: str = "") -> int:
    """Load configs and register one Tool per remote agent. Returns count."""
    tools = build_a2a_tools(load_a2a_agent_configs(cwd=cwd))
    for tool in tools:
        registry.register(tool)
    return len(tools)
