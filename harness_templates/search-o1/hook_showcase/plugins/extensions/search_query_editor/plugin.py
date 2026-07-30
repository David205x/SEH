"""Normalize search calls immediately before tool execution."""

from __future__ import annotations

from typing import Any

from search_harness.core import BaseHook, HookContext, HookPhase, ToolCall


class SearchQueryEditorHook(BaseHook):
    """Normalize query whitespace and cap the requested passage count."""

    def __init__(
        self,
        *,
        max_topk: int,
        hook_id: str = "search_query_editor",
    ) -> None:
        if max_topk < 1:
            raise ValueError("max_topk must be positive")
        self._max_topk = max_topk
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.PRE_TOOL}),
            writable_stage_keys=frozenset({"stage.tool_call"}),
        )

    def handle(self, context: HookContext) -> None:
        tool_call = context.state.get("stage.tool_call")
        if not isinstance(tool_call, ToolCall):
            raise TypeError("stage.tool_call must be a ToolCall")
        if tool_call.name != "search":
            return

        arguments = dict(tool_call.arguments)
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("search query must be a non-empty string")
        arguments["query"] = " ".join(query.split())

        topk = arguments.get("topk", self._max_topk)
        if not isinstance(topk, int):
            raise TypeError("search topk must be an integer")
        arguments["topk"] = min(max(topk, 1), self._max_topk)

        edited = ToolCall(name=tool_call.name, arguments=arguments)
        if edited != tool_call:
            context.state.set("stage.tool_call", edited)


def build(config: dict[str, Any], context: Any) -> SearchQueryEditorHook:
    """Build the deterministic pre-tool call editor."""

    del context
    allowed = {"max_topk"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(
            f"search_query_editor has unsupported config keys: {sorted(unknown)}"
        )
    max_topk = config.get("max_topk", 5)
    if not isinstance(max_topk, int):
        raise TypeError("search_query_editor.max_topk must be an integer")
    return SearchQueryEditorHook(max_topk=max_topk)
