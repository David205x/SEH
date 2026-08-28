"""Shadow Mechanism Distiller Prompt Component。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import TeacherResources
from search_harness.evolution.research.roles.contracts import TeacherPayload
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.spec import TeacherPromptSpec
from search_harness.evolution.research.shadow_task_inputs import (
    shadow_task_source_catalog,
)
from search_harness.evolution.research.views import (
    render_mechanism_distiller_input,
)
from search_harness.framework.harness import ComponentFactoryContext
from search_harness.framework.tools import ToolSet


_CLOSING_INSTRUCTION = (
    "Distill the smallest supported Teacher-free mechanism through the Shadow "
    "assembly tools, validate it, and submit only the resulting mechanism_ref. "
    "Do not use legacy draft tools or run a Student model experiment."
)


@dataclass(frozen=True)
class ShadowMechanismDistillerPrompt(TeacherPromptSpec):
    """Render the current dossier plus a source-derived input catalog。"""

    trial_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_catalog: dict[str, Any] = field(default_factory=dict)

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        dossier = render_mechanism_distiller_input(
            role_input.model_dump(mode="json"),
            self.trial_payloads,
            resource_context,
            closing_instruction=_CLOSING_INSTRUCTION,
        )
        return "\n\n".join(
            (
                dossier,
                "## Controlled Task Input Source Catalog\n"
                + json.dumps(
                    self.source_catalog,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                (
                    "Use only these exact sources or state.<name> for state "
                    "declared by the submitted Mechanism."
                ),
            )
        )


def build(
    config: dict[str, Any],
    context: ComponentFactoryContext,
    tools: ToolSet,
) -> TeacherPromptSpec:
    del tools
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("Shadow Distiller prompt requires TeacherResources")
    if resources.trials is None:
        raise ValueError("Shadow Distiller prompt requires trial resources")
    prompt = load_prompt_spec(Path(__file__).resolve().parent, config)
    return ShadowMechanismDistillerPrompt(
        instructions=prompt.instructions,
        user_template=prompt.user_template,
        continuation_templates=prompt.continuation_templates,
        trial_payloads=resources.trials.trials,
        source_catalog=shadow_task_source_catalog(),
    )
