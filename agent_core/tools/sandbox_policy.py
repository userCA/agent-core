"""Sandbox policy extension — quota assignment and dangerous-command interception."""

from __future__ import annotations

import re
from typing import Any

from agent_core.tools.operations import SandboxQuota


class SandboxPolicyExtension:
    """Extension that assigns resource quotas and blocks dangerous commands.

    Does NOT switch backends — backend routing is done at tool construction time
    by injecting different file_ops/bash_ops into each tool.
    """

    name = "sandbox-policy"

    # Patterns that indicate the command needs network access
    _INSTALL_PATTERNS = [
        r"\bpip\b.*\binstall\b", r"\bpip3\b.*\binstall\b",
        r"\bapt-get\b", r"\bapt\b",
        r"\bnpm\b.*\binstall\b", r"\bnpx\b",
        r"\bcurl\b", r"\bwget\b",
        r"\bgit\b.*\bclone\b",
    ]

    # Patterns that are always denied regardless of sandbox
    _DANGEROUS_PATTERNS = [
        r"\brm\s+-rf\s+/", r"\brm\s+-rf\s+\/\*",
        r"\bchmod\s+777\s+/",
        r"\bmkfs\.", r"\bdd\s+if=",
        r">\s*/dev/sda", r">\s*/dev/nvme",
        r"\bshutdown\b", r"\breboot\b",
        r"\bfork\s+bomb", r":\(\)\s*{\s*:\|:",
    ]

    _QUOTA_MATRIX = {
        "default": SandboxQuota(cpu_cores=0.5, memory_mb=256, timeout_seconds=60, network_allowed=False),
        "data_analysis": SandboxQuota(cpu_cores=1.0, memory_mb=1024, timeout_seconds=120, network_allowed=False),
        "image_processing": SandboxQuota(cpu_cores=2.0, memory_mb=2048, timeout_seconds=180, network_allowed=False),
        "install_package": SandboxQuota(cpu_cores=1.0, memory_mb=512, timeout_seconds=120, network_allowed=True),
    }

    def __init__(self) -> None:
        pass

    async def on_event(self, ctx: Any, evt: Any) -> None:
        pass

    async def on_before_tool_call(
        self, ctx: Any, tool_call: Any
    ) -> dict[str, Any] | None:
        if tool_call.name != "bash":
            return None

        command = tool_call.arguments.get("command", "")

        # 1. Block dangerous commands
        for pattern in self._DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return {
                    "block": True,
                    "reason": f"Dangerous command pattern detected: '{pattern}'. "
                              f"This operation is blocked to prevent system damage.",
                }

        # 2. Pick quota based on command content
        quota = self._pick_quota(command)
        return {"inject_metadata": {"sandbox_quota": quota.__dict__}}

    async def on_after_tool_call(
        self, ctx: Any, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        return None

    def _pick_quota(self, command: str) -> SandboxQuota:
        # Check for install commands first
        for pattern in self._INSTALL_PATTERNS:
            if re.search(pattern, command):
                return self._QUOTA_MATRIX["install_package"]

        # Check for task-type indicators
        data_keywords = ["pandas", "numpy", "sklearn", "scipy", "sql",
                         "dataframe", "csv", "groupby", "matplotlib -"]
        img_keywords = ["matplotlib", "PIL", "cv2", "ffmpeg", "pillow",
                        "plot", "chart", "graph", "figure"]

        cmd_lower = command.lower()
        if any(k in cmd_lower for k in img_keywords):
            return self._QUOTA_MATRIX["image_processing"]
        if any(k in cmd_lower for k in data_keywords):
            return self._QUOTA_MATRIX["data_analysis"]

        return self._QUOTA_MATRIX["default"]
