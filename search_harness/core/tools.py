"""Synchronous single-tool runtime for the first core loop."""

from __future__ import annotations

from collections.abc import Iterable

from .errors import ToolExecutionError, ToolRuntimeError, UnknownToolError
from .protocols import Tool
from .types import ToolCall, ToolResult

class ToolRuntime:
    """Execute exactly one parsed tool call synchronously."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool registered: {tool.name}")
            self._tools[tool.name] = tool

    def call_one(self, tool_call: ToolCall) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if tool is None:
            raise UnknownToolError(f"unknown tool requested: {tool_call.name}")

        try:
            result = tool.run(tool_call.arguments)
        except ToolRuntimeError:
            raise
        except Exception as exc:
            message = f"tool '{tool_call.name}' failed: {exc}"
            raise ToolExecutionError(message) from exc

        if not isinstance(result, ToolResult):
            raise ToolExecutionError(
                f"tool '{tool_call.name}' returned {type(result).__name__}, expected ToolResult"
            )
        return result
