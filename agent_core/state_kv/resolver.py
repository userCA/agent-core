"""Resolve ``{{state.key}}`` placeholders against a SessionStateStore."""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from agent_core.state_kv.store import SessionStateStore

# Flat keys: letters, digits, underscore. No nested path in MVP.
_PLACEHOLDER_RE = re.compile(r"\{\{state\.([A-Za-z_][A-Za-z0-9_]*)\}\}")
_WHOLE_PLACEHOLDER_RE = re.compile(
    r"^\{\{state\.([A-Za-z_][A-Za-z0-9_]*)\}\}$"
)

STATE_KEY_MISSING = "STATE_KEY_MISSING"


class StateKeyMissingError(KeyError):
    """Raised when a ``{{state.*}}`` placeholder cannot be resolved."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"{STATE_KEY_MISSING}: state key '{key}' is not bound for this session"
        )


LookupFn = Callable[[str], Awaitable[Any | None]]


async def _lookup_key(store: SessionStateStore, session_id: str, key: str) -> Any:
    if not await store.has(session_id, key):
        raise StateKeyMissingError(key)
    return await store.get(session_id, key)


async def resolve_placeholders(
    value: Any,
    *,
    store: SessionStateStore,
    session_id: str,
) -> Any:
    """Deep-resolve ``{{state.key}}`` in strings / dicts / lists.

    - Entire string equal to ``{{state.key}}`` → replace with typed store value.
    - Partial string with placeholders → interpolate via ``str(value)``.
    - Missing keys raise :class:`StateKeyMissingError`.
    """

    async def lookup(key: str) -> Any:
        return await _lookup_key(store, session_id, key)

    return await _resolve(value, lookup)


async def _resolve(value: Any, lookup: LookupFn) -> Any:
    if isinstance(value, str):
        return await _resolve_string(value, lookup)
    if isinstance(value, dict):
        return {k: await _resolve(v, lookup) for k, v in value.items()}
    if isinstance(value, list):
        return [await _resolve(v, lookup) for v in value]
    if isinstance(value, tuple):
        return tuple([await _resolve(v, lookup) for v in value])
    return value


async def _resolve_string(text: str, lookup: LookupFn) -> Any:
    whole = _WHOLE_PLACEHOLDER_RE.match(text)
    if whole:
        return await lookup(whole.group(1))

    if not _PLACEHOLDER_RE.search(text):
        return text

    async def repl(match: re.Match[str]) -> str:
        resolved = await lookup(match.group(1))
        return str(resolved)

    # Manual rebuild because re.sub cannot await.
    parts: list[str] = []
    last = 0
    for match in _PLACEHOLDER_RE.finditer(text):
        parts.append(text[last : match.start()])
        parts.append(await repl(match))
        last = match.end()
    parts.append(text[last:])
    return "".join(parts)


def has_state_placeholder(value: Any) -> bool:
    """Return True if *value* (deep) contains any ``{{state.*}}`` string."""
    if isinstance(value, str):
        return _PLACEHOLDER_RE.search(value) is not None
    if isinstance(value, dict):
        return any(has_state_placeholder(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_state_placeholder(v) for v in value)
    return False
