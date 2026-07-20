"""In-session PlanStore with optional CustomEntry persistence."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agent_core.planning.types import Plan, PlanStep, PlanStepStatus
from agent_core.session.store import CustomEntry, SessionStore

logger = logging.getLogger(__name__)

PLAN_SNAPSHOT_TYPE = "plan_snapshot"


class PlanStore:
    """Authoritative in-memory plan for one session; optionally persists snapshots."""

    def __init__(
        self,
        *,
        session_store: SessionStore | None = None,
        session_id: str = "",
        owner: str = "",
        persist: bool = True,
    ) -> None:
        self._session_store = session_store
        self._session_id = session_id
        self._owner = owner
        self._persist = persist and session_store is not None and bool(session_id)
        self._plan: Plan | None = None

    @property
    def plan(self) -> Plan | None:
        return self._plan

    def set_plan(self, plan: Plan) -> Plan:
        self._plan = plan
        return plan

    def clear(self) -> None:
        self._plan = None

    def replace(
        self,
        *,
        title: str,
        steps: list[dict[str, Any]],
        plan_id: str | None = None,
    ) -> Plan:
        parsed: list[PlanStep] = []
        for i, raw in enumerate(steps):
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("id") or f"s{i + 1}")
            parsed.append(
                PlanStep(
                    id=sid,
                    title=str(raw.get("title") or raw.get("task") or sid),
                    status=raw.get("status") or "pending",  # type: ignore[arg-type]
                    detail=raw.get("detail"),
                )
            )
        version = (self._plan.version + 1) if self._plan else 1
        plan = Plan(
            id=plan_id or (self._plan.id if self._plan else str(uuid.uuid4())),
            title=title or "Plan",
            status="active",
            steps=parsed,
            version=version,
        )
        self._plan = plan
        return plan

    def set_status(
        self,
        *,
        step_id: str | None = None,
        status: PlanStepStatus | None = None,
        detail: str | None = None,
        updates: list[dict[str, Any]] | None = None,
    ) -> Plan:
        if self._plan is None:
            raise ValueError("No active plan; call replace first")
        plan = self._plan
        by_id = {s.id: s for s in plan.steps}

        items: list[dict[str, Any]] = list(updates or [])
        if step_id and status:
            items.append({"id": step_id, "status": status, "detail": detail})

        for item in items:
            sid = str(item.get("id") or "")
            step = by_id.get(sid)
            if step is None:
                continue
            if item.get("status"):
                step.status = item["status"]  # type: ignore[assignment]
            if "detail" in item and item["detail"] is not None:
                step.detail = str(item["detail"])

        # Enforce at most one in_progress: if multiple, keep the last marked.
        in_prog = [s for s in plan.steps if s.status == "in_progress"]
        if len(in_prog) > 1:
            for s in in_prog[:-1]:
                if s.status == "in_progress":
                    s.status = "pending"

        plan.version += 1
        return plan

    def revise(self, *, steps: list[dict[str, Any]] | None = None, title: str | None = None) -> Plan:
        if self._plan is None:
            raise ValueError("No active plan; call replace first")
        plan = self._plan
        if title:
            plan.title = title
        if steps is not None:
            existing = {s.id: s for s in plan.steps}
            merged: list[PlanStep] = []
            seen: set[str] = set()
            for i, raw in enumerate(steps):
                if not isinstance(raw, dict):
                    continue
                sid = str(raw.get("id") or f"s{i + 1}")
                seen.add(sid)
                if sid in existing and "title" not in raw and "status" not in raw:
                    step = existing[sid]
                    if raw.get("detail") is not None:
                        step.detail = str(raw["detail"])
                    merged.append(step)
                else:
                    prev = existing.get(sid)
                    merged.append(
                        PlanStep(
                            id=sid,
                            title=str(raw.get("title") or (prev.title if prev else sid)),
                            status=raw.get("status")
                            or (prev.status if prev else "pending"),  # type: ignore[arg-type]
                            detail=raw.get("detail") if "detail" in raw else (prev.detail if prev else None),
                        )
                    )
            plan.steps = merged
        plan.version += 1
        return plan

    def complete_plan(self) -> Plan:
        if self._plan is None:
            raise ValueError("No active plan")
        for s in self._plan.steps:
            if s.status in ("pending", "in_progress"):
                s.status = "completed"
        self._plan.status = "completed"
        self._plan.version += 1
        return self._plan

    def cancel_plan(self) -> Plan:
        if self._plan is None:
            raise ValueError("No active plan")
        for s in self._plan.steps:
            if s.status in ("pending", "in_progress"):
                s.status = "cancelled"
        self._plan.status = "cancelled"
        self._plan.version += 1
        return self._plan

    def snapshot_payload(self, *, phase: str = "updated") -> dict[str, Any]:
        plan = self._plan
        if plan is None:
            return {
                "type": "plan",
                "phase": phase,
                "plan": None,
                "owner": self._owner,
                "session_id": self._session_id,
            }
        done, total = plan.progress()
        return {
            "type": "plan",
            "phase": phase,
            "plan": plan.to_dict(),
            "done": done,
            "total": total,
            "owner": self._owner,
            "session_id": self._session_id,
            "version": plan.version,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    async def persist(self) -> None:
        if not self._persist or self._session_store is None or not self._session_id:
            return
        if self._plan is None:
            return
        entry = CustomEntry(
            custom_type=PLAN_SNAPSHOT_TYPE,
            data={
                "plan": self._plan.to_dict(),
                "owner": self._owner,
                "session_id": self._session_id,
                "version": self._plan.version,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            id=f"plan-{self._plan.id}-v{self._plan.version}-{int(time.time() * 1000)}",
        )
        try:
            await self._session_store.append_entry(self._session_id, entry)
        except Exception as exc:
            logger.warning("Failed to persist plan_snapshot: %s", exc)

    async def load_latest(self) -> Plan | None:
        if self._session_store is None or not self._session_id:
            return None
        try:
            snap = await self._session_store.load_session(self._session_id)
        except KeyError:
            return None
        except Exception as exc:
            logger.warning("Failed to load session for plan restore: %s", exc)
            return None
        latest: Plan | None = None
        for entry in snap.entries:
            if isinstance(entry, CustomEntry) and entry.custom_type == PLAN_SNAPSHOT_TYPE:
                data = entry.data if isinstance(entry.data, dict) else {}
                plan_data = data.get("plan")
                if isinstance(plan_data, dict):
                    try:
                        latest = Plan.from_dict(plan_data)
                    except Exception:
                        continue
        if latest is not None:
            self._plan = latest
        return latest
