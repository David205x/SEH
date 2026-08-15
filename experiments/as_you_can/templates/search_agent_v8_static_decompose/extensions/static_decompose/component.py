"""Static two-step decomposition with deterministic execution of planned searches."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_templates.experiments.decomposed_context_student.plugins.extensions.decomposed_context_controller import plugin as upstream
from search_harness.framework import ParsedOutput, ToolCall


class StaticDecomposeHook(upstream.DecomposedContextControllerHook):
    """Project every retrieval-stage generation onto the current planned call."""

    def _bridge_bare_tool_json(self, context: Any, status: str) -> None:
        if status != "awaiting_tool":
            return
        plan = context.state.get(upstream._PLAN)
        index = context.state.get(upstream._INDEX)
        subtask = upstream._current_subtask(plan, index)
        context.state.set(
            "stage.parsed_output",
            ParsedOutput.for_tool_call(
                ToolCall(
                    name="search",
                    arguments={"query": subtask["query"], "topk": self._topk},
                )
            ),
        )


def build(config: dict[str, Any], context: Any) -> StaticDecomposeHook:
    allowed = {
        "planner_prompt_file",
        "subtask_system_prompt_file",
        "synthesis_system_prompt_file",
        "max_subtasks",
        "topk",
        "max_evidence_chars",
    }
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"static decompose has unsupported keys: {sorted(unknown)}")
    return StaticDecomposeHook(
        planner_prompt=_load(context, config.get("planner_prompt_file")),
        subtask_system_prompt=_load(context, config.get("subtask_system_prompt_file")),
        synthesis_system_prompt=_load(context, config.get("synthesis_system_prompt_file")),
        max_subtasks=_positive(config.get("max_subtasks", 2), "max_subtasks"),
        topk=_positive(config.get("topk", 5), "topk"),
        max_evidence_chars=_positive(
            config.get("max_evidence_chars", 5000), "max_evidence_chars"
        ),
    )


def _load(context: Any, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("prompt file must be a non-empty string")
    root = getattr(context, "template_root", None)
    if not isinstance(root, Path):
        raise TypeError("static decompose requires ComponentFactoryContext.template_root")
    path = (root / value).resolve()
    path.relative_to(root.resolve())
    return path.read_text(encoding="utf-8")


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value
