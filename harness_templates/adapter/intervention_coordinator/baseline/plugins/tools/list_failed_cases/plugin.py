"""Failure-pool listing tool for the Intervention Coordinator."""

from __future__ import annotations

from typing import Any

from search_harness.adapter.intervention import InterventionCoordinatorContext
from search_harness.adapter.intervention.coordinator_context import ListFailedCasesTool


def build(config: dict[str, Any], context: Any) -> ListFailedCasesTool:
    """Bind paginated failure listing to this Coordinator run."""

    if config:
        raise ValueError("list_failed_cases does not accept configuration")
    if not isinstance(context.runtime_context, InterventionCoordinatorContext):
        raise TypeError("list_failed_cases requires an InterventionCoordinatorContext")
    return ListFailedCasesTool(context.runtime_context)
