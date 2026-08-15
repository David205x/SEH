"""Route structurally simple/comparison questions away from decomposition."""

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


ROUTE_KEY = "shared.question_route"

SYSTEM = """Classify only the reasoning structure of a factual question. Do not answer it.
Return exactly one JSON object: {"mode":"delegate"} or {"mode":"decompose"}.
- delegate: a direct one-relation lookup, or a comparison/shared-property question that must
  evaluate the same attribute for two explicitly given subjects.
- decompose: answering requires first resolving an intermediate entity/event/work/person and
  then retrieving a property or relation of that resolved bridge.
Examples: 'Which is older, A or B?' is delegate. 'Do A and B share a nationality?' is delegate.
'What city was the author of Book X born in?' is decompose. Never use world knowledge."""


class QuestionRouterHook(BaseHook):
    def __init__(self) -> None:
        hook_id = "question_router"
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.PRE_PROMPT}),
            state_refs=(
                StateRef(
                    ROUTE_KEY,
                    hook_id,
                    str,
                    frozenset({hook_id}),
                    "unknown",
                ),
            ),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        if context.state.get(ROUTE_KEY) != "unknown":
            return
        question = context.state.get("core.question")
        if not isinstance(question, str):
            raise TypeError("core.question must be a string")
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="question_structure_route",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=SYSTEM),
                        ChatMessage(role="user", content=question),
                    ]
                ),
            )
        )
        try:
            route = _parse_route(response.raw_output)
        except ValueError:
            route = "decompose"
        context.state.set(ROUTE_KEY, route)


def _parse_route(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        raise ValueError("router output contains no JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid router JSON: {exc.msg}") from exc
    mode = payload.get("mode") if isinstance(payload, dict) else None
    if mode not in {"delegate", "decompose"}:
        raise ValueError(f"invalid router mode: {mode!r}")
    return mode


def build(config: dict[str, Any], context: Any) -> QuestionRouterHook:
    del context
    if config:
        raise ValueError("question_router does not accept configuration")
    return QuestionRouterHook()
