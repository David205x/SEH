"""Parent Harness file listing for the Compiler."""

from __future__ import annotations

import json
from typing import Any

from search_harness.adapter.compiler import CompilerContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolDefinition, tool


class ListHarnessFilesTool:
    def __init__(self, compiler: CompilerContext) -> None:
        self._compiler = compiler
        self._tool = CallableTool.from_callable(self.list_harness_files)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="list_harness_files")
    def list_harness_files(self) -> ToolResult:
        """List every parent Harness file path and byte size."""

        payload = self._compiler.list_harness_files()
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> ListHarnessFilesTool:
    if config:
        raise ValueError("list_harness_files does not accept configuration")
    if not isinstance(context.runtime_context, CompilerContext):
        raise TypeError("list_harness_files requires a CompilerContext")
    return ListHarnessFilesTool(context.runtime_context)
