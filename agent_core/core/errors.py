"""AgentHarnessError — unified structured error for all public API failures.

Every public method on AgentHarness (or Agent) should raise
``AgentHarnessError`` with a typed ``code`` instead of raw ``RuntimeError``
or ``ValueError``.

Error codes:
    busy             — operation rejected because the harness is running
    invalid_state    — operation rejected because current state doesn't allow it
    invalid_argument — bad input (duplicate names, unknown tool, etc.)
    session          — persistence / store failure
    hook             — hook handler threw
    compaction       — compaction failure
    unknown          — catch-all
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


class AgentHarnessError(Exception):
    """Structured error carrying a machine-readable ``code``."""

    def __init__(self, code: str, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.cause = cause

    def __repr__(self) -> str:
        return f"AgentHarnessError(code={self.code!r}, message={str(self)!r})"


def normalize_harness_error(error: BaseException, fallback_code: str = "unknown") -> AgentHarnessError:
    """Wrap any exception into an ``AgentHarnessError``.

    If ``error`` is already an ``AgentHarnessError``, return it unchanged.
    """
    if isinstance(error, AgentHarnessError):
        return error
    return AgentHarnessError(fallback_code, str(error), cause=error)


def normalize_hook_error(error: BaseException) -> AgentHarnessError:
    """Normalize an exception thrown inside a hook handler."""
    return normalize_harness_error(error, "hook")
