"""Create and persist an answer-neutral structural rewrite of the question."""

from __future__ import annotations

import json
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookModelRequest,
    HookPhase,
    ModelInput,
    StateRef,
)


_ANALYSIS = "extension.question_rewrite.analysis"
_READY = "extension.question_rewrite.ready"
_ERROR = "extension.question_rewrite.error"

_REWRITE_PROMPT = """You normalize a factual retrieval question before another agent searches.
Do not answer the question. Do not add world knowledge, candidate answers, evidence, or facts not
explicitly stated in the question. Preserve every constraint and relation direction. Return only
one JSON object with these string fields:
- resolved_question: a concise self-contained rewrite with an explicit unknown answer slot
- answer_type: expected semantic type such as person, place, date, number, yes/no, or option
- target_relation: the exact relation/property ultimately requested
- known_entities: comma-separated entities explicitly present in the question
- bridge_unknown: any intermediate entity/relation that must be resolved, or an empty string
- search_focus: a short answer-neutral description of what evidence retrieval must establish
Use empty strings when a field is not applicable."""


class QuestionRewriteHook(BaseHook):
    """Call the same Student once, then inject its structural view on every turn."""

    def __init__(self) -> None:
        hook_id = "question_rewrite"
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.POST_PROMPT}),
            state_refs=(
                StateRef(_ANALYSIS, hook_id, dict, frozenset({hook_id}), {}),
                StateRef(_READY, hook_id, bool, frozenset({hook_id}), False),
                StateRef(_ERROR, hook_id, str, frozenset({hook_id}), ""),
            ),
            writable_stage_keys=frozenset({"stage.model_input"}),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        model_input = context.state.get("stage.model_input")
        question = context.state.get("core.question")
        if not isinstance(model_input, ModelInput) or not isinstance(question, str):
            raise TypeError("question rewrite requires ModelInput and string question")

        if not context.state.get(_READY):
            response = context.call_model(
                HookModelRequest(
                    profile="student",
                    purpose="answer_neutral_question_rewrite",
                    model_input=ModelInput.from_messages(
                        [
                            ChatMessage(role="system", content=_REWRITE_PROMPT),
                            ChatMessage(role="user", content=question),
                        ]
                    ),
                )
            )
            try:
                analysis = _parse_analysis(response.raw_output)
            except ValueError as exc:
                analysis = {}
                context.state.set(_ERROR, str(exc))
            context.state.set(_ANALYSIS, analysis)
            context.state.set(_READY, True)
        else:
            analysis = context.state.get(_ANALYSIS)

        if not analysis:
            return
        control = (
            "\n\nQuestion structure (generated only from the original wording; this is not "
            "retrieval evidence and never supplies the answer):\n"
            + json.dumps(analysis, ensure_ascii=False, separators=(",", ":"))
            + "\nThe original question remains authoritative. Search for evidence before answering."
        )
        messages = list(model_input.messages)
        for index, message in enumerate(messages):
            if message.role == "system":
                messages[index] = ChatMessage(
                    role="system", content=message.content + control
                )
                break
        context.state.set("stage.model_input", ModelInput.from_messages(messages))


def _parse_analysis(raw: str) -> dict[str, str]:
    start = raw.find("{")
    if start < 0:
        raise ValueError("rewrite output contains no JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid rewrite JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("rewrite JSON must be an object")
    fields = (
        "resolved_question",
        "answer_type",
        "target_relation",
        "known_entities",
        "bridge_unknown",
        "search_focus",
    )
    result = {
        key: value.strip()
        for key in fields
        if isinstance((value := payload.get(key)), str) and value.strip()
    }
    if not result.get("resolved_question") or not result.get("target_relation"):
        raise ValueError("rewrite JSON lacks resolved_question or target_relation")
    return result


def build(config: dict[str, Any], context: Any) -> QuestionRewriteHook:
    del context
    if config:
        raise ValueError("question_rewrite does not accept configuration")
    return QuestionRewriteHook()
