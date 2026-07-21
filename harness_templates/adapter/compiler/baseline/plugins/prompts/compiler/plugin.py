"""Prompt plugin for the baseline Compiler Agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.adapter.compiler import CompilerContext
from search_harness.core import AgentState, ChatMessage, ModelInput
from search_harness.framework.prompting.renderers import render_tagged_tool_section
from search_harness.framework.tooling import ToolSet


DEFAULT_TEMPLATE = "templates/system.md"


class CompilerPromptBuilder:
    def __init__(self, compiler: CompilerContext, tools: ToolSet, template: str) -> None:
        self._compiler = compiler
        self._tools = tools
        self._template = template.strip()
        if "{{tool_section}}" not in self._template:
            raise ValueError("compiler prompt template must contain {{tool_section}}")

    def build(self, state: AgentState) -> ModelInput:
        messages = [
            ChatMessage(role="system", content=self._render_system()),
            ChatMessage(role="user", content=self._render_initial_user(state.question)),
        ]
        messages.extend(state.conversation_messages)
        return ModelInput.from_messages(messages)

    def _render_system(self) -> str:
        return self._template.replace(
            "{{tool_section}}",
            render_tagged_tool_section(self._tools.definitions),
        )

    def _render_initial_user(self, task: str) -> str:
        return (
            f"Compilation task:\n{task.strip()}\n\n"
            "Bound Compiler context:\n"
            f"{json.dumps(self._compiler.initial_context(), ensure_ascii=False, indent=2)}"
        )


def build(config: dict[str, Any], context: Any, tools: ToolSet) -> CompilerPromptBuilder:
    unknown = set(config) - {"template"}
    if unknown:
        raise ValueError(f"compiler prompt has unsupported config keys: {sorted(unknown)}")
    if not isinstance(context.runtime_context, CompilerContext):
        raise TypeError("compiler prompt requires a CompilerContext")
    template = config.get("template", DEFAULT_TEMPLATE)
    if not isinstance(template, str):
        raise TypeError("compiler prompt template must be a string")
    root = Path(__file__).resolve().parent
    path = (root / template).resolve()
    if root not in path.parents and path != root:
        raise ValueError("compiler prompt template must stay inside its plugin directory")
    return CompilerPromptBuilder(
        compiler=context.runtime_context,
        tools=tools,
        template=path.read_text(encoding="utf-8"),
    )
