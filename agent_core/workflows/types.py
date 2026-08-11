from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowStatus = Literal["running", "completed", "failed", "aborted", "paused"]


class WorkflowMeta(BaseModel):
    name: str
    description: str = ""
    phases: list[str] = Field(default_factory=list)


class WorkflowOptions(BaseModel):
    search_paths: list[str] = Field(default_factory=lambda: ["./.pi/workflows"])
    include_builtin_recipes: bool = True
    max_agent_invocations: int = 100
    enable_dynamic_exec: bool = False
    auto_checkpoint_phases: bool = True
    model_config = {"arbitrary_types_allowed": True}


class WorkflowProgress(BaseModel):
    type: Literal["workflow"] = "workflow"
    run_id: str
    name: str
    status: WorkflowStatus
    phase: str | None = None
    phases: list[str] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)
    progress: dict[str, int] = Field(default_factory=dict)
    error_message: str | None = None
    result: Any | None = None


class WorkflowCheckpoint(BaseModel):
    run_id: str
    workflow_name: str
    status: WorkflowStatus
    current_phase: str | None = None
    completed_phases: list[str] = Field(default_factory=list)
    all_phases: list[str] = Field(default_factory=list)
    phase_outputs: dict[str, Any] = Field(default_factory=dict)
    args: dict[str, Any] = Field(default_factory=dict)
    agent_invocation_count: int = 0
    updated_at: float = 0.0
    owner: str = ""
    session_id: str = ""
    log: list[str] = Field(default_factory=list)


class WorkflowRunResult(BaseModel):
    run_id: str
    name: str
    status: WorkflowStatus
    result: Any | None = None
    error_message: str | None = None
    checkpoint: WorkflowCheckpoint | None = None
