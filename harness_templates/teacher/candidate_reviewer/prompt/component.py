"""candidate_reviewer Prompt Component。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.evolution.research.candidate_views import (
    render_candidate_review_input,
)
from search_harness.evolution.research.roles.contracts import TeacherPayload
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.spec import TeacherPromptSpec
from search_harness.framework.tools import ToolSet


@dataclass(frozen=True)
class CandidateReviewerPrompt(TeacherPromptSpec):
    """Render a non-duplicated Candidate decision brief."""

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return render_candidate_review_input(
            role_input.model_dump(mode="json"),
            resource_context,
        )


def build(
    config: dict[str, Any],
    context: Any,
    tools: ToolSet,
) -> TeacherPromptSpec:
    del context, tools
    prompt = load_prompt_spec(Path(__file__).resolve().parent, config)
    return CandidateReviewerPrompt(
        instructions=prompt.instructions,
        user_template=prompt.user_template,
        continuation_templates=prompt.continuation_templates,
    )
