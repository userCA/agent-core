"""Diagnostic collector for resource loading."""

from __future__ import annotations

from agent_core.resources.types import ResourceDiagnostic


class ResourceDiagnostics:
    """Collects diagnostics during resource loading."""

    def __init__(self) -> None:
        self._items: list[ResourceDiagnostic] = []

    def warning(self, message: str, *, source_path: str | None = None) -> None:
        self._items.append(ResourceDiagnostic(type="warning", message=message, source_path=source_path))

    def error(self, message: str, *, source_path: str | None = None) -> None:
        self._items.append(ResourceDiagnostic(type="error", message=message, source_path=source_path))

    def collision(
        self,
        message: str,
        *,
        winner_path: str,
        loser_path: str,
    ) -> None:
        self._items.append(
            ResourceDiagnostic(
                type="collision",
                message=message,
                winner_path=winner_path,
                loser_path=loser_path,
            )
        )

    @property
    def items(self) -> list[ResourceDiagnostic]:
        return list(self._items)

    @property
    def has_errors(self) -> bool:
        return any(d.type == "error" for d in self._items)
