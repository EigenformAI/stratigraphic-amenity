"""Typed errors for agent-facing MCP operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpToolError(Exception):
    """An actionable tool failure with a stable machine-readable code."""

    code: str
    message: str
    trace_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    recovery_hints: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.trace_id is not None:
            data["trace_id"] = self.trace_id
        if self.details:
            data["details"] = dict(self.details)
        if self.recovery_hints:
            data["recovery_hints"] = list(self.recovery_hints)
        return data
