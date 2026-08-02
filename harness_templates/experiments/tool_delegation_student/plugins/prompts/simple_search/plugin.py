"""Tagged-text prompt plugin for the baseline search Harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from search_harness.framework import AgentState, ChatMessage, ModelInput
from search_harness.framework.prompting import render_tagged_tool_section
from search_harness.framework.tools import ToolDefinition, ToolSet


DEFAULT_TEMPLATE = "templates/system.md"


class SimplePromptBuilder:
    """Render state into structured chat messages for the tagged search actor."""

    def __init__(
        self,
        tools: ToolSet | Iterable[ToolDefinition],
        system_prompt: str,
    ) -> None:
        self._system_prompt_template = system_prompt.strip()
        self._tool_definitions = _tool_definitions(tools)
        if "{{tool_section}}" not in self._system_prompt_template:
            raise ValueError("system prompt template must contain {{tool_section}}")

    def build(self, state: AgentState) -> ModelInput:
        messages = [
            ChatMessage(role="system", content=self._render_system_prompt()),
            ChatMessage(role="user", content=state.question),
        ]
        messages.extend(state.conversation_messages)
        return ModelInput.from_messages(messages)

    def _render_system_prompt(self) -> str:
        return self._system_prompt_template.replace(
            "{{tool_section}}",
            render_tagged_tool_section(self._tool_definitions),
        )


def build(config: dict[str, Any], context: Any, tools: ToolSet) -> SimplePromptBuilder:
    """Create this prompt plugin from manifest configuration."""

    del context
    template = config.get("template", DEFAULT_TEMPLATE)
    if not isinstance(template, str):
        raise TypeError("simple_search template must be a string")
    unknown = set(config) - {"template"}
    if unknown:
        raise ValueError(f"simple_search has unsupported config keys: {sorted(unknown)}")
    template_path = _resolve_local_path(template)
    return SimplePromptBuilder(tools=tools, system_prompt=template_path.read_text(encoding="utf-8"))


def _resolve_local_path(relative_path: str) -> Path:
    root = Path(__file__).resolve().parent
    path = (root / relative_path).resolve()
    if root not in path.parents and path != root:
        raise ValueError("simple_search template must stay inside its plugin directory")
    return path


def _tool_definitions(
    tools: ToolSet | Iterable[ToolDefinition],
) -> tuple[ToolDefinition, ...]:
    if isinstance(tools, ToolSet):
        return tools.definitions
    return tuple(tools)
