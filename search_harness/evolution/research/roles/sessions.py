"""Role continuation state and short-lived run collectors."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar


_ToolCallT = TypeVar("_ToolCallT")
_OutputT = TypeVar("_OutputT")


@dataclass
class ToolCallCollector(Generic[_ToolCallT]):
    """Collect Tool Call audit records produced by one Agent Run."""

    calls: list[_ToolCallT] = field(default_factory=list)


@dataclass
class OutputCollector(Generic[_OutputT]):
    """Collect one submitted structured terminal output."""

    output: _OutputT | None = None


@dataclass(frozen=True)
class RoleContinuation:
    """Append structured feedback to an existing Role Session."""

    previous_artifact: dict[str, Any]
    feedback_source: str
    feedback: dict[str, Any]


@dataclass
class RoleSession:
    """Persistable conversation state for continued work in one Agent Role."""

    session_id: str
    revision: int
    messages: list[dict[str, Any]]
    output_history: list[dict[str, Any]]
    feedback_history: list[dict[str, Any]]

    def continued(
        self,
        *,
        feedback_event: dict[str, Any],
        feedback_message: str,
    ) -> "RoleSession":
        """Return the next revision without mutating the restored session."""

        return RoleSession(
            session_id=self.session_id,
            revision=self.revision + 1,
            messages=[
                *deepcopy(self.messages),
                {"role": "user", "content": feedback_message},
            ],
            output_history=deepcopy(self.output_history),
            feedback_history=[
                *deepcopy(self.feedback_history),
                deepcopy(feedback_event),
            ],
        )
