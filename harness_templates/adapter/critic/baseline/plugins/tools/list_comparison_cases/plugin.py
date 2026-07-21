"""Paginated cross-report case transitions for the Critic."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class ListComparisonCasesTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.list_comparison_cases)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="list_comparison_cases")
    def list_comparison_cases(
        self,
        page: Annotated[int, ToolArg("One-based result page.", minimum=1)] = 1,
        page_size: Annotated[
            int, ToolArg("Number of cases per page.", minimum=1, maximum=100)
        ] = 20,
        transition: Annotated[
            str,
            ToolArg(
                "Score transition filter from primary to comparison.",
                choices=(
                    "any",
                    "primary_only_correct",
                    "comparison_only_correct",
                    "both_correct",
                    "both_incorrect",
                    "unresolved",
                    "unmatched",
                    "success_rate_improved",
                    "success_rate_regressed",
                    "success_rate_unchanged",
                ),
            ),
        ] = "any",
    ) -> ToolResult:
        """List aligned score transitions without exposing question content."""

        try:
            payload = self._critic.list_comparison_cases(
                page=page, page_size=page_size, transition=transition
            )
        except ValueError as exc:
            return ToolResult(
                name=self.name,
                content=f"COMPARISON_ERROR: {exc}",
                metadata={"error": str(exc)},
            )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> ListComparisonCasesTool:
    if config:
        raise ValueError("list_comparison_cases does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("list_comparison_cases requires a CriticContext")
    return ListComparisonCasesTool(context.runtime_context)
