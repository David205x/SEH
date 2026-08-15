"""Run one corrective retrieval when a non-binary question gets a null answer."""

from __future__ import annotations

import json
import re
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    FinalDecision,
    HookContext,
    HookModelRequest,
    HookPhase,
    ModelInput,
    ParsedOutput,
    StateRef,
    ToolCall,
)


_PREFIX = "extension.corrective_recovery."
_STATUS = _PREFIX + "status"
_QUERY = _PREFIX + "query"
_RETRIES = _PREFIX + "retries"

_QUERY_SYSTEM = """Plan one corrective corpus search for a factual question whose current
answer is invalid or unsupported. Do not answer the question. Return exactly one JSON object:
{"query":"concise standalone entity-centered query"}. Target the still-missing final relation,
reuse a bridge entity already exposed by previous queries when possible, preserve qualifiers and
relation direction, and do not repeat a previous query. Never use world knowledge."""

_RETRIEVAL_SYSTEM = """Execute the required corrective retrieval. Output exactly one block:
<tool_call>{"name":"search","arguments":{"query":"copy the required query","topk":5}}</tool_call>
Do not answer or alter the query."""

_SYNTHESIS_SYSTEM = """Answer the original factual question using only the raw retrieval
evidence. The previous null answer was invalid because this is not a yes/no question. Check the
requested answer type, relation direction, qualifiers, comparison attribute, and geographic
granularity. Do not output no, unknown, or an insufficiency statement. Output only the minimal
answer in exactly one block: <final_answer>answer only</final_answer>"""

_BINARY_START = re.compile(
    r"^\s*(?:are|is|was|were|do|does|did|can|could|have|has|had|will|would)\b",
    flags=re.IGNORECASE,
)
_NULL_ANSWERS = {
    "no",
    "unknown",
    "cannot determine",
    "insufficient evidence",
    "not enough information",
}


class CorrectiveRecoveryHook(BaseHook):
    """Exploit Qwen's query-planning strength without trusting a free-form verifier."""

    def __init__(self, *, topk: int, max_evidence_chars: int) -> None:
        self._topk = topk
        self._max_evidence_chars = max_evidence_chars
        hook_id = "corrective_recovery"
        super().__init__(
            hook_id=hook_id,
            phases=frozenset(
                {
                    HookPhase.POST_PROMPT,
                    HookPhase.POST_PARSE,
                    HookPhase.PRE_TOOL,
                    HookPhase.POST_TOOL,
                    HookPhase.PRE_FINAL,
                }
            ),
            state_refs=(
                StateRef(_STATUS, hook_id, str, frozenset({hook_id}), "idle"),
                StateRef(_QUERY, hook_id, str, frozenset({hook_id}), ""),
                StateRef(_RETRIES, hook_id, int, frozenset({hook_id}), 0),
            ),
            writable_stage_keys=frozenset(
                {
                    "stage.model_input",
                    "stage.parsed_output",
                    "stage.tool_call",
                    "stage.final_decision",
                }
            ),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        status = context.state.get(_STATUS)
        if context.phase == HookPhase.POST_PROMPT:
            self._project(context, status)
            return
        if context.phase == HookPhase.POST_PARSE and status == "awaiting_tool":
            context.state.set(
                "stage.parsed_output",
                ParsedOutput.for_tool_call(self._planned_call(context)),
            )
            return
        if context.phase == HookPhase.PRE_TOOL and status == "awaiting_tool":
            context.state.set("stage.tool_call", self._planned_call(context))
            return
        if context.phase == HookPhase.POST_TOOL and status == "awaiting_tool":
            context.state.set(_STATUS, "synthesis_pending")
            return
        if context.phase == HookPhase.PRE_FINAL:
            if status == "awaiting_final":
                context.state.set(_STATUS, "completed")
                return
            if status == "idle":
                self._recover_if_needed(context)

    def _recover_if_needed(self, context: HookContext) -> None:
        decision = context.state.get("stage.final_decision")
        core = context.state.get("core")
        if not isinstance(decision, FinalDecision) or not isinstance(core, dict):
            raise TypeError("corrective recovery requires final decision and core state")
        question = core.get("question")
        candidate = decision.answer
        if not isinstance(question, str) or not isinstance(candidate, str):
            raise TypeError("corrective recovery requires string question and answer")
        if _BINARY_START.match(question) or not _is_null_answer(candidate):
            return
        if context.state.get(_RETRIES) >= 1:
            return

        previous_queries = _previous_queries(core)
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="corrective_query_planning",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_QUERY_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Original question: {question}\n"
                                f"Rejected answer: {candidate}\n"
                                "Previous queries: "
                                + json.dumps(previous_queries, ensure_ascii=False)
                            ),
                        ),
                    ]
                ),
            )
        )
        query = _parse_query(response.raw_output)
        if not query or _normalized(query) in {_normalized(item) for item in previous_queries}:
            query = question
        context.state.set(_QUERY, query)
        context.state.set(_RETRIES, 1)
        context.state.set(_STATUS, "retrieval_pending")
        context.state.set(
            "stage.final_decision",
            FinalDecision.defer(
                "The prior answer had the wrong answer type. Run one focused corrective search."
            ),
        )

    def _project(self, context: HookContext, status: str) -> None:
        core = context.state.get("core")
        if not isinstance(core, dict):
            raise TypeError("corrective recovery requires core state")
        question = core.get("question")
        if status in {"retrieval_pending", "awaiting_tool"}:
            query = context.state.get(_QUERY)
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_RETRIEVAL_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=f"Original question: {question}\nRequired query: {query}",
                        ),
                    ]
                ),
            )
            context.state.set(_STATUS, "awaiting_tool")
            return
        if status in {"synthesis_pending", "awaiting_final"}:
            evidence = _render_evidence(core, self._max_evidence_chars)
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_SYNTHESIS_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Original question: {question}\n\n"
                                f"Raw retrieval evidence:\n{evidence}"
                            ),
                        ),
                    ]
                ),
            )
            context.state.set(_STATUS, "awaiting_final")

    def _planned_call(self, context: HookContext) -> ToolCall:
        query = context.state.get(_QUERY)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("corrective recovery has no query")
        return ToolCall("search", {"query": query.strip(), "topk": self._topk})


