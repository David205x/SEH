"""Complete evaluation record lookup for the Critic."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class GetCaseEvaluationTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.get_case_evaluation)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_case_evaluation")
    def get_case_evaluation(
        self,
        example_id: Annotated[str, ToolArg("Example ID returned by list_evaluation_cases.")],
    ) -> ToolResult:
        """Read one logical-example stability summary and replicate directory."""

        try:
            payload = self._critic.get_case_evaluation(example_id)
        except KeyError as exc:
            return ToolResult(
                name=self.name,
                content=f"EVIDENCE_LOOKUP_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetCaseEvaluationTool:
    if config:
        raise ValueError("get_case_evaluation does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("get_case_evaluation requires a CriticContext")
    return GetCaseEvaluationTool(context.runtime_context)
