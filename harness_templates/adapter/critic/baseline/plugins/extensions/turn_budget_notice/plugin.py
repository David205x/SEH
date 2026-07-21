"""Inject the current Critic turn budget into the model input."""

from __future__ import annotations

from typing import Any

from search_harness.core import BaseHook, ChatMessage, HookContext, HookPhase, ModelInput


class TurnBudgetNoticeHook(BaseHook):
    """Append a per-turn budget reminder immediately before model generation."""

    def __init__(self, hook_id: str = "turn_budget_notice") -> None:
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.POST_PROMPT}),
            writable_stage_keys=frozenset({"stage.model_input"}),
        )

    def handle(self, context: HookContext) -> None:
        model_input = context.state.get("stage.model_input")
        step = context.state.get("core.step")
        max_steps = context.state.get("core.max_steps")
        if not isinstance(model_input, ModelInput):
            raise TypeError("stage.model_input must be ModelInput")
        if not isinstance(step, int) or not isinstance(max_steps, int):
            raise TypeError("core.step and core.max_steps must be integers")

        notice = f"Turn budget: this is step {step} of {max_steps}."
        if step == max_steps:
            notice += (
                " This is the final allowed turn. Complete the current analysis and "
                "return <final_answer>; do not call another tool."
            )
        updated_messages = [*model_input.messages, ChatMessage(role="user", content=notice)]
        context.state.set("stage.model_input", ModelInput.from_messages(updated_messages))


def build(config: dict[str, Any], context: Any) -> TurnBudgetNoticeHook:
    """Create the Critic turn-budget prompt hook."""

    del context
    if config:
        raise ValueError("turn_budget_notice does not accept configuration")
    return TurnBudgetNoticeHook()
