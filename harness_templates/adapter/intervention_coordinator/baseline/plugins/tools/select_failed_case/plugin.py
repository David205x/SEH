"""Specified failure selection tool for the Intervention Coordinator."""

from __future__ import annotations

from typing import Any

from search_harness.adapter.intervention import InterventionCoordinatorContext
from search_harness.adapter.intervention.coordinator_context import SelectFailedCaseTool


def build(config: dict[str, Any], context: Any) -> SelectFailedCaseTool:
    """Bind stable-ID failure selection to this Coordinator run."""

    if config:
        raise ValueError("select_failed_case does not accept configuration")
    if not isinstance(context.runtime_context, InterventionCoordinatorContext):
        raise TypeError("select_failed_case requires an InterventionCoordinatorContext")
    return SelectFailedCaseTool(context.runtime_context)
