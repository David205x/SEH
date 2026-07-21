"""Worker trial tool for the Intervention Coordinator."""

from __future__ import annotations

from typing import Any

from search_harness.adapter.intervention import InterventionCoordinatorContext
from search_harness.adapter.intervention.coordinator_context import RunWorkerTrialTool


def build(config: dict[str, Any], context: Any) -> RunWorkerTrialTool:
    """Bind independent Worker execution to this Coordinator run."""

    if config:
        raise ValueError("run_worker_trial does not accept configuration")
    if not isinstance(context.runtime_context, InterventionCoordinatorContext):
        raise TypeError("run_worker_trial requires an InterventionCoordinatorContext")
    return RunWorkerTrialTool(context.runtime_context)
