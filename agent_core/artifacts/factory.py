"""Wire L4 inspect tool + DataBus index extension onto a session."""

from __future__ import annotations

from typing import Any

from agent_core.artifacts.databus import DataBusIndexExtension
from agent_core.artifacts.inspect import InspectArtifactTool
from agent_core.artifacts.ref_index import ArtifactRefIndex
from agent_core.artifacts.store import ArtifactStore
from agent_core.session.tool_utils import resolve_tool_name
from agent_core.tools.base import ToolRegistry

_SHARED_INDEX: ArtifactRefIndex | None = None


def shared_ref_index() -> ArtifactRefIndex:
    """Process-wide ref index (MVP).

    Entries accumulate until ``clear_session`` is called; no automatic TTL yet.
    """
    global _SHARED_INDEX
    if _SHARED_INDEX is None:
        _SHARED_INDEX = ArtifactRefIndex()
    return _SHARED_INDEX


def install_databus(
    tool_registry: ToolRegistry,
    *,
    store: ArtifactStore,
    session_id: str,
    ref_index: ArtifactRefIndex | None = None,
    extensions: list[Any] | None = None,
) -> tuple[ArtifactRefIndex, InspectArtifactTool, list[Any]]:
    """Register ``inspect_artifact`` and append ``DataBusIndexExtension``."""
    index = ref_index if ref_index is not None else shared_ref_index()
    tool = InspectArtifactTool(store=store, ref_index=index, session_id=session_id)
    name = resolve_tool_name(tool)
    if tool_registry.get(name) is None:
        tool_registry.register(tool)

    ext_list = list(extensions or [])
    if not any(getattr(e, "name", None) == "databus_index" for e in ext_list):
        ext_list.append(DataBusIndexExtension(index, session_id=session_id))
    return index, tool, ext_list
