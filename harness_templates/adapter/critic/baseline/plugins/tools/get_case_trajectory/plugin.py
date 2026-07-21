"""Complete Actor trajectory lookup for the Critic."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class GetCaseTrajectoryTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.get_case_trajectory)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_case_trajectory")
    def get_case_trajectory(
        self,
        example_id: Annotated[str, ToolArg("Example ID returned by list_evaluation_cases.")],
        replicate_id: Annotated[
            str,
            ToolArg("Replicate ID returned by get_case_evaluation."),
        ],
    ) -> ToolResult:
        """Read one complete Actor replicate identified by both IDs."""

        try:
            payload = self._critic.get_case_trajectory(example_id, replicate_id)
        except KeyError as exc:
            return ToolResult(
                name=self.name,
                content=f"EVIDENCE_LOOKUP_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetCaseTrajectoryTool:
    if config:
        raise ValueError("get_case_trajectory does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("get_case_trajectory requires a CriticContext")
    return GetCaseTrajectoryTool(context.runtime_context)
