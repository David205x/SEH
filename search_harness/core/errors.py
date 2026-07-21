"""Exceptions raised by the core runtime."""

from __future__ import annotations


class AgentLoopError(RuntimeError):
    """Base class for recoverable agent loop errors."""


class InvalidModelOutputError(AgentLoopError):
    """Raised when model output cannot be parsed into a loop action."""


class MaxStepsReachedError(AgentLoopError):
    """Raised internally when a run reaches the configured step budget."""


class ToolRuntimeError(AgentLoopError):
    """Base class for tool runtime errors."""


class UnknownToolError(ToolRuntimeError):
    """Raised when a model requests a tool that is not registered."""


class ToolExecutionError(ToolRuntimeError):
    """Raised when a registered tool fails during execution."""

