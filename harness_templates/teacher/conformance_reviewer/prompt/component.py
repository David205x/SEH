"""conformance_reviewer Prompt Component。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.evolution.research.conformance import (
    render_conformance_batch_input,
)
from search_harness.evolution.research.roles.contracts import TeacherPayload
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.spec import (
    RESOURCE_CONTEXT_PLACEHOLDER,
    ROLE_INPUT_PLACEHOLDER,
    TeacherPromptSpec,
)
from search_harness.framework.tools import ToolSet


@dataclass(frozen=True)
class ConformanceReviewerPrompt(TeacherPromptSpec):
    """Separate shared evidence from exact per-replicate trajectory views."""

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return (
            self.user_template.replace(
                ROLE_INPUT_PLACEHOLDER,
                render_conformance_batch_input(
                    role_input.model_dump(mode="json"),
                ),
            )
            .replace(
                RESOURCE_CONTEXT_PLACEHOLDER,
                _render_resource_context(resource_context),
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
    return ConformanceReviewerPrompt(
        instructions=prompt.instructions,
        user_template=prompt.user_template,
        continuation_templates=prompt.continuation_templates,
    )


def _render_resource_context(value: dict[str, Any]) -> str:
    if not value:
        return "No query resources are available for this review."
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
