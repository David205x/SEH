"""compiler Prompt Component。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.evolution.research.compiler_views import (
    render_compiler_resource_context,
)
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.contracts import TeacherPayload
from search_harness.evolution.research.roles.spec import (
    RESOURCE_CONTEXT_PLACEHOLDER,
    ROLE_INPUT_PLACEHOLDER,
    TeacherPromptSpec,
)
from search_harness.framework.tools import ToolSet


@dataclass(frozen=True)
class CompilerPrompt(TeacherPromptSpec):
    """Preserve full Compiler input while compacting program API context."""

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return (
            self.user_template.replace(
                ROLE_INPUT_PLACEHOLDER,
                json.dumps(
                    role_input.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            .replace(
                RESOURCE_CONTEXT_PLACEHOLDER,
                render_compiler_resource_context(resource_context),
            )
            .strip()
        )


def build(
    config: dict[str, Any],
    context: Any,
    tools: ToolSet,
) -> TeacherPromptSpec:
    del context, tools
    prompt = load_prompt_spec(Path(__file__).resolve().parent, config)
    return CompilerPrompt(
        instructions=prompt.instructions,
        user_template=prompt.user_template,
        continuation_templates=prompt.continuation_templates,
    )
