"""Actor Harness file and component comparison for the Critic."""

from __future__ import annotations

import json
from typing import Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolDefinition, tool


class GetHarnessChangeSummaryTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.get_harness_change_summary)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_harness_change_summary")
    def get_harness_change_summary(self) -> ToolResult:
        """List component and file changes from primary to comparison Harness."""

        try:
            payload = self._critic.get_harness_change_summary()
        except ValueError as exc:
            return ToolResult(
                name=self.name,
                content=f"COMPARISON_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetHarnessChangeSummaryTool:
    if config:
        raise ValueError("get_harness_change_summary does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("get_harness_change_summary requires a CriticContext")
    return GetHarnessChangeSummaryTool(context.runtime_context)
