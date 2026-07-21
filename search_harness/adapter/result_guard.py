"""Fixed PRE_FINAL guard for structured Adapter role results."""

from __future__ import annotations

from collections.abc import Callable

from search_harness.core import (
    BaseHook,
    FinalDecision,
    FinalDecisionAction,
    HookContext,
    HookPhase,
)


class StructuredResultGuard(BaseHook):
    """Defer a final answer until one role-specific parser accepts its schema."""

    def __init__(
        self,
        *,
        hook_id: str,
        role_name: str,
        parser: Callable[[str], object],
        shape_hint: str,
    ) -> None:
        self._role_name = role_name
        self._parser = parser
        self._shape_hint = shape_hint
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.PRE_FINAL}),
            writable_stage_keys=frozenset({"stage.final_decision"}),
        )

    def handle(self, context: HookContext) -> None:
        decision = context.state.get("stage.final_decision")
        if not isinstance(decision, FinalDecision):
            raise TypeError(
                f"{self._role_name} PRE_FINAL decision must be FinalDecision"
            )
        if decision.action is FinalDecisionAction.DEFER:
            return
        if decision.answer is None:
            raise ValueError(f"{self._role_name} final decision has no answer")
        try:
            self._parser(decision.answer)
        except (TypeError, ValueError) as exc:
            context.state.set(
                "stage.final_decision",
                FinalDecision.defer(
                    f"Your {self._role_name} <final_answer> violates its required "
                    f"result schema: {exc}. Rewrite the complete result; do not fill "
                    "required fields with guessed defaults, omit fields, add fields, "
                    "or wrap the JSON in Markdown. Required shape: "
                    f"{self._shape_hint}"
                ),
            )
