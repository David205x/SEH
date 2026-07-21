"""Prompt plugin for the standalone Intervention Coordinator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.adapter.intervention import InterventionCoordinatorContext
from search_harness.core import AgentState, ChatMessage, ModelInput
from search_harness.framework.prompting.renderers import render_tagged_tool_section
from search_harness.framework.tooling import ToolSet


DEFAULT_TEMPLATE = "templates/system.md"


class InterventionCoordinatorPromptBuilder:
    """Render one case-bound coordination task and its dynamic tools."""

    def __init__(
        self,
        coordinator: InterventionCoordinatorContext,
        tools: ToolSet,
        system_prompt: str,
    ) -> None:
        self._coordinator = coordinator
        self._tools = tools
        self._system_prompt = system_prompt.strip()
        if "{{tool_section}}" not in self._system_prompt:
            raise ValueError("coordinator template must contain {{tool_section}}")

    def build(self, state: AgentState) -> ModelInput:
        system = self._system_prompt.replace(
            "{{tool_section}}",
            render_tagged_tool_section(self._tools.definitions),
        )
        initial = (
            f"Coordination task:\n{state.question.strip()}\n\n"
            "Bound source case:\n"
            f"{json.dumps(self._coordinator.initial_context(), ensure_ascii=False, indent=2)}"
        )
        return ModelInput.from_messages(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=initial),
                *state.conversation_messages,
            ]
        )


def build(
    config: dict[str, Any],
    context: Any,
    tools: ToolSet,
) -> InterventionCoordinatorPromptBuilder:
    """Create the case-bound Coordinator prompt builder."""

    allowed = {"template"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"coordinator prompt has unsupported config: {sorted(unknown)}")
    if not isinstance(context.runtime_context, InterventionCoordinatorContext):
        raise TypeError("coordinator prompt requires an InterventionCoordinatorContext")
    template = config.get("template", DEFAULT_TEMPLATE)
    if not isinstance(template, str):
        raise TypeError("coordinator prompt template must be a string")
    root = Path(__file__).resolve().parent
    path = (root / template).resolve()
    if root not in path.parents and path != root:
        raise ValueError("coordinator prompt template must stay inside its plugin directory")
    return InterventionCoordinatorPromptBuilder(
        coordinator=context.runtime_context,
        tools=tools,
        system_prompt=path.read_text(encoding="utf-8"),
    )
