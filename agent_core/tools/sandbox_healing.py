"""Self-healing extension — detect common sandbox errors and apply fixes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_core.tools.operations import BashOperations

logger = logging.getLogger(__name__)

# Patterns that indicate a specific fix is needed
_MISSING_MODULE_RE = r"No module named '(\w+)'"
_MEMORY_ERROR_RE = r"MemoryError|Killed"
_FILE_NOT_FOUND_RE = r"No such file or directory: '?([^'\n]+)'?"


class SelfHealingExtension:
    """Detects common sandbox execution errors and applies automated fixes.

    Phase 1 (immediate): Auto-install missing modules, copy files into sandbox.
    Phase 2 (prompt retry): Return enhanced error messages telling the LLM
    what was done so it can retry the original command.

    Does NOT block the tool runner — the LLM retries naturally in the next turn.
    """

    name = "self-healing"

    def __init__(self, bash_ops: BashOperations | None = None) -> None:
        """bash_ops: backend for running fix commands (pip install, cp, etc.).
        If None, auto-install fixes are skipped (only error enhancement is applied).
        """
        self._bash_ops = bash_ops
        self._fixes_applied: dict[str, list[str]] = {}  # tool_call_id -> applied fixes

    async def on_event(self, ctx: Any, evt: Any) -> None:
        pass

    async def on_before_tool_call(
        self, ctx: Any, tool_call: Any
    ) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: Any, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        if not is_error:
            return None

        if tool_call.name != "bash":
            return None

        result_text = self._extract_text(result)
        command = tool_call.arguments.get("command", "")
        fixes: list[str] = []

        # 1. ModuleNotFoundError → pip install
        missing_module = self._detect_missing_module(result_text)
        if missing_module and self._bash_ops is not None:
            fix_result = await self._install_module(missing_module)
            if fix_result:
                fixes.append(f"Installed missing module '{missing_module}': {fix_result}")
            else:
                fixes.append(f"Attempted to install '{missing_module}' but it may have failed. "
                             f"Check that the package name is correct.")

        # 2. MemoryError → suggest quota increase
        if self._is_memory_error(result_text):
            fixes.append(
                "Memory limit exceeded. Consider processing data in smaller chunks "
                "or requesting higher memory quota."
            )

        # 3. Timeout → suggest longer timeout
        if self._is_timeout(result_text):
            fixes.append(
                "Command timed out. Consider optimizing the command, reducing data size, "
                "or requesting a longer timeout."
            )

        # 4. FileNotFoundError → suggest copying file into sandbox
        missing_file = self._detect_missing_file(result_text)
        if missing_file:
            fixes.append(
                f"File not found: '{missing_file}'. If this file exists outside the sandbox, "
                f"use the write tool to copy it into the sandbox output directory."
            )

        if not fixes:
            return None

        self._fixes_applied[tool_call.id] = fixes
        return self._build_response(result, fixes)

    def _detect_missing_module(self, text: str) -> str | None:
        import re
        match = re.search(_MISSING_MODULE_RE, text)
        return match.group(1) if match else None

    def _is_memory_error(self, text: str) -> bool:
        import re
        return bool(re.search(_MEMORY_ERROR_RE, text))

    def _is_timeout(self, text: str) -> bool:
        return "timed out" in text.lower()

    def _detect_missing_file(self, text: str) -> str | None:
        import re
        match = re.search(_FILE_NOT_FOUND_RE, text)
        return match.group(1) if match else None

    async def _install_module(self, module: str) -> str | None:
        try:
            result = await self._bash_ops.execute(
                f"pip install {module}",
                timeout=60.0,
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[-1] if result.stdout else "ok"
            return None
        except Exception as exc:
            logger.warning("Auto-install of '%s' failed: %s", module, exc)
            return None

    def _extract_text(self, result: Any) -> str:
        parts: list[str] = []
        for c in getattr(result, "content", []) or []:
            text = getattr(c, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _build_response(self, result: Any, fixes: list[str]) -> dict[str, Any]:
        import time
        orig_text = self._extract_text(result)
        fix_text = "\n\n[Self-healing]\n" + "\n".join(f"- {f}" for f in fixes)
        enhanced_text = orig_text + fix_text

        from agent_core.core.content import TextContent
        return {
            "result": {
                "content": [TextContent(text=enhanced_text)],
                "details": getattr(result, "details", None),
                "display": getattr(result, "display", None),
            }
        }
