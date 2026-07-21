"""Seeded failure sampling tool for the Intervention Coordinator."""

from __future__ import annotations

from typing import Any

from search_harness.adapter.intervention import InterventionCoordinatorContext
from search_harness.adapter.intervention.coordinator_context import SampleFailedCaseTool


def build(config: dict[str, Any], context: Any) -> SampleFailedCaseTool:
    """Bind reproducible random failure selection to this Coordinator run."""

    if config:
        raise ValueError("sample_failed_case does not accept configuration")
    if not isinstance(context.runtime_context, InterventionCoordinatorContext):
        raise TypeError("sample_failed_case requires an InterventionCoordinatorContext")
    return SampleFailedCaseTool(context.runtime_context)
