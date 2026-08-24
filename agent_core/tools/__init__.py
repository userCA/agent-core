"""Tool abstractions and adapters."""

from agent_core.tools.base import (
    Tool,
    ToolContext,
    ToolDefinition,
    ToolInfo,
    ToolRegistry,
    ToolResult,
)
from agent_core.tools.mutation_queue import FileMutationQueue
from agent_core.tools.operations import (
    BashOperations,
    BashResult,
    FileInfo,
    FileOperations,
    SandboxBackend,
    SandboxQuota,
)
from agent_core.tools.operations_local import LocalBashOperations, LocalFileOperations
from agent_core.tools.a2a_client import A2AClient, A2AError, A2ATask
from agent_core.tools.a2a_tool import (
    A2AAgentConfig,
    A2AAgentTool,
    build_a2a_tools,
    load_a2a_agent_configs,
    parse_a2a_agents,
    register_a2a_tools,
)
from agent_core.tools.render import RenderedOutput, ToolRenderer
from agent_core.tools.truncate import format_size, truncate_head, truncate_line, truncate_tail

__all__ = [
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolInfo",
    "ToolRegistry",
    "ToolResult",
    "FileMutationQueue",
    "BashOperations",
    "BashResult",
    "FileInfo",
    "FileOperations",
    "SandboxBackend",
    "SandboxQuota",
    "LocalBashOperations",
    "LocalFileOperations",
    "RenderedOutput",
    "ToolRenderer",
    "A2AClient",
    "A2AError",
    "A2ATask",
    "A2AAgentConfig",
    "A2AAgentTool",
    "build_a2a_tools",
    "load_a2a_agent_configs",
    "parse_a2a_agents",
    "register_a2a_tools",
    "format_size",
    "truncate_head",
    "truncate_line",
    "truncate_tail",
]
