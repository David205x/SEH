"""hook_feasibility_reviewer Prompt Component。"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any

from search_harness.evolution.research.hook_feasibility import (
    render_hook_feasibility_review_input,
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
class HookFeasibilityReviewerPrompt(TeacherPromptSpec):
    """Present each real prefix once and compact repeated observations."""

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        context = (
            "No query resources are available for this review."
            if not resource_context
            else str(resource_context)
        )
        return (
            self.user_template.replace(
                ROLE_INPUT_PLACEHOLDER,
                render_hook_feasibility_review_input(
                    role_input.model_dump(mode="json")
                ),
            )
            .replace(RESOURCE_CONTEXT_PLACEHOLDER, context)
            .strip()
        )


def build(
    config: dict[str, Any],
    context: Any,
    tools: ToolSet,
) -> TeacherPromptSpec:
    del context, tools
    prompt = load_prompt_spec(Path(__file__).resolve().parent, config)
    return HookFeasibilityReviewerPrompt(
        instructions=prompt.instructions,
        user_template=prompt.user_template,
        continuation_templates=prompt.continuation_templates,
    )
