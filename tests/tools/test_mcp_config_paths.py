"""Tests for MCP config path resolution (load_mcp_server_configs)."""

import json
from pathlib import Path

from agent_core.tools.mcp_tool import load_mcp_server_configs


def _write_mcp_json(path: Path, servers: dict) -> None:
    """Write a Claude Desktop-style .mcp.json config file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _stdio_server(command: str, args: list[str]) -> dict:
    return {"command": command, "args": args}


def _sse_server(url: str) -> dict:
    return {"url": url}


class TestExplicitPath:
    def test_explicit_path_loads_configs(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "custom.json"
        _write_mcp_json(
            cfg_file,
            {
                "local_tools": _stdio_server("python", ["-m", "demo_server"]),
                "remote": _sse_server("http://localhost:8080/sse"),
            },
        )
        monkeypatch.setenv("MCP_SERVERS", "stdio:env_srv:echo:hi")

        servers = load_mcp_server_configs(path=str(cfg_file))

        assert len(servers) == 2
        local = servers[0]
        assert local.name == "local_tools"
        assert local.transport == "stdio"
        assert local.command == ["python", "-m", "demo_server"]
        remote = servers[1]
        assert remote.name == "remote"
        assert remote.transport == "sse"
        assert remote.url == "http://localhost:8080/sse"

    def test_explicit_path_missing_falls_back_to_env(self, tmp_path, monkeypatch):
        missing = tmp_path / "does-not-exist.json"
        monkeypatch.setenv("MCP_SERVERS", "stdio:env_srv:echo:hi")

        servers = load_mcp_server_configs(path=str(missing))

        assert len(servers) == 1
        assert servers[0].name == "env_srv"
        assert servers[0].transport == "stdio"
        assert servers[0].command == ["echo", "hi"]


class TestDefaultResolution:
    def test_prefers_shared_over_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "stdio:env_srv:echo:hi")
        _write_mcp_json(
            tmp_path / ".pi" / "mcp" / "shared.mcp.json",
            {"shared_srv": _stdio_server("python", ["-m", "shared_server"])},
        )
        _write_mcp_json(
            tmp_path / ".mcp.json",
            {"root_srv": _stdio_server("python", ["-m", "root_server"])},
        )

        servers = load_mcp_server_configs(cwd=str(tmp_path))

        assert len(servers) == 1
        assert servers[0].name == "shared_srv"
        assert servers[0].transport == "stdio"
        assert servers[0].command == ["python", "-m", "shared_server"]

    def test_falls_back_to_root_when_shared_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "stdio:env_srv:echo:hi")
        _write_mcp_json(
            tmp_path / ".mcp.json",
            {"root_srv": _stdio_server("python", ["-m", "root_server"])},
        )

        servers = load_mcp_server_configs(cwd=str(tmp_path))

        assert len(servers) == 1
        assert servers[0].name == "root_srv"
        assert servers[0].transport == "stdio"
        assert servers[0].command == ["python", "-m", "root_server"]

    def test_falls_back_to_env_when_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "sse:env_srv:http://localhost:9000/sse")

        servers = load_mcp_server_configs(cwd=str(tmp_path))

        assert len(servers) == 1
        assert servers[0].name == "env_srv"
        assert servers[0].transport == "sse"
        assert servers[0].url == "http://localhost:9000/sse"
