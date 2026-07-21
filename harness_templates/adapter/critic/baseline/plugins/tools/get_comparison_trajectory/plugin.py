"""Paired complete Actor trajectories for the Critic."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class GetComparisonTrajectoryTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.get_comparison_trajectory)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_comparison_trajectory")
    def get_comparison_trajectory(
        self,
        example_id: Annotated[
            str, ToolArg("Example ID returned by list_comparison_cases.")
        ],
        replicate_id: Annotated[
            str,
            ToolArg("Replicate ID returned by get_comparison_case."),
        ],
    ) -> ToolResult:
        """Read paired complete rollouts and a derived execution delta."""

        try:
            payload = self._critic.get_comparison_trajectory(
                example_id, replicate_id
            )
        except (KeyError, ValueError) as exc:
            return ToolResult(
                name=self.name,
                content=f"COMPARISON_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetComparisonTrajectoryTool:
    if config:
        raise ValueError("get_comparison_trajectory does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("get_comparison_trajectory requires a CriticContext")
    return GetComparisonTrajectoryTool(context.runtime_context)
