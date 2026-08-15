"""Search-o1 style focused reasoning over every retrieved document group."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookModelRequest,
    HookPhase,
    ModelInput,
    ToolCall,
    ToolResult,
)


class ForceTopKHook(BaseHook):
    def __init__(self, topk: int) -> None:
        self._topk = topk
        super().__init__(
            hook_id="force_topk",
            phases=frozenset({HookPhase.PRE_TOOL}),
            writable_stage_keys=frozenset({"stage.tool_call"}),
        )

    def handle(self, context: HookContext) -> None:
        call = context.state.get("stage.tool_call")
        if not isinstance(call, ToolCall):
            raise TypeError("stage.tool_call must be a ToolCall")
        if call.name != "search":
            return
        arguments = dict(call.arguments)
        arguments["topk"] = self._topk
        context.state.set("stage.tool_call", ToolCall(name=call.name, arguments=arguments))


class ReasonInDocumentsHook(BaseHook):
    def __init__(
        self,
        *,
        prompt: str,
        max_history_chars: int,
        max_document_chars: int,
    ) -> None:
        self._prompt = prompt.strip()
        self._max_history_chars = max_history_chars
        self._max_document_chars = max_document_chars
        super().__init__(
            hook_id="reason_in_documents",
            phases=frozenset({HookPhase.POST_TOOL}),
            writable_stage_keys=frozenset({"stage.tool_result"}),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        call = context.state.get("stage.tool_call")
        result = context.state.get("stage.tool_result")
        if not isinstance(call, ToolCall) or not isinstance(result, ToolResult):
            raise TypeError("document reasoner requires ToolCall and ToolResult")
        if call.name != "search" or result.name != "search":
            return
        query = call.arguments.get("query")
        question = context.state.get("core.question")
        core = context.state.get("core")
        if not isinstance(query, str) or not isinstance(question, str) or not isinstance(core, dict):
            raise TypeError("document reasoner requires query, question, and core state")
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="reason_in_retrieved_documents",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=self._prompt),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Original question:\n{question}\n\n"
                                f"Current query:\n{query}\n\n"
                                f"Previous evidence/reasoning:\n"
                                f"{_history(core, self._max_history_chars)}\n\n"
                                f"Retrieved passages:\n"
                                f"{_retain_edges(result.content, self._max_document_chars)}"
                            ),
                        ),
                    ]
                ),
            )
        )
        payload = _parse_object(response.raw_output)
        if not _valid_analysis(payload):
            return
        metadata = dict(result.metadata)
        metadata["reason_in_documents"] = {
            "query": query,
            "source_chars": len(result.content),
            "analysis": payload,
        }
        context.state.set(
            "stage.tool_result",
            ToolResult(
                name=result.name,
                content="EVIDENCE ANALYSIS\n" + json.dumps(payload, ensure_ascii=False),
                metadata=metadata,
            ),
        )


class ProtocolRepairHook(BaseHook):
    def __init__(self) -> None:
        super().__init__(
            hook_id="protocol_repair",
            phases=frozenset({HookPhase.POST_MODEL}),
            writable_stage_keys=frozenset({"stage.raw_model_output"}),
        )

    def handle(self, context: HookContext) -> None:
        raw = context.state.get("stage.raw_model_output")
        core = context.state.get("core")
        if not isinstance(raw, str) or not isinstance(core, dict):
            raise TypeError("protocol repair requires raw output and core state")
        text = raw.strip()
        if "<tool_call>" in text or "<final_answer>" in text or not core.get("tool_interactions"):
            return
        if text and len(text) <= 300 and len(text.split()) <= 40 and not text.startswith("{"):
            context.state.set("stage.raw_model_output", f"<final_answer>{text}</final_answer>")


def _history(core: dict[str, Any], limit: int) -> str:
    messages = core.get("conversation_messages")
    if not isinstance(messages, list):
        return "None"
    rendered = "\n\n".join(
        f"{item.get('role')}: {item.get('content')}"
        for item in messages
        if isinstance(item, dict) and isinstance(item.get("content"), str)
    )
    return _retain_edges(rendered, limit) or "None"


def _retain_edges(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = max(1, limit // 3)
    return f"{text[:head]}\n\n[...middle omitted...]\n\n{text[-(limit-head):]}"


def _parse_object(raw: str) -> dict[str, Any]:
    text = raw.strip().strip("`").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _valid_analysis(payload: dict[str, Any]) -> bool:
    facts = payload.get("relevant_facts")
    return isinstance(facts, list) and all(isinstance(item, str) for item in facts)


def build(config: dict[str, Any], context: Any) -> tuple[BaseHook, ...]:
    del context
    allowed = {"topk", "max_history_chars", "max_document_chars"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unsupported reasoner config keys: {sorted(unknown)}")
    topk = config.get("topk", 10)
    max_history = config.get("max_history_chars", 6000)
    max_documents = config.get("max_document_chars", 24000)
    if not all(isinstance(value, int) and value > 0 for value in (topk, max_history, max_documents)):
        raise ValueError("reasoner limits must be positive integers")
    prompt = Path(__file__).resolve().with_name("reasoner.md").read_text(encoding="utf-8")
    return (
        ForceTopKHook(topk),
        ReasonInDocumentsHook(
            prompt=prompt,
            max_history_chars=max_history,
            max_document_chars=max_documents,
        ),
        ProtocolRepairHook(),
    )
