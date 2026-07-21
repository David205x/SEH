"""Critic 评估证据与 Harness 来源的一致性校验。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .context import CriticContext


def validate_iteration_rollouts(
    context: CriticContext,
    *,
    iteration_id: str,
    candidate_digest: str,
) -> None:
    """拒绝并非由指定 pending candidate 生成的 rollout。"""

    for example_id, replicate_id, record in _iter_rollouts(
        context.rollout_records
    ):
        identity = f"{example_id}/{replicate_id}"
        raw_harness = record.get("harness")
        if not isinstance(raw_harness, Mapping):
            raise ValueError(
                f"rollout {identity} has no Harness provenance for iteration review"
            )
        if raw_harness.get("source_type") != "pending_iteration":
            raise ValueError(f"rollout {identity} is not a pending-iteration rollout")
        actual_iteration = raw_harness.get("iteration_id")
        if actual_iteration != iteration_id:
            raise ValueError(
                f"rollout {identity} iteration mismatch: "
                f"expected {iteration_id}, got {actual_iteration}"
            )
        actual_digest = raw_harness.get("candidate_digest")
        if actual_digest != candidate_digest:
            raise ValueError(
                f"rollout {identity} candidate digest mismatch: "
                f"expected {candidate_digest}, got {actual_digest}"
            )


def validate_accepted_rollouts(
    records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    store_root: Path,
    checkpoint_store_id: str,
    version_id: str,
    digest: str,
    evidence_name: str,
) -> None:
    """拒绝并非由指定 accepted snapshot 生成的 rollout。"""

    for example_id, replicate_id, record in _iter_rollouts(records):
        identity = f"{example_id}/{replicate_id}"
        raw_harness = record.get("harness")
        if not isinstance(raw_harness, Mapping):
            raise ValueError(
                f"{evidence_name} rollout {identity} has no Harness provenance"
            )
        if raw_harness.get("source_type") != "accepted_version":
            raise ValueError(
                f"{evidence_name} rollout {identity} is not an accepted-version rollout"
            )
        raw_store = raw_harness.get("checkpoint_store")
        if not isinstance(raw_store, str) or Path(raw_store).resolve() != store_root:
            raise ValueError(
                f"{evidence_name} rollout {identity} Harness Store mismatch"
            )
        if raw_harness.get("checkpoint_store_id") != checkpoint_store_id:
            raise ValueError(
                f"{evidence_name} rollout {identity} Checkpoint Store ID mismatch"
            )
        if raw_harness.get("version_id") != version_id:
            raise ValueError(
                f"{evidence_name} rollout {identity} version mismatch: "
                f"expected {version_id}, got {raw_harness.get('version_id')}"
            )
        if raw_harness.get("candidate_digest") != digest:
            raise ValueError(
                f"{evidence_name} rollout {identity} digest mismatch: "
                f"expected {digest}, got {raw_harness.get('candidate_digest')}"
            )


def validate_paired_rollouts(context: CriticContext) -> None:
    """Require identical replicate identities and sampling seeds for comparison."""

    if context.comparison is None:
        raise ValueError("paired rollout validation requires comparison evidence")
    primary = {
        (example_id, replicate_id): record
        for example_id, replicate_id, record in _iter_rollouts(
            context.rollout_records
        )
    }
    comparison = {
        (example_id, replicate_id): record
        for example_id, replicate_id, record in _iter_rollouts(
            context.comparison.rollout_records
        )
    }
    if set(primary) != set(comparison):
        raise ValueError("comparison rollout identities do not match primary evidence")
    for identity in sorted(primary):
        primary_seed = _sampling_seed(primary[identity])
        comparison_seed = _sampling_seed(comparison[identity])
        if primary_seed != comparison_seed:
            joined = "/".join(identity)
            raise ValueError(
                f"comparison rollout seed mismatch for {joined}: "
                f"primary={primary_seed}, comparison={comparison_seed}"
            )


def _iter_rollouts(
    records: Mapping[str, Mapping[str, Mapping[str, Any]]],
):
    for example_id, replicates in records.items():
        for replicate_id, record in replicates.items():
            yield example_id, replicate_id, record


def _sampling_seed(record: Mapping[str, Any]) -> object:
    replicate = record.get("replicate")
    return replicate.get("sampling_seed") if isinstance(replicate, Mapping) else None
