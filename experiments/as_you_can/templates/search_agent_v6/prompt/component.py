"""Compact interleaved-retrieval Prompt Component."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from search_harness.framework.agent.types import AgentState, ChatMessage, ModelInput
from search_harness.framework.prompting import render_tagged_tool_section
from search_harness.framework.tools import ToolDefinition, ToolSet


class SearchPrompt:
    def __init__(self, tools: ToolSet | Iterable[ToolDefinition], prompt: str) -> None:
        self._prompt = prompt.strip()
        self._tools = tools.definitions if isinstance(tools, ToolSet) else tuple(tools)
        if "{{tool_section}}" not in self._prompt:
            raise ValueError("system prompt must contain {{tool_section}}")

    def build(self, state: AgentState) -> ModelInput:
        messages = [
            ChatMessage(
                role="system",
                content=self._prompt.replace(
                    "{{tool_section}}", render_tagged_tool_section(self._tools)
                ),
            ),
            ChatMessage(role="user", content=state.question),
        ]
        messages.extend(state.conversation_messages)
        return ModelInput.from_messages(messages)


def build(config: dict[str, Any], context: Any, tools: ToolSet) -> SearchPrompt:
    del context
    if config:
        raise ValueError("ircot_search does not accept configuration")
    path = Path(__file__).resolve().with_name("system.md")
    return SearchPrompt(tools, path.read_text(encoding="utf-8"))
