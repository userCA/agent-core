"""Workflow checkpoint persistence via CustomEntry."""

from __future__ import annotations

import logging
import uuid

from agent_core.session.store import CustomEntry, SessionStore
from agent_core.workflows.types import WorkflowCheckpoint

logger = logging.getLogger(__name__)

WORKFLOW_CHECKPOINT_TYPE = "workflow_checkpoint"


class WorkflowStore:
    """Persists workflow checkpoints as CustomEntry snapshots in a session."""

    def __init__(
        self,
        *,
        session_store: SessionStore,
        session_id: str,
        owner: str = "",
        persist: bool = True,
    ) -> None:
        self._session_store = session_store
        self._session_id = session_id
        self._owner = owner
        self._persist = persist and bool(session_id)

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        if not self._persist:
            return
        data = checkpoint.model_dump()
        if not data.get("owner"):
            data["owner"] = self._owner
        if not data.get("session_id"):
            data["session_id"] = self._session_id
        entry = CustomEntry(
            custom_type=WORKFLOW_CHECKPOINT_TYPE,
            data=data,
            id=str(uuid.uuid4()),
        )
        try:
            await self._session_store.append_entry(self._session_id, entry)
        except Exception as exc:
            logger.warning("Failed to persist workflow_checkpoint: %s", exc)

    async def load_checkpoint(self, run_id: str) -> WorkflowCheckpoint | None:
        latest = self._latest_by_run_id(await self._load_checkpoint_entries())
        cp = latest.get(run_id)
        return WorkflowCheckpoint.model_validate(cp) if cp is not None else None

    async def list_checkpoints(self) -> list[WorkflowCheckpoint]:
        latest = self._latest_by_run_id(await self._load_checkpoint_entries())
        return [WorkflowCheckpoint.model_validate(data) for data in latest.values()]

    async def _load_checkpoint_entries(self) -> list[dict]:
        try:
            snap = await self._session_store.load_session(self._session_id)
        except KeyError:
            return []
        except Exception as exc:
            logger.warning("Failed to load session for workflow checkpoints: %s", exc)
            return []

        entries: list[dict] = []
        for entry in snap.entries:
            if not isinstance(entry, CustomEntry):
                continue
            if entry.custom_type != WORKFLOW_CHECKPOINT_TYPE:
                continue
            if not isinstance(entry.data, dict):
                continue
            entries.append(entry.data)
        return entries

    @staticmethod
    def _latest_by_run_id(entries: list[dict]) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for data in entries:
            run_id = data.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                continue
            latest[run_id] = data
        return latest
