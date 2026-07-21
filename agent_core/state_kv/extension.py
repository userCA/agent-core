"""Extension: bind tool-result keys + resolve ``{{state.key}}`` before execute."""

from __future__ import annotations

import re
from typing import Any

from agent_core.extensions.base import ExtensionContext
from agent_core.state_kv.resolver import (
    STATE_KEY_MISSING,
    StateKeyMissingError,
    has_state_placeholder,
    resolve_placeholders,
)
from agent_core.state_kv.store import SessionStateStore

STATE_BIND_KEY = "__state_bind"
STATE_BOUND_KEY = "__state_bound"
_BIND_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SessionStateBindingExtension:
    """H3 parameterBindings: session KV bind + system-side placeholder inject.

    **Write** — tools put ``details["__state_bind"] = {key: value, ...}``.
    Bound payloads are stripped from details (replaced by ``__state_bound``
    key list) so large arrays never linger in the transcript.

    **Read** — tool args containing ``{{state.key}}`` are resolved in
    ``on_before_tool_call`` via ``mutated_args`` (not via the LLM).
    Only keys that contain placeholders are returned, so peer hooks'
    ``mutated_args`` for other keys are not overwritten.
    """

    name = "session_state_binding"

    def __init__(self, store: SessionStateStore) -> None:
        self._store = store

    @property
    def store(self) -> SessionStateStore:
        return self._store

    async def on_before_tool_call(
        self, ctx: ExtensionContext, tool_call: Any
    ) -> dict[str, Any] | None:
        args = getattr(tool_call, "arguments", None)
        if not isinstance(args, dict) or not has_state_placeholder(args):
            return None
        try:
            resolved = await resolve_placeholders(
                args,
                store=self._store,
                session_id=ctx.session_id,
            )
        except StateKeyMissingError as exc:
            return {
                "block": True,
                "reason": str(exc),
            }
        if not isinstance(resolved, dict):
            return {
                "block": True,
                "reason": f"{STATE_KEY_MISSING}: resolved args must be an object",
            }
        changed = {
            k: resolved[k]
            for k in args
            if k in resolved and has_state_placeholder(args[k])
        }
        return {"mutated_args": changed} if changed else None

    async def on_after_tool_call(
        self,
        ctx: ExtensionContext,
        tool_call: Any,
        result: Any,
        is_error: bool,
    ) -> dict[str, Any] | None:
        if is_error:
            return None

        details = getattr(result, "details", None)
        if not isinstance(details, dict):
            return None
        bind = details.get(STATE_BIND_KEY)
        if not isinstance(bind, dict):
            return None

        bound_keys: list[str] = []
        for key, value in bind.items():
            if not isinstance(key, str) or not _BIND_KEY_RE.match(key):
                continue
            await self._store.set(ctx.session_id, key, value)
            bound_keys.append(key)

        # Always strip __state_bind so large payloads never stay in transcript,
        # even when no valid keys were bound.
        new_details = {k: v for k, v in details.items() if k != STATE_BIND_KEY}
        if bound_keys:
            new_details[STATE_BOUND_KEY] = bound_keys

        content = list(getattr(result, "content", None) or [])
        return {
            "result": {
                "content": content,
                "details": new_details,
                "display": getattr(result, "display", None),
            }
        }


def create_state_kv_extension(
    store: SessionStateStore | None = None,
) -> tuple[SessionStateStore, SessionStateBindingExtension]:
    """Return ``(store, extension)`` ready to append to Harness ``extensions``."""
    from agent_core.state_kv.store import InMemorySessionStateStore

    resolved: SessionStateStore = (
        store if store is not None else InMemorySessionStateStore()
    )
    return resolved, SessionStateBindingExtension(resolved)
