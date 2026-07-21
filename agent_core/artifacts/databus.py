"""L4 DataBus extension — inject ref index into system prompt."""

from __future__ import annotations

from typing import Any

from agent_core.artifacts.ref_index import ArtifactRefIndex
from agent_core.extensions.base import ExtensionContext


class DataBusIndexExtension:
    """Append artifact ref index so the model knows what can be inspected."""

    name = "databus_index"

    def __init__(self, ref_index: ArtifactRefIndex, *, session_id: str) -> None:
        self._index = ref_index
        self._session_id = session_id

    async def on_event(self, ctx: ExtensionContext, evt: Any) -> None:
        return None

    async def on_before_agent_start(
        self, ctx: ExtensionContext, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        sid = ctx.session_id or self._session_id
        block = self._index.format_index_block(sid)
        if not block:
            return None
        if "## Artifact Ref Index" in system_prompt:
            return None
        return {"system_prompt": f"{system_prompt.rstrip()}\n\n{block}"}

    async def on_before_tool_call(
        self, ctx: ExtensionContext, tool_call: Any
    ) -> dict[str, Any] | None:
        return None

    async def on_after_tool_call(
        self, ctx: ExtensionContext, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        # Backup registration if externalize extension did not wire the index.
        if is_error:
            return None
        details = getattr(result, "details", None)
        if not isinstance(details, dict) or not details.get("__stored"):
            return None
        ref_id = details.get("__refId")
        if not isinstance(ref_id, str) or not ref_id:
            return None
        sid = ctx.session_id or self._session_id
        if self._index.get(sid, ref_id) is not None:
            return None  # already registered by ArtifactExternalizeExtension
        self._index.register(
            ref_id=ref_id,
            session_id=sid,
            tool_name=getattr(tool_call, "name", "") or "",
            chars=int(details.get("__chars") or 0),
            summary=str(details.get("__summary") or "")[:240],
        )
        return None
