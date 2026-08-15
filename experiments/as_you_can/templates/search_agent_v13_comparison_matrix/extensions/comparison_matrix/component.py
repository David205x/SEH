"""Retrieve a symmetric two-column evidence matrix for explicit comparisons."""

from __future__ import annotations

from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookPhase,
    ModelInput,
    ParsedOutput,
    StateRef,
    ToolCall,
)

from experiments.as_you_can.templates.search_agent_v13_comparison_matrix.extensions.question_router.component import (
    PLAN_KEY,
    ROUTE_KEY,
)


_PREFIX = "extension.comparison_matrix."
_STATUS = _PREFIX + "status"
_INDEX = _PREFIX + "index"
_EVIDENCE = _PREFIX + "evidence"

_RETRIEVAL_SYSTEM = """Execute one side of a paired comparison retrieval. Output exactly:
<tool_call>{"name":"search","arguments":{"query":"copy required query","topk":5}}</tool_call>
Do not answer or alter the query."""

_SYNTHESIS_SYSTEM = """Answer the original comparison using only the paired raw evidence.
First establish exactly the same requested attribute for side A and side B, then apply the stated
comparison. Do not compare different attributes, publication versus founding dates, locations
versus nationalities, or a subject with a distractor. For a shared-property question return the
minimal shared value; for yes/no return exactly yes or no; otherwise return the named winning
option exactly as written in the question. Output exactly one block:
<final_answer>answer only</final_answer>"""


class ComparisonMatrixHook(BaseHook):
    def __init__(self, *, topk: int, max_evidence_chars: int) -> None:
        self._topk = topk
        self._max_evidence_chars = max_evidence_chars
        hook_id = "comparison_matrix"
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
                StateRef(_STATUS, hook_id, str, frozenset({hook_id}), "pending"),
                StateRef(_INDEX, hook_id, int, frozenset({hook_id}), 0),
                StateRef(_EVIDENCE, hook_id, list, frozenset({hook_id}), []),
            ),
            writable_stage_keys=frozenset(
                {"stage.model_input", "stage.parsed_output", "stage.tool_call"}
            ),
        )

    def handle(self, context: HookContext) -> None:
        if context.state.get(ROUTE_KEY) != "comparison":
            return
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
            self._record(context)
            return
        if context.phase == HookPhase.PRE_FINAL and status == "awaiting_final":
            context.state.set(_STATUS, "completed")

    def _project(self, context: HookContext, status: str) -> None:
        question = context.state.get("core.question")
        plan = context.state.get(PLAN_KEY)
        index = context.state.get(_INDEX)
        if not isinstance(question, str) or not isinstance(plan, dict):
            raise TypeError("comparison matrix state is invalid")
        if status in {"pending", "awaiting_tool"} and index < 2:
            field = "query_a" if index == 0 else "query_b"
            query = plan.get(field, "")
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_RETRIEVAL_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Original question: {question}\n"
                                f"Common attribute: {plan.get('attribute', '')}\n"
                                f"Required query: {query}"
                            ),
                        ),
                    ]
                ),
            )
            context.state.set(_STATUS, "awaiting_tool")
            return
        if status in {"synthesis_pending", "awaiting_final"}:
            evidence = context.state.get(_EVIDENCE)
            rendered = _render_evidence(evidence, self._max_evidence_chars)
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=_SYNTHESIS_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Original question: {question}\n"
                                f"Common attribute: {plan.get('attribute', '')}\n\n"
                                f"Paired raw evidence:\n{rendered}"
                            ),
                        ),
                    ]
                ),
            )
            context.state.set(_STATUS, "awaiting_final")

    def _planned_call(self, context: HookContext) -> ToolCall:
        plan = context.state.get(PLAN_KEY)
        index = context.state.get(_INDEX)
        field = "query_a" if index == 0 else "query_b"
        query = plan.get(field) if isinstance(plan, dict) else None
        if not isinstance(query, str) or not query.strip():
            raise ValueError("comparison matrix has no query")
        return ToolCall("search", {"query": query.strip(), "topk": self._topk})

    def _record(self, context: HookContext) -> None:
        result = context.state.get("stage.tool_result")
        content = getattr(result, "content", None)
        if not isinstance(content, str):
            raise TypeError("tool result must expose string content")
        evidence = context.state.get(_EVIDENCE)
        index = context.state.get(_INDEX)
        call = self._planned_call(context)
        context.state.set(
            _EVIDENCE,
            [*evidence, {"side": index + 1, "query": call.arguments["query"], "result": content}],
        )
        context.state.set(_INDEX, index + 1)
        context.state.set(_STATUS, "pending" if index + 1 < 2 else "synthesis_pending")


def _render_evidence(evidence: list[object], limit: int) -> str:
    blocks = []
    for item in evidence:
        if isinstance(item, dict):
            blocks.append(
                f"SIDE {item.get('side')}; QUERY: {item.get('query', '')}\n{item.get('result', '')}"
            )
    return "\n\n".join(blocks)[:limit]


def build(config: dict[str, Any], context: Any) -> ComparisonMatrixHook:
    del context
    unknown = set(config) - {"topk", "max_evidence_chars"}
    if unknown:
        raise ValueError(f"comparison matrix has unsupported keys: {sorted(unknown)}")
    topk = config.get("topk", 5)
    max_evidence_chars = config.get("max_evidence_chars", 7000)
    if not isinstance(topk, int) or isinstance(topk, bool) or topk < 1:
        raise ValueError("topk must be a positive integer")
    if not isinstance(max_evidence_chars, int) or max_evidence_chars < 1000:
        raise ValueError("max_evidence_chars must be an integer >= 1000")
    return ComparisonMatrixHook(topk=topk, max_evidence_chars=max_evidence_chars)
