"""Parent Harness component reader for the Compiler."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.compiler import CompilerContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class GetHarnessComponentTool:
    def __init__(self, compiler: CompilerContext) -> None:
        self._compiler = compiler
        self._tool = CallableTool.from_callable(self.get_harness_component)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_harness_component")
    def get_harness_component(
        self,
        component_id: Annotated[str, ToolArg("Manifest component instance_id.")],
    ) -> ToolResult:
        """Read one component declaration and all files in its directory."""

        try:
            payload = self._compiler.get_harness_component(component_id)
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            return ToolResult(
                name=self.name,
                content=f"HARNESS_LOOKUP_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetHarnessComponentTool:
    if config:
        raise ValueError("get_harness_component does not accept configuration")
    if not isinstance(context.runtime_context, CompilerContext):
        raise TypeError("get_harness_component requires a CompilerContext")
    return GetHarnessComponentTool(context.runtime_context)
