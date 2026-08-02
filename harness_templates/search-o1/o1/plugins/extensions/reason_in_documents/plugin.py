"""Reason over retrieved passages before exposing them to the main Actor."""

from __future__ import annotations

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


DEFAULT_TEMPLATE = "templates/reasoner.md"
FINAL_INFORMATION_MARKER = "**Final Information**"
NO_HELPFUL_INFORMATION = "No helpful information found."


class ReasonInDocumentsHook(BaseHook):
    """Replace one raw search observation with model-refined evidence."""

    def __init__(
        self,
        *,
        system_prompt: str,
        max_history_chars: int,
        max_document_chars: int,
        hook_id: str = "reason_in_documents",
    ) -> None:
        if not system_prompt.strip():
            raise ValueError("reason-in-documents system prompt must not be empty")
        if max_history_chars < 1:
            raise ValueError("max_history_chars must be positive")
        if max_document_chars < 1:
            raise ValueError("max_document_chars must be positive")
        self._system_prompt = system_prompt.strip()
        self._max_history_chars = max_history_chars
        self._max_document_chars = max_document_chars
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.POST_TOOL}),
            writable_stage_keys=frozenset({"stage.tool_result"}),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        tool_call = context.state.get("stage.tool_call")
        tool_result = context.state.get("stage.tool_result")
        if not isinstance(tool_call, ToolCall):
            raise TypeError("stage.tool_call must be a ToolCall")
        if not isinstance(tool_result, ToolResult):
            raise TypeError("stage.tool_result must be a ToolResult")
        if tool_call.name != "search" or tool_result.name != "search":
            return

        query = tool_call.arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("search tool call must contain a non-empty query")
        model_input = self._reasoner_input(
            context=context,
            query=query.strip(),
            documents=tool_result.content,
        )
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="reason_in_retrieved_documents",
                model_input=model_input,
            )
        )
        information = _extract_final_information(response.raw_output)
        metadata = dict(tool_result.metadata)
        metadata["reason_in_documents"] = {
            "query": query.strip(),
            "source_chars": len(tool_result.content),
            "output_chars": len(information),
        }
        context.state.set(
            "stage.tool_result",
            ToolResult(
                name=tool_result.name,
                content=information,
                metadata=metadata,
            ),
        )

    def _reasoner_input(
        self,
        *,
        context: HookContext,
        query: str,
        documents: str,
    ) -> ModelInput:
        question = context.state.get("core.question")
        if not isinstance(question, str):
            raise TypeError("core.question must be a string")
        core = context.state.get("core")
        if not isinstance(core, dict):
            raise TypeError("core state must be an object")
        history = _render_previous_reasoning(core, self._max_history_chars)
        user_content = (
            f"Original Question:\n{question}\n\n"
            f"Previous Reasoning:\n{history}\n\n"
            f"Current Search Query:\n{query}\n\n"
            "Retrieved Passages:\n"
            f"{_retain_edges(documents, self._max_document_chars)}"
        )
        return ModelInput.from_messages(
            [
                ChatMessage(role="system", content=self._system_prompt),
                ChatMessage(role="user", content=user_content),
            ]
        )


def build(config: dict[str, Any], context: Any) -> ReasonInDocumentsHook:
    """Build the post-tool document reasoner."""

    del context
    allowed = {"template", "max_history_chars", "max_document_chars"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(
            "reason_in_documents has unsupported config keys: "
            f"{sorted(unknown)}"
        )
    template = config.get("template", DEFAULT_TEMPLATE)
    if not isinstance(template, str):
        raise TypeError("reason_in_documents template must be a string")
    max_history_chars = config.get("max_history_chars", 8000)
    max_document_chars = config.get("max_document_chars", 16000)
    if not isinstance(max_history_chars, int):
        raise TypeError("max_history_chars must be an integer")
    if not isinstance(max_document_chars, int):
        raise TypeError("max_document_chars must be an integer")
    path = _resolve_local_path(template)
    return ReasonInDocumentsHook(
        system_prompt=path.read_text(encoding="utf-8"),
        max_history_chars=max_history_chars,
        max_document_chars=max_document_chars,
    )


def _resolve_local_path(relative_path: str) -> Path:
    root = Path(__file__).resolve().parent
    path = (root / relative_path).resolve()
    if root not in path.parents and path != root:
        raise ValueError(
            "reason_in_documents template must stay inside its plugin directory"
        )
    return path


def _render_previous_reasoning(core: dict[str, Any], limit: int) -> str:
    rendered: list[str] = []
    messages = core.get("conversation_messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if isinstance(role, str) and isinstance(content, str):
                rendered.append(f"{role.title()}:\n{content}")

    outputs = core.get("model_outputs")
    if isinstance(outputs, list) and outputs and isinstance(outputs[-1], str):
        rendered.append(f"Assistant:\n{outputs[-1]}")
    return _retain_edges("\n\n".join(rendered), limit)


def _retain_edges(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = max(1, limit // 4)
    tail = max(1, limit - head)
    return f"{text[:head]}\n\n...\n\n{text[-tail:]}"


def _extract_final_information(raw_output: str) -> str:
    if FINAL_INFORMATION_MARKER not in raw_output:
        return NO_HELPFUL_INFORMATION
    information = raw_output.rsplit(FINAL_INFORMATION_MARKER, maxsplit=1)[-1]
    information = information.strip().strip("`").strip()
    return information or NO_HELPFUL_INFORMATION
