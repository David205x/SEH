"""Evidence-grounded Prompt Component."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from search_harness.framework.agent.types import AgentState, ChatMessage, ModelInput
from search_harness.framework.prompting import render_tagged_tool_section
from search_harness.framework.tools import ToolDefinition, ToolSet


class EvidenceSearchPrompt:
    """Render the fixed system contract and current Agent conversation."""

    def __init__(
        self,
        tools: ToolSet | Iterable[ToolDefinition],
        system_prompt: str,
    ) -> None:
        self._system_prompt = system_prompt.strip()
        self._tools = tools.definitions if isinstance(tools, ToolSet) else tuple(tools)
        if "{{tool_section}}" not in self._system_prompt:
            raise ValueError("system prompt must contain {{tool_section}}")

    def build(self, state: AgentState) -> ModelInput:
        messages = [
            ChatMessage(
                role="system",
                content=self._system_prompt.replace(
                    "{{tool_section}}", render_tagged_tool_section(self._tools)
                ),
            ),
            ChatMessage(role="user", content=state.question),
        ]
        messages.extend(state.conversation_messages)
        return ModelInput.from_messages(messages)


def build(
    config: dict[str, Any], context: Any, tools: ToolSet
) -> EvidenceSearchPrompt:
    """Build the Prompt from a component-local UTF-8 asset."""

    del context
    unknown = set(config) - {"template"}
    if unknown:
        raise ValueError(f"unsupported prompt config keys: {sorted(unknown)}")
    template = config.get("template", "system.md")
    if not isinstance(template, str):
        raise TypeError("prompt template must be a string")
    root = Path(__file__).resolve().parent
    path = (root / template).resolve()
    if path != root and root not in path.parents:
        raise ValueError("prompt template must stay in its component directory")
    return EvidenceSearchPrompt(tools, path.read_text(encoding="utf-8"))
