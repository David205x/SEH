"""Parent Harness UTF-8 file reader for the Compiler."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.compiler import CompilerContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class ReadHarnessFileTool:
    def __init__(self, compiler: CompilerContext) -> None:
        self._compiler = compiler
        self._tool = CallableTool.from_callable(self.read_harness_file)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="read_harness_file")
    def read_harness_file(
        self,
        path: Annotated[str, ToolArg("POSIX plugins-root-relative file path.")],
    ) -> ToolResult:
        """Read one complete UTF-8 file from the parent Harness."""

        try:
            payload = self._compiler.read_harness_file(path)
        except (KeyError, ValueError) as exc:
            return ToolResult(
                name=self.name,
                content=f"HARNESS_LOOKUP_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> ReadHarnessFileTool:
    if config:
        raise ValueError("read_harness_file does not accept configuration")
    if not isinstance(context.runtime_context, CompilerContext):
        raise TypeError("read_harness_file requires a CompilerContext")
    return ReadHarnessFileTool(context.runtime_context)
