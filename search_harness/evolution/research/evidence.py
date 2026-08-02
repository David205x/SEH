"""Deterministic aggregation of persisted Intervention Trial evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def aggregate_trial_observations(
    trial_artifacts: list[dict[str, Any]],
    trial_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Summarize persisted Intervention Trial evidence for review."""

    items = [_trial_observation(artifact) for artifact in trial_artifacts]
    if trial_paths is not None:
        if len(trial_paths) != len(items):
            raise ValueError("trial artifact and path counts must match")
        for item, path in zip(items, trial_paths):
            item["trial_ref"] = path.parent.name
    return {
        "trial_count": len(items),
        "completed_source_count": sum(
            item["source_status"] == "completed" for item in items
        ),
        "completed_branch_count": sum(
            item["branch_status"] == "completed" for item in items
        ),
        "source_full_tool_calls": sum(
            item["source_full_tool_calls"] for item in items
        ),
        "branch_continuation_tool_calls": sum(
            item["branch_continuation_tool_calls"] for item in items
        ),
        "source_full_model_calls": sum(
            item["source_full_model_calls"] for item in items
        ),
        "branch_continuation_model_calls": sum(
            item["branch_continuation_model_calls"] for item in items
        ),
        "answer_changed_count": sum(
            item["source_answer"] != item["branch_answer"] for item in items
        ),
        "fully_activated_plan_count": sum(
            not item["unmet_phases"] for item in items
        ),
        "fully_modified_plan_count": sum(
            set(item["modified_phases"])
            == set(item["activated_phases"])
            and not item["unmet_phases"]
            for item in items
        ),
        "concrete_intervention_count": sum(
            item["concrete_intervention_count"] for item in items
        ),
        "phase_activation_counts": _sum_phase_counts(items),
        "phase_modification_counts": _sum_phase_modifications(items),
        "items": items,
    }


def _trial_observation(artifact: dict[str, Any]) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    trial = resources.get("intervention_trial")
    trial = trial if isinstance(trial, dict) else {}
    comparison = trial.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}
    source = comparison.get("source")
    source = source if isinstance(source, dict) else {}
    branch = comparison.get("branch")
    branch = branch if isinstance(branch, dict) else {}
    output = artifact.get("output")
    output = output if isinstance(output, dict) else {}
    activation_counts = trial.get("activation_counts")
    activation_counts = (
        activation_counts if isinstance(activation_counts, dict) else {}
    )
    context_changes = trial.get("context_changes")
    context_changes = (
        context_changes if isinstance(context_changes, list) else []
    )
    source_execution = source.get("execution")
    source_execution = (
        source_execution if isinstance(source_execution, dict) else {}
    )
    branch_execution = branch.get("execution")
    branch_execution = (
        branch_execution if isinstance(branch_execution, dict) else {}
    )
    return {
        "source_status": source.get("status"),
        "branch_status": branch.get("status"),
        "source_answer": source.get("answer"),
        "branch_answer": branch.get("answer"),
        "source_score": source.get("score"),
        "branch_score": branch.get("score"),
        "source_full_tool_calls": _integer(
            source_execution.get("tool_calls")
        ),
        "branch_continuation_tool_calls": _integer(
            branch_execution.get("tool_calls")
        ),
        "source_full_model_calls": _integer(
            source_execution.get("model_calls")
        ),
        "branch_continuation_model_calls": _integer(
            branch_execution.get("model_calls")
        ),
        "activated_phases": list(output.get("activated_phases", [])),
        "modified_phases": list(output.get("modified_phases", [])),
        "unmet_phases": list(output.get("unmet_phases", [])),
        "phase_activation_counts": {
            str(phase): _integer(count)
            for phase, count in activation_counts.items()
        },
        "concrete_intervention_count": sum(
            isinstance(change, dict)
            and isinstance(change.get("action"), dict)
            and change["action"].get("kind") != "continue_without_change"
            for change in context_changes
        ),
    }


def _sum_phase_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in items:
        for phase, count in item["phase_activation_counts"].items():
            totals[phase] = totals.get(phase, 0) + count
    return dict(sorted(totals.items()))


def _sum_phase_modifications(
    items: list[dict[str, Any]],
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in items:
        for phase in item["modified_phases"]:
            totals[phase] = totals.get(phase, 0) + 1
    return dict(sorted(totals.items()))


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
