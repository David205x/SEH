"""Read-only source case tool for the Intervention Coordinator."""

from __future__ import annotations

from typing import Any

from search_harness.adapter.intervention import InterventionCoordinatorContext
from search_harness.adapter.intervention.coordinator_context import (
    InspectInterventionCaseTool,
)


def build(config: dict[str, Any], context: Any) -> InspectInterventionCaseTool:
    """Bind the source-case inspection tool to this Coordinator run."""

    if config:
        raise ValueError("inspect_intervention_case does not accept configuration")
    if not isinstance(context.runtime_context, InterventionCoordinatorContext):
        raise TypeError(
            "inspect_intervention_case requires an InterventionCoordinatorContext"
        )
    return InspectInterventionCaseTool(context.runtime_context)
