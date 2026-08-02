"""角色无关的同步 Tool Execution 边界。"""

from __future__ import annotations

from collections.abc import Iterable

from .definitions import DefinedTool
from .types import ToolCall, ToolResult


class ToolRuntimeError(RuntimeError):
    """Tool Execution 的基础错误。"""


class UnknownToolError(ToolRuntimeError):
    """Tool Call 引用了未装配的 Tool。"""


class ToolExecutionError(ToolRuntimeError):
    """Tool 执行失败或返回了无效结果。"""


class ToolExecutor:
    """按名称执行一个已装配 Tool Call。"""

    def __init__(self, tools: Iterable[DefinedTool]) -> None:
        self._tools: dict[str, DefinedTool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool registered: {tool.name}")
            self._tools[tool.name] = tool

    def execute(self, tool_call: ToolCall) -> ToolResult:
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
                f"tool '{tool_call.name}' returned {type(result).__name__}, "
                "expected ToolResult"
            )
        return result
