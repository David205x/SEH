"""Progressively disclosed Hook authoring API for the Compiler."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.compiler import CompilerContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class GetHookAuthoringGuideTool:
    def __init__(self, compiler: CompilerContext) -> None:
        self._compiler = compiler
        self._tool = CallableTool.from_callable(self.get_hook_authoring_guide)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_hook_authoring_guide")
    def get_hook_authoring_guide(
        self,
        topic: Annotated[
            str,
            ToolArg(
                "Hook API topic to read.",
                choices=(
                    "index",
                    "implementation",
                    "lifecycle",
                    "state_access",
                    "model_inference",
                    "final_decision",
                    "manifest",
                ),
            ),
        ] = "index",
    ) -> ToolResult:
        """Read one authoritative, versioned slice of the Hook authoring API."""

        payload = self._compiler.get_hook_authoring_guide(topic)
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetHookAuthoringGuideTool:
    if config:
        raise ValueError("get_hook_authoring_guide does not accept configuration")
    if not isinstance(context.runtime_context, CompilerContext):
        raise TypeError("get_hook_authoring_guide requires a CompilerContext")
    return GetHookAuthoringGuideTool(context.runtime_context)
