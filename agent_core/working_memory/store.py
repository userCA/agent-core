"""Session working memory — pinned facts + rolling insights (H4)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkingMemoryStore:
    """Process-local working memory for one session (MVP)."""

    pinned: str = ""
    insights: list[str] = field(default_factory=list)
    max_insights: int = 12

    def write_pinned(self, content: str) -> None:
        self.pinned = content.strip()

    def clear_pinned(self) -> None:
        self.pinned = ""

    def write_insight(self, content: str) -> None:
        text = content.strip()
        if not text:
            return
        # Newest first; drop oldest when over capacity (scroll eviction).
        self.insights = [text, *[i for i in self.insights if i != text]]
        if len(self.insights) > self.max_insights:
            self.insights = self.insights[: self.max_insights]

    def format_pinned_block(self) -> str:
        if not self.pinned:
            return ""
        return f"## Pinned\n{self.pinned}"

    def format_insights_block(self) -> str:
        if not self.insights:
            return ""
        lines = ["## Working Memory Insights (newest first)"]
        for i, item in enumerate(self.insights, start=1):
            lines.append(f"{i}. {item}")
        return "\n".join(lines)
