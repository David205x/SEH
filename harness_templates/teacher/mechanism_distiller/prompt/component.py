"""mechanism_distiller Prompt Component。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import TeacherResources
from search_harness.evolution.research.roles.contracts import TeacherPayload
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.spec import TeacherPromptSpec
from search_harness.evolution.research.views import (
    render_mechanism_distiller_input,
)
from search_harness.framework.harness import ComponentFactoryContext
from search_harness.framework.tools import ToolSet


@dataclass(frozen=True)
class MechanismDistillerPrompt(TeacherPromptSpec):
    """Render one complete dossier over attached immutable Trial evidence."""

    trial_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return render_mechanism_distiller_input(
            role_input.model_dump(mode="json"),
            self.trial_payloads,
            resource_context,
        )


def build(
    config: dict[str, Any],
    context: ComponentFactoryContext,
    tools: ToolSet,
) -> TeacherPromptSpec:
    del tools
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("Mechanism Distiller prompt requires TeacherResources")
    if resources.trials is None:
        raise ValueError("Mechanism Distiller prompt requires trial resources")
    prompt = load_prompt_spec(Path(__file__).resolve().parent, config)
    return MechanismDistillerPrompt(
        instructions=prompt.instructions,
        user_template=prompt.user_template,
        continuation_templates=prompt.continuation_templates,
        trial_payloads=resources.trials.trials,
    )
