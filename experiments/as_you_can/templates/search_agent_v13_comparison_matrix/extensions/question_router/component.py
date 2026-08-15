"""Route explicit two-subject comparisons into a paired-evidence workflow."""

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
PLAN_KEY = "shared.comparison_plan"

SYSTEM = """Classify only the reasoning structure of a factual question. Do not answer it.
Return exactly one JSON object.
- For an explicit two-subject comparison or shared-property question, return
  {"mode":"comparison","attribute":"same attribute to establish","query_a":"first subject plus attribute","query_b":"second subject plus attribute"}.
  Each query must be concise, standalone, answer-neutral, and evaluate the same attribute.
- For a direct one-relation lookup, return {"mode":"delegate"}.
- If the final property can only be searched after resolving an intermediate entity, work,
  event, or person, return {"mode":"decompose"}.
Examples: 'Which is older, A or B?' and 'Do A and B share a nationality?' are comparison.
'What city was the author of Book X born in?' is decompose. Never use world knowledge."""


class ThreeWayRouterHook(BaseHook):
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
                StateRef(
                    PLAN_KEY,
                    hook_id,
                    dict,
                    frozenset({hook_id}),
                    {},
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
                purpose="three_way_question_structure_route",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=SYSTEM),
                        ChatMessage(role="user", content=question),
                    ]
                ),
            )
        )
        try:
            route, plan = _parse(response.raw_output)
        except ValueError:
            route, plan = "decompose", {}
        context.state.set(ROUTE_KEY, route)
        context.state.set(PLAN_KEY, plan)


def _parse(raw: str) -> tuple[str, dict[str, str]]:
    start = raw.find("{")
    if start < 0:
        raise ValueError("router output contains no JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid router JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("router JSON must be an object")
    mode = payload.get("mode")
    if mode not in {"delegate", "decompose", "comparison"}:
        raise ValueError(f"invalid router mode: {mode!r}")
    if mode != "comparison":
        return mode, {}
    fields = ("attribute", "query_a", "query_b")
    plan = {
        field: payload.get(field, "").strip()
        if isinstance(payload.get(field), str)
        else ""
        for field in fields
    }
    if not plan["query_a"] or not plan["query_b"]:
        raise ValueError("comparison plan lacks paired queries")
    return mode, plan


def build(config: dict[str, Any], context: Any) -> ThreeWayRouterHook:
    del context
    if config:
        raise ValueError("question_router does not accept configuration")
    return ThreeWayRouterHook()
