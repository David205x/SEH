"""Shadow Teacher Role Output Contract adapter。"""

from __future__ import annotations

from typing import Any

from search_harness.evolution.research.resources.base import TeacherResources
from search_harness.evolution.research.roles.contracts import (
    ShadowDistillationSubmission,
)
from search_harness.evolution.research.roles.spec import TeacherOutputSpec


def build(config: dict[str, Any], context: Any) -> TeacherOutputSpec:
    if config:
        raise ValueError("role_contract output does not accept configuration")
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("Shadow Distiller output requires TeacherResources")
    return TeacherOutputSpec(
        submission_type=ShadowDistillationSubmission,
        materializer=resources.materialize_shadow_distillation,
    )
