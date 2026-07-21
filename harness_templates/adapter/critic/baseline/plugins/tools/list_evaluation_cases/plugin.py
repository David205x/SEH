"""Paginated evaluation case index for the Critic."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool


class ListEvaluationCasesTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.list_evaluation_cases)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="list_evaluation_cases")
    def list_evaluation_cases(
        self,
        page: Annotated[int, ToolArg("One-based result page.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Number of cases per page.", minimum=1, maximum=100),
        ] = 20,
        score: Annotated[
            int,
            ToolArg(
                "Question aggregate score filter; -1 means any, 1 means stable "
                "correct, and 0 means stable failure.",
                choices=(-1, 0, 1),
            ),
        ] = -1,
        run_status: Annotated[
            str,
            ToolArg(
                "Actor run status filter.",
                choices=(
                    "any",
                    "completed",
                    "invalid_output",
                    "max_steps_reached",
                    "tool_error",
                    "runner_error",
                    "mixed",
                ),
            ),
        ] = "any",
        has_retriever_error: Annotated[
            str,
            ToolArg(
                "Retriever error filter.",
                choices=("any", "true", "false"),
            ),
        ] = "any",
        stability: Annotated[
            str,
            ToolArg(
                "Question-level rollout stability filter.",
                choices=(
                    "any",
                    "stable_correct",
                    "stable_failure",
                    "unstable",
                    "unresolved",
                ),
            ),
        ] = "any",
    ) -> ToolResult:
        """List compact evaluation cases with filters and pagination metadata."""

        payload = self._critic.list_evaluation_cases(
            page=page,
            page_size=page_size,
            score=score,
            run_status=run_status,
            has_retriever_error=has_retriever_error,
            stability=stability,
        )
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> ListEvaluationCasesTool:
    if config:
        raise ValueError("list_evaluation_cases does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("list_evaluation_cases requires a CriticContext")
    return ListEvaluationCasesTool(context.runtime_context)
