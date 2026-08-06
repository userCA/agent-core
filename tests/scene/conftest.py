"""Shared fixtures for scene tests."""

from __future__ import annotations

import pytest


# Ambient vars loaded from a repo-local .env (e.g. AGENT_PROVIDER=deepseek) by
# another test module at import time must not leak into scene tests. Each test
# runs with these removed; the original values are restored on teardown.
_AGENT_AMBIENT_ENV_KEYS = (
    "AGENT_PROVIDER",
    "AGENT_MODEL",
    "AGENT_API_KEY_ENV",
)


@pytest.fixture(autouse=True)
def _isolate_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each scene test with a clean AGENT_* env; restore afterwards."""
    for key in _AGENT_AMBIENT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
