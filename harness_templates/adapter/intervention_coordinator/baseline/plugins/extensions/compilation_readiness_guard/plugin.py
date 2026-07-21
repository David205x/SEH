"""Prevent unsupported Coordinator conclusions from reaching the Compiler."""

from __future__ import annotations

import json
from typing import Any

from search_harness.adapter.intervention import (
    InterventionCoordinatorContext,
    InterventionCoordinatorResult,
)
from search_harness.core import BaseHook, FinalDecision, HookContext, HookPhase


class CompilationReadinessGuard(BaseHook):
    """Require measured cross-case and revision evidence before support."""

    def __init__(self, coordinator: InterventionCoordinatorContext) -> None:
        self._coordinator = coordinator
        super().__init__(
            hook_id="compilation_readiness_guard",
            phases=frozenset({HookPhase.PRE_FINAL}),
            writable_stage_keys=frozenset({"stage.final_decision"}),
        )

    def handle(self, context: HookContext) -> None:
        decision = context.state.get("stage.final_decision")
        if not isinstance(decision, FinalDecision) or decision.answer is None:
            raise TypeError("stage.final_decision must contain an accepted answer")
        try:
            payload = json.loads(decision.answer)
            result = InterventionCoordinatorResult.from_dict(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._defer(
                context,
                "The final answer does not match the required Coordinator JSON "
                f"schema ({type(exc).__name__}: {exc}). Return exactly one JSON object "
                "with analysis, verdict, selected_trial_id, and recommendation; do not "
                "add fields or wrap it in Markdown.",
            )
            return
        if result.verdict != "supported":
            return

        completed = [
            trial for trial in self._coordinator.trials
            if trial.get("status") == "completed"
        ]
        selected = next(
            (
                trial for trial in completed
                if trial.get("trial_id") == result.selected_trial_id
            ),
            None,
        )
        if selected is None:
            self._defer(context, "A supported result must select a completed trial.")
            return

        if self._coordinator.report_dir is not None:
            positive_examples = {
                str(trial.get("example_id"))
                for trial in completed
                if _resolved_score(trial) == 1
            }
            if len(positive_examples) < 2:
                self._defer(
                    context,
                    "Before declaring support, obtain positive measured results on at "
                    "least two distinct failed examples, or return inconclusive.",
                )
                return
            reusable_examples = _reusable_positive_examples(completed)
            if len(reusable_examples) < 2:
                self._defer(
                    context,
                    "Before declaring support, run the same non-empty generic Hook "
                    "guidance unchanged on at least two distinct failed examples. "
                    "Case-specific successful instructions do not establish a "
                    "compilable mechanism.",
                )
                return

        if self._coordinator.compiler_feedback is not None:
            positive_new = [
                trial for trial in self._coordinator.new_trials
                if trial.get("status") == "completed" and _resolved_score(trial) == 1
            ]
            if not positive_new:
                self._defer(
                    context,
                    "The Compiler requested clarification. Run at least one new positive "
                    "trial that directly tests the generalized implementation requested "
                    "by that feedback, or return inconclusive.",
                )

    @staticmethod
    def _defer(context: HookContext, feedback: str) -> None:
        context.state.set("stage.final_decision", FinalDecision.defer(feedback))


def _resolved_score(trial: dict[str, Any]) -> int | None:
    comparison = trial.get("comparison")
    if not isinstance(comparison, dict):
        return None
    branch = comparison.get("branch")
    if not isinstance(branch, dict):
        return None
    score = branch.get("score")
    return score if score in {0, 1} else None


def _reusable_positive_examples(trials: list[dict[str, Any]]) -> set[str]:
    """Return examples sharing one unchanged, non-empty successful Hook scheme."""

    examples_by_guidance: dict[str, set[str]] = {}
    for trial in trials:
        if _resolved_score(trial) != 1:
            continue
        guidance = trial.get("hook_guidance")
        if not isinstance(guidance, dict) or not guidance:
            continue
        normalized = json.dumps(guidance, ensure_ascii=False, sort_keys=True)
        examples_by_guidance.setdefault(normalized, set()).add(
            str(trial.get("example_id"))
        )
    return max(examples_by_guidance.values(), key=len, default=set())


def build(config: dict[str, Any], context: Any) -> CompilationReadinessGuard:
    """Build the fixed Coordinator reliability guard."""

    if config:
        raise ValueError("compilation_readiness_guard does not accept configuration")
    runtime = getattr(context, "runtime_context", None)
    if not isinstance(runtime, InterventionCoordinatorContext):
        raise TypeError("compilation_readiness_guard requires Coordinator context")
    return CompilationReadinessGuard(runtime)
