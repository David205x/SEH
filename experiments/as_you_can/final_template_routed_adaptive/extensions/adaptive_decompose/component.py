"""Evidence-adaptive retrieval decomposition driven only by the Student model."""

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
    ParsedOutput,
    StateRef,
    ToolCall,
)


_PREFIX = "extension.adaptive_decompose."
_STATUS = _PREFIX + "status"
_DECISION = _PREFIX + "decision"
_EVIDENCE = _PREFIX + "evidence"
_COUNT = _PREFIX + "search_count"
_ERRORS = _PREFIX + "decision_errors"
_ROUTE = "shared.question_route"

_DECISION_SYSTEM = """You are an answer-neutral retrieval controller for a factual question.
Do not answer the question. Select the next evidence obligation after inspecting retrieved text.
Return only one JSON object. If another search is needed, use:
{"action":"search","goal":"answer-neutral evidence obligation","query":"concise standalone entity-centered query","answer_type":"expected type","target_relation":"requested relation","evidence_summary":"what is established and what remains unknown"}
If the evidence is sufficient, use the same fields but set action to "synthesize" and query to "".
On the first decision you must search. Never put a proposed final answer in any field. Preserve
relation direction, qualifiers, time, comparison attribute, and requested place granularity.
After evidence identifies a bridge entity, use that exact entity in the next query. Avoid repeating
a query, and synthesize as soon as evidence directly supports the requested answer."""

_RETRIEVAL_SYSTEM = """Execute the required retrieval action. Output exactly one block and nothing else:
<tool_call>{"name":"search","arguments":{"query":"copy the required query","topk":5}}</tool_call>
Do not answer the question or alter the query."""

_SYNTHESIS_SYSTEM = """Answer the original short factual question using only the supplied retrieval
evidence. Check relation direction, expected answer type, qualifiers, time, comparison attribute,
and place granularity. Do not return a bridge entity when its property is requested. Missing
evidence is not evidence for no. For yes/no output exactly yes or no; otherwise output only the
minimal answer, preserving full proper names when supported. Return exactly one block:
<final_answer>answer only</final_answer>"""


