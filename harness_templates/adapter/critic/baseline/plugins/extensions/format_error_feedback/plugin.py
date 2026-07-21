"""Detailed tagged-output diagnostics for invalid Critic responses."""

from __future__ import annotations

from typing import Any

from search_harness.core import (
    BaseHook,
    HookContext,
    HookPhase,
    ParsedOutput,
    ParsedOutputKind,
)


class FormatErrorFeedbackHook(BaseHook):
    """Replace a generic invalid parse error with concrete tag diagnostics."""

    def __init__(self, hook_id: str = "format_error_feedback") -> None:
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.POST_PARSE}),
            writable_stage_keys=frozenset({"stage.parsed_output"}),
        )

    def handle(self, context: HookContext) -> None:
        parser_input = context.state.get("stage.parser_input")
        parsed_output = context.state.get("stage.parsed_output")
        if not isinstance(parser_input, str):
            raise TypeError("stage.parser_input must be a string")
        if not isinstance(parsed_output, ParsedOutput):
            raise TypeError("stage.parsed_output must be ParsedOutput")
        if parsed_output.kind is not ParsedOutputKind.INVALID:
            return

        diagnostics = _diagnose_tags(parser_input)
        if not diagnostics:
            return
        detail = "; ".join(dict.fromkeys(diagnostics))
        base_error = parsed_output.error or "model output did not match expected schema"
        context.state.set(
            "stage.parsed_output",
            ParsedOutput.invalid(
                error=f"{base_error}. Specific format issue: {detail}",
                inband_thinking=parsed_output.inband_thinking,
            ),
        )


def _diagnose_tags(parser_input: str) -> list[str]:
    diagnostics: list[str] = []
    if "<tool_use>" in parser_input or "</tool_use>" in parser_input:
        diagnostics.append("the supported tool tag is <tool_call>, not <tool_use>")
    for tag in ("tool_call", "final_answer"):
        opening = parser_input.count(f"<{tag}>")
        closing = parser_input.count(f"</{tag}>")
        if opening > closing:
            diagnostics.append(f"<{tag}> is missing </{tag}>")
        elif closing > opening:
            diagnostics.append(f"</{tag}> is missing <{tag}>")
    return diagnostics


def build(config: dict[str, Any], context: Any) -> FormatErrorFeedbackHook:
    """Create the Critic format diagnostic hook."""

    del context
    if config:
        raise ValueError("format_error_feedback does not accept configuration")
    return FormatErrorFeedbackHook()
