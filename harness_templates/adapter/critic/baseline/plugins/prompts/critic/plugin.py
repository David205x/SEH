"""Prompt plugin for the baseline Critic Agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import AgentState, ChatMessage, ModelInput
from search_harness.framework.prompting.renderers import render_tagged_tool_section
from search_harness.framework.tooling import ToolSet


DEFAULT_TEMPLATE = "templates/system.md"


class CriticPromptBuilder:
    def __init__(self, critic: CriticContext, tools: ToolSet, system_prompt: str) -> None:
        self._critic = critic
        self._tools = tools
        self._system_prompt = system_prompt.strip()
        if "{{tool_section}}" not in self._system_prompt:
            raise ValueError("critic prompt template must contain {{tool_section}}")

    def build(self, state: AgentState) -> ModelInput:
        messages = [
            ChatMessage(role="system", content=self._render_system()),
            ChatMessage(role="user", content=self._render_initial_user(state.question)),
        ]
        messages.extend(state.conversation_messages)
        return ModelInput.from_messages(messages)

    def _render_system(self) -> str:
        return self._system_prompt.replace(
            "{{tool_section}}",
            render_tagged_tool_section(self._tools.definitions),
        )

    def _render_initial_user(self, task: str) -> str:
        payload = self._critic.initial_context()
        return (
            f"Analysis task:\n{task.strip()}\n\n"
            "Bound Critic context:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )


def build(config: dict[str, Any], context: Any, tools: ToolSet) -> CriticPromptBuilder:
    allowed = {"template"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"critic prompt has unsupported config keys: {sorted(unknown)}")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("critic prompt requires a CriticContext")
    template = config.get("template", DEFAULT_TEMPLATE)
    if not isinstance(template, str):
        raise TypeError("critic prompt template must be a string")
    root = Path(__file__).resolve().parent
    path = (root / template).resolve()
    if root not in path.parents and path != root:
        raise ValueError("critic prompt template must stay inside its plugin directory")
    return CriticPromptBuilder(
        critic=context.runtime_context,
        tools=tools,
        system_prompt=path.read_text(encoding="utf-8"),
    )