class AdaptiveDecomposeHook(BaseHook):
    """Choose each search after seeing the preceding retrieval result."""

    def __init__(self, *, max_searches: int, topk: int, max_evidence_chars: int) -> None:
        self._max_searches = max_searches
        self._topk = topk
        self._max_evidence_chars = max_evidence_chars
        hook_id = "adaptive_decompose"
        super().__init__(
            hook_id=hook_id,
            phases=frozenset(
                {
                    HookPhase.PRE_PROMPT,
                    HookPhase.POST_PROMPT,
                    HookPhase.POST_PARSE,
                    HookPhase.PRE_TOOL,
                    HookPhase.POST_TOOL,
                    HookPhase.PRE_FINAL,
                }
            ),
            state_refs=(
                StateRef(_STATUS, hook_id, str, frozenset({hook_id}), "need_decision"),
                StateRef(_DECISION, hook_id, dict, frozenset({hook_id}), {}),
                StateRef(_EVIDENCE, hook_id, list, frozenset({hook_id}), []),
                StateRef(_COUNT, hook_id, int, frozenset({hook_id}), 0),
                StateRef(_ERRORS, hook_id, list, frozenset({hook_id}), []),
            ),
            writable_stage_keys=frozenset(
                {"stage.model_input", "stage.parsed_output", "stage.tool_call"}
            ),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        if context.state.get(_ROUTE, "decompose") == "delegate":
            return
        status = context.state.get(_STATUS)
        if context.phase == HookPhase.PRE_PROMPT:
            if status == "need_decision":
                self._decide(context)
            return
        if context.phase == HookPhase.POST_PROMPT:
            self._project_context(context, status)
            return
        if context.phase == HookPhase.POST_PARSE:
            if status == "awaiting_tool":
                context.state.set(
                    "stage.parsed_output",
                    ParsedOutput.for_tool_call(self._planned_call(context)),
                )
            return
        if context.phase == HookPhase.PRE_TOOL:
            if status == "awaiting_tool":
                context.state.set("stage.tool_call", self._planned_call(context))
            return
        if context.phase == HookPhase.POST_TOOL:
            if status == "awaiting_tool":
                self._record_result(context)
            return
        if context.phase == HookPhase.PRE_FINAL:
            if status == "awaiting_final":
                context.state.set(_STATUS, "completed")
            return

    def _decide(self, context: HookContext) -> None:
        question = context.state.get("core.question")
        evidence = context.state.get(_EVIDENCE)
        count = context.state.get(_COUNT)
        if not isinstance(question, str) or not isinstance(evidence, list):
            raise TypeError("adaptive controller state is invalid")
        if count >= self._max_searches:
            context.state.set(
                _DECISION,
                {
                    "action": "synthesize",
                    "goal": "Answer from the retrieved evidence.",
                    "query": "",
                    "answer_type": "",
                    "target_relation": "",
                    "evidence_summary": "Search budget exhausted.",
                },
            )
            context.state.set(_STATUS, "synthesis_pending")
            return

        evidence_text = self._render_evidence(evidence)
        user = (
            f"Original question: {question}\n"
            f"Searches used: {count}/{self._max_searches}\n"
            f"Retrieved evidence:\n{evidence_text or '(none yet)'}"
        )
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="adaptive_retrieval_decision",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_DECISION_SYSTEM),
                        ChatMessage(role="user", content=user),
                    ]
                ),
            )
        )
        try:
            decision = _parse_decision(response.raw_output, must_search=count == 0)
        except ValueError as exc:
            errors = context.state.get(_ERRORS)
            context.state.set(_ERRORS, [*errors, str(exc)])
            decision = (
                {
                    "action": "search",
                    "goal": "Retrieve direct evidence for the original question.",
                    "query": question,
                    "answer_type": "",
                    "target_relation": "",
                    "evidence_summary": "",
                }
                if count == 0
                else {
                    "action": "synthesize",
                    "goal": "Answer from the retrieved evidence.",
                    "query": "",
                    "answer_type": "",
                    "target_relation": "",
                    "evidence_summary": "Decision parse fallback.",
                }
            )
        context.state.set(_DECISION, decision)
        context.state.set(
            _STATUS,
            "subtask_pending" if decision["action"] == "search" else "synthesis_pending",
        )

    def _project_context(self, context: HookContext, status: str) -> None:
        question = context.state.get("core.question")
        decision = context.state.get(_DECISION)
        if status in {"subtask_pending", "awaiting_tool"}:
            user = (
                f"Original question: {question}\n"
                f"Evidence obligation: {decision.get('goal', '')}\n"
                f"Required query: {decision.get('query', '')}\n"
                f"Required topk: {self._topk}"
            )
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_RETRIEVAL_SYSTEM),
                        ChatMessage(role="user", content=user),
                    ]
                ),
            )
            context.state.set(_STATUS, "awaiting_tool")
            return
        if status in {"synthesis_pending", "awaiting_final"}:
            evidence = context.state.get(_EVIDENCE)
            control = json.dumps(decision, ensure_ascii=False, separators=(",", ":"))
            user = (
                f"Original question: {question}\n"
                f"Controller analysis (not itself evidence): {control}\n\n"
                f"Retrieved evidence:\n{self._render_evidence(evidence)}"
            )
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_SYNTHESIS_SYSTEM),
                        ChatMessage(role="user", content=user),
                    ]
                ),
            )
            context.state.set(_STATUS, "awaiting_final")

    def _planned_call(self, context: HookContext) -> ToolCall:
        decision = context.state.get(_DECISION)
        query = decision.get("query") if isinstance(decision, dict) else None
        if not isinstance(query, str) or not query.strip():
            raise ValueError("adaptive search decision has no query")
        return ToolCall("search", {"query": query.strip(), "topk": self._topk})

    def _record_result(self, context: HookContext) -> None:
        result = context.state.get("stage.tool_result")
        content = getattr(result, "content", None)
        if not isinstance(content, str):
            raise TypeError("tool result must expose string content")
        decision = context.state.get(_DECISION)
        evidence = context.state.get(_EVIDENCE)
        count = context.state.get(_COUNT)
        context.state.set(
            _EVIDENCE,
            [
                *evidence,
                {
                    "goal": decision.get("goal", ""),
                    "query": decision.get("query", ""),
                    "result": content,
                },
            ],
        )
        context.state.set(_COUNT, count + 1)
        context.state.set(_STATUS, "need_decision")

    def _render_evidence(self, evidence: list[object]) -> str:
        blocks: list[str] = []
        remaining = self._max_evidence_chars
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict) or remaining <= 0:
                continue
            block = (
                f"Evidence {index}; goal={item.get('goal', '')}; "
                f"query={item.get('query', '')}:\n{item.get('result', '')}"
            )[:remaining]
            blocks.append(block)
            remaining -= len(block)
        return "\n\n".join(blocks)


def _parse_decision(raw: str, *, must_search: bool) -> dict[str, str]:
    start = raw.find("{")
    if start < 0:
        raise ValueError("decision output contains no JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid decision JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("decision JSON must be an object")
    action = payload.get("action")
    if action not in {"search", "synthesize"} or (must_search and action != "search"):
        raise ValueError("decision action is invalid for the current stage")
    fields = ("goal", "query", "answer_type", "target_relation", "evidence_summary")
    result = {
        field: payload.get(field, "").strip()
        if isinstance(payload.get(field, ""), str)
        else ""
        for field in fields
    }
    result["action"] = action
    if action == "search" and not result["query"]:
        raise ValueError("search decision must include a query")
    if action == "synthesize":
        result["query"] = ""
    return result


def build(config: dict[str, Any], context: Any) -> AdaptiveDecomposeHook:
    del context
    unknown = set(config) - {"max_searches", "topk", "max_evidence_chars"}
    if unknown:
        raise ValueError(f"adaptive decompose has unsupported keys: {sorted(unknown)}")
    values = {
        key: _positive(config.get(key, default), key)
        for key, default in (
            ("max_searches", 2),
            ("topk", 5),
            ("max_evidence_chars", 6000),
        )
    }
    return AdaptiveDecomposeHook(**values)


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value
