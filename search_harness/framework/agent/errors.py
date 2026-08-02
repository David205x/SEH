"""Exceptions raised by the core runtime."""

from __future__ import annotations

from ..tools import (
    ToolExecutionError,
    ToolRuntimeError,
    UnknownToolError,
)


class AgentLoopError(RuntimeError):
    """Base class for recoverable agent loop errors."""


class InvalidModelOutputError(AgentLoopError):
    """Raised when model output cannot be parsed into a loop action."""


class MaxStepsReachedError(AgentLoopError):
    """Raised internally when a run reaches the configured step budget."""