def _is_null_answer(candidate: str) -> bool:
    normalized = _normalized(candidate)
    return normalized in _NULL_ANSWERS or any(
        phrase in normalized
        for phrase in ("insufficient evidence", "cannot determine", "not enough information")
    )


def _parse_query(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        return ""
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError:
        return ""
    query = payload.get("query") if isinstance(payload, dict) else None
    return query.strip() if isinstance(query, str) else ""


def _previous_queries(core: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    for interaction in core.get("tool_interactions", []):
        if not isinstance(interaction, dict):
            continue
        call = interaction.get("tool_call") or {}
        query = (call.get("arguments") or {}).get("query")
        if isinstance(query, str) and query.strip():
            queries.append(query.strip())
    return queries


def _render_evidence(core: dict[str, Any], limit: int) -> str:
    blocks: list[str] = []
    for interaction in core.get("tool_interactions", []):
        if not isinstance(interaction, dict):
            continue
        call = interaction.get("tool_call") or {}
        result = interaction.get("tool_result") or {}
        query = (call.get("arguments") or {}).get("query", "")
        content = result.get("content", "")
        if isinstance(content, str):
            blocks.append(f"QUERY: {query}\n{content}")
    return "\n\n".join(blocks)[:limit]


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip().rstrip(".!"))


def build(config: dict[str, Any], context: Any) -> CorrectiveRecoveryHook:
    del context
    unknown = set(config) - {"topk", "max_evidence_chars"}
    if unknown:
        raise ValueError(f"corrective recovery has unsupported keys: {sorted(unknown)}")
    topk = config.get("topk", 5)
    max_evidence_chars = config.get("max_evidence_chars", 8000)
    if not isinstance(topk, int) or isinstance(topk, bool) or topk < 1:
        raise ValueError("topk must be a positive integer")
    if (
        not isinstance(max_evidence_chars, int)
        or isinstance(max_evidence_chars, bool)
        or max_evidence_chars < 1000
    ):
        raise ValueError("max_evidence_chars must be an integer >= 1000")
    return CorrectiveRecoveryHook(topk=topk, max_evidence_chars=max_evidence_chars)
