"""Shadow Evidence Reviewer Prompt Component."""

from __future__ import annotations

from typing import Any

from experiments.teacher_query_views.prompt import ShadowEvidenceReviewerPrompt
from search_harness.evolution.research.roles.prompting import load_prompt_spec


def build(config: dict[str, Any], context: Any, tools: Any):
    del context, tools
    from pathlib import Path

    formal = load_prompt_spec(Path(__file__).resolve().parent, config)
    return ShadowEvidenceReviewerPrompt(
        instructions=formal.instructions,
        user_template=formal.user_template,
        continuation_templates=formal.continuation_templates,
    )
