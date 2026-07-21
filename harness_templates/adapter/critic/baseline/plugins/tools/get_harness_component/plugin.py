"""Actor Harness component lookup for the Critic."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class GetHarnessComponentTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
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
        category: Annotated[
            str,
            ToolArg("Manifest component category.", choices=("tools", "prompts", "extensions")),
        ],
        component_id: Annotated[str, ToolArg("Manifest component instance_id.")],
    ) -> ToolResult:
        """Read one Actor Harness component declaration and all of its UTF-8 files."""

        try:
            payload = self._critic.get_harness_component(category, component_id)
        except (KeyError, ValueError) as exc:
            return ToolResult(
                name=self.name,
                content=f"HARNESS_LOOKUP_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetHarnessComponentTool:
    if config:
        raise ValueError("get_harness_component does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("get_harness_component requires a CriticContext")
    return GetHarnessComponentTool(context.runtime_context)
