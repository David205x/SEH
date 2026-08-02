"""Tool Call、Tool Result 与一次完整 Tool Interaction。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """Model 请求执行一个 Tool 的结构化指令。"""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool call name must not be empty")
        if not isinstance(self.arguments, dict):
            raise TypeError("tool call arguments must be a dict")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "arguments", dict(self.arguments))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "arguments": dict(self.arguments)}


@dataclass(frozen=True)
class ToolResult:
    """Tool Execution 返回的输出、错误和执行元数据。"""

    name: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool result name must not be empty")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "content", str(self.content))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ToolInteraction:
    """一组相互关联的 Tool Call 与 Tool Result。"""

    tool_call: ToolCall
    tool_result: ToolResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_call": self.tool_call.to_dict(),
            "tool_result": self.tool_result.to_dict(),
        }
