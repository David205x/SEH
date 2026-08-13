"""Shadow Mechanism Distiller prompt assembled from formal instructions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.teacher_query_views.prompt import ShadowMechanismDistillerPrompt
from search_harness.evolution.research.resources.base import TeacherResources
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.framework.harness import ComponentFactoryContext


_FORMAL_USER_REQUIREMENT = (
    "Inspect every cited trial and use the mechanism draft tools before returning\n"
    "`distilled`. For `needs_evidence`, request only a discriminating additional\n"
    "assignment of the same frozen hypothesis."
)
_SHADOW_USER_REQUIREMENT = (
    "The dossier already contains every cited Trial's independent Review, exact "
    "Student-visible mutation, deterministic effect, and outcome. Use the "
    "mechanism draft tools before returning `distilled`. Call "
    "`get_distillation_trial_detail` only to resolve a concrete conflict or "
    "ambiguity. For `needs_evidence`, request only a discriminating additional "
    "assignment of the same frozen hypothesis."
)


def build(
    config: dict[str, Any],
    context: ComponentFactoryContext,
    tools: Any,
):
    del tools
    if config:
        raise ValueError("shadow Distiller prompt does not accept configuration")
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("shadow Distiller prompt requires TeacherResources")
    if resources.trials is None:
        raise ValueError("shadow Distiller prompt requires trial resources")
    formal_root = (
        Path(__file__).resolve().parents[5]
        / "harness_templates"
        / "teacher"
        / "mechanism_distiller"
        / "prompt"
    )
    formal = load_prompt_spec(
        formal_root,
        {"instructions": "system.md", "user_template": "user.md"},
    )
    if _FORMAL_USER_REQUIREMENT not in formal.user_template:
        raise ValueError("formal Distiller user requirement changed")
    instructions = formal.instructions + (
        "\n\n## Shadow evidence dossier\n\n"
        "The initial user message is one complete, deterministic Distillation "
        "Evidence Dossier. Treat its independent Reviews and deterministic facts "
        "as the default evidence record. Do not call the detail tool merely to "
        "repeat or re-adjudicate those facts. Use it only when the dossier contains "
        "a material conflict, missing exact event boundary, or ambiguous mutation "
        "that blocks an operational mechanism definition."
    )
    return ShadowMechanismDistillerPrompt(
        instructions=instructions,
        user_template=formal.user_template.replace(
            _FORMAL_USER_REQUIREMENT,
            _SHADOW_USER_REQUIREMENT,
        ),
        continuation_templates=formal.continuation_templates,
        trial_payloads=resources.trials.trials,
    )
