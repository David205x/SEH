"""Inject a one-time reflection instruction after every completed tool call."""

from __future__ import annotations

from typing import Any

from search_harness.core import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookPhase,
    ModelInput,
    StateRef,
)


_PENDING_KEY = "extension.result_summary_prompt.pending"
_INSTRUCTION = "The available information may be insufficient. Please expand the search scope and increase the recall quantity to make a more accurate determination."


class ResultSummaryPromptHook(BaseHook):
    """Request reflection on the tool result in the next model input."""

    def __init__(self, hook_id: str = "result_summary_prompt") -> None:
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.POST_TOOL, HookPhase.POST_PROMPT}),
            state_refs=(
                StateRef(
                    key=_PENDING_KEY,
                    owner=hook_id,
                    value_type=bool,
                    writers=frozenset({hook_id}),
                    default=False,
                ),
            ),
            writable_stage_keys=frozenset({"stage.model_input"}),
        )

    def handle(self, context: HookContext) -> None:
        """Set the marker after a tool, then consume it when the next prompt exists."""

        if context.phase == HookPhase.POST_TOOL:
            context.state.set(_PENDING_KEY, True)
            return

        if not context.state.get(_PENDING_KEY):
            return

        model_input = context.state.get("stage.model_input")
        if not isinstance(model_input, ModelInput):
            raise TypeError("stage.model_input must be a ModelInput")
        context.state.set(
            "stage.model_input",
            ModelInput.from_messages(
                [*model_input.messages, ChatMessage(role="user", content=_INSTRUCTION)]
            ),
        )
        context.state.set(_PENDING_KEY, False)


def build(config: dict[str, Any], context: Any) -> ResultSummaryPromptHook:
    """Create the hook; its instruction is intentionally fixed in this baseline."""

    del context
    if config:
        raise ValueError("result_summary_prompt does not accept configuration")
    return ResultSummaryPromptHook()
