"""Shadow Conformance Reviewer batch inputs and reference projections."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import Field, model_validator

from search_harness.evolution.research.roles.contracts import (
    ConformanceReview,
    TeacherPayload,
)


class ShadowConformanceFinding(ConformanceReview):
    """One independently judged replicate in a shadow batch."""

    replicate_id: str = Field(min_length=1)


class ShadowConformanceBatch(TeacherPayload):
    """Experiment-only output containing one finding per supplied replicate."""

    findings: list[ShadowConformanceFinding] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_replicates(self) -> "ShadowConformanceBatch":
        replicate_ids = [item.replicate_id for item in self.findings]
        if len(replicate_ids) != len(set(replicate_ids)):
            raise ValueError("findings must not repeat replicate_id")
        return self


def compact_reference_observations(
    observations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep reference behavior facts while removing case-specific patch text."""

    return [_compact_reference_observation(item) for item in observations]


def build_shadow_conformance_input(
    *,
    mechanism: dict[str, Any],
    trial_refs: list[str],
    reference_observations: list[dict[str, Any]],
    example_id: str,
    trajectories: list[dict[str, Any]],
    compact_references: bool,
) -> dict[str, Any]:
    """Build one example-level input without discarding rollout evidence."""

    references = (
        compact_reference_observations(reference_observations)
        if compact_references
        else reference_observations
    )
    return {
        "mechanism": mechanism,
        "trial_refs": trial_refs,
        "reference_observations": references,
        "example_id": example_id,
        "candidate_trajectory_views": trajectories,
    }


def render_shadow_conformance_input(value: dict[str, Any]) -> str:
    """Render a dense batch brief with exact JSON evidence boundaries."""

    trajectories = value.get("candidate_trajectory_views")
    trajectories = trajectories if isinstance(trajectories, list) else []
    lines = [
        "# Example-level Conformance Review Batch",
        (
            "Judge each replicate independently. Shared Mechanism and reference "
            "evidence appear once; a finding for one replicate must not be "
            "inferred from another replicate's behavior."
        ),
        "",
        "## Shared authoritative Mechanism",
        "```json",
        _compact_json(value.get("mechanism")),
        "```",
        "",
        "## Shared reference boundary",
        f"example_id: {value.get('example_id', 'unavailable')}",
        "trial_refs: " + _compact_json(value.get("trial_refs")),
        "```json",
        _compact_json(value.get("reference_observations")),
        "```",
        "",
        "## Candidate rollout views",
    ]
    for item in trajectories:
        item = item if isinstance(item, dict) else {}
        lines.extend(
            (
                f"### replicate {item.get('replicate_id', 'unavailable')}",
                "```json",
                _compact_json(item.get("candidate_trajectory_view")),
                "```",
            )
        )
    lines.extend(
        (
            "",
            "## Submission requirement",
            (
                "Submit exactly one independent finding for every replicate_id "
                "above, in the same order. Apply the full verdict and diagnostic "
                "contract separately to every finding."
            ),
        )
    )
    return "\n".join(lines)


def validate_shadow_batch(
    batch: ShadowConformanceBatch,
    *,
    expected_replicate_ids: list[str],
) -> None:
    """Require exact ordered coverage of the program-owned replicate batch."""

    actual = [item.replicate_id for item in batch.findings]
    if actual != expected_replicate_ids:
        raise ValueError(
            "shadow Conformance findings must match supplied replicate order; "
            f"expected={expected_replicate_ids}, actual={actual}"
        )


def _compact_reference_observation(value: dict[str, Any]) -> dict[str, Any]:
    phase_plan = value.get("phase_plan")
    phase_effects = value.get("phase_effects")
    phase_plan = phase_plan if isinstance(phase_plan, list) else []
    phase_effects = phase_effects if isinstance(phase_effects, list) else []
    return {
        "trial_ref": value.get("trial_ref"),
        "declared_phases": [
            {
                "phase": item.get("phase"),
                "max_activations": item.get("max_activations"),
            }
            for item in phase_plan
            if isinstance(item, dict)
        ],
        "activation_counts": value.get("activation_counts"),
        "observed_phase_effects": [
            {
                key: item.get(key)
                for key in (
                    "phase",
                    "phase_activation",
                    "action_kind",
                    "modified",
                    "anchor_found",
                    "next_model_decision",
                    "tool_calls_before_next_final",
                    "next_final_step",
                )
            }
            for item in phase_effects
            if isinstance(item, dict)
        ],
        "context_effects": _compact_context_effects(value.get("context_changes")),
    }


def _compact_context_effects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    effects = []
    for change in value:
        if not isinstance(change, dict):
            continue
        action = change.get("action")
        action = action if isinstance(action, dict) else {}
        model_change = change.get("model_input_change")
        model_change = model_change if isinstance(model_change, dict) else {}
        changed_blocks = model_change.get("changed_blocks")
        changed_blocks = changed_blocks if isinstance(changed_blocks, list) else []
        effects.append(
            {
                "phase": change.get("phase"),
                "action_kind": action.get("kind"),
                "model_input_before_count": model_change.get("before_count"),
                "model_input_after_count": model_change.get("after_count"),
                "changed_blocks": [
                    {
                        "block_id": block.get("block_id"),
                        "change_kind": _block_change_kind(block),
                        "role_before": _nested_value(block, "before", "role"),
                        "role_after": _nested_value(block, "after", "role"),
                    }
                    for block in changed_blocks
                    if isinstance(block, dict)
                ],
            }
        )
    return effects


def _block_change_kind(value: dict[str, Any]) -> str:
    before = value.get("before")
    after = value.get("after")
    if before is None and after is not None:
        return "inserted"
    if before is not None and after is None:
        return "deleted"
    return "replaced"


def _nested_value(value: dict[str, Any], key: str, nested_key: str) -> object:
    nested = value.get(key)
    return nested.get(nested_key) if isinstance(nested, dict) else None


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
