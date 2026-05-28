"""Minimal MCP stdio server with echo / add / get_time tools for testing.

Start in another terminal before launching the agent:
  python -m agent_core.skills.mcp_example_server

Or let the agent start it automatically via MCP_SERVERS env:
  MCP_SERVERS=stdio:example:python:-m:agent_core.skills.mcp_example_server
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any


def _write_json(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def _read_json() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def main() -> None:
    # ---------- initialize ----------
    req = _read_json()
    if req is None:
        return

    _write_json({
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "example-mcp", "version": "1.0.0"},
        },
    })

    # Consume "initialized" notification
    _read_json()

    # ---------- request loop ----------
    while True:
        req = _read_json()
        if req is None:
            break

        method = req.get("method", "")
        req_id = req.get("id")

        if method == "tools/list":
            _write_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo back the input message",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string", "description": "Message to echo"}
                                },
                                "required": ["message"],
                            },
                        },
                        {
                            "name": "add",
                            "description": "Add two numbers together",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "a": {"type": "number", "description": "First number"},
                                    "b": {"type": "number", "description": "Second number"},
                                },
                                "required": ["a", "b"],
                            },
                        },
                        {
                            "name": "get_time",
                            "description": "Get the current server timestamp",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            })

        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            if tool_name == "echo":
                text = f"Echo: {arguments.get('message', '')}"
            elif tool_name == "add":
                a = arguments.get("a", 0)
                b = arguments.get("b", 0)
                text = f"{a} + {b} = {a + b}"
            elif tool_name == "get_time":
                text = f"Server time: {time.strftime('%Y-%m-%d %H:%M:%S')} (unix: {int(time.time())})"
            else:
                text = f"Unknown tool: {tool_name}"

            _write_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": text}]},
            })

        else:
            _write_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            })


if __name__ == "__main__":
    main()
