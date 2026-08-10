class WorkflowError(Exception):
    """Base workflow error."""


class SandboxError(WorkflowError):
    """Script failed AST/sandbox validation."""


class CheckpointError(WorkflowError):
    """Checkpoint missing or incompatible."""


class QuotaExceeded(WorkflowError):
    """max_agent_invocations exceeded."""
