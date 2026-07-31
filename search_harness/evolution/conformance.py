"""Deterministic inputs and aggregation for Mechanism Conformance Replay."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from search_harness.datasets import DatasetExample
from search_harness.teacher.contracts import ConformanceFinding

from .experience import load_experience_set


CONFORMANCE_REPLICATES = 3


@dataclass(frozen=True)
class ConformanceCase:
    """One distinct intervention example and its distilled trial evidence."""

    example: DatasetExample
    trial_refs: tuple[str, ...]
    reference_observations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ConformanceSummary:
    """Program-owned suite decision derived from independent findings."""

    decision: str
    finding_counts: dict[str, int]
    per_example: dict[str, dict[str, Any]]
    compiler_feedback: tuple[str, ...]
    finding_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "finding_counts": dict(self.finding_counts),
            "per_example": {
                key: dict(value) for key, value in self.per_example.items()
            },
            "compiler_feedback": list(self.compiler_feedback),
            "finding_refs": list(self.finding_refs),
        }


def load_conformance_cases(
    *,
    experience_file: Path,
    trial_files: Iterable[Path],
) -> tuple[ConformanceCase, ...]:
    """Resolve distinct trial example IDs against the frozen Experience Set."""

    examples = {
        example.example_id: example
        for example in load_experience_set(experience_file)
    }
    evidence_by_example: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    order: list[str] = []
    for path in trial_files:
        artifact = _read_object(path)
        role_input = artifact.get("input")
        if not isinstance(role_input, dict):
            raise ValueError(f"intervention trial lacks role input: {path}")
        example_id = role_input.get("example_id")
        if not isinstance(example_id, str) or not example_id.strip():
            raise ValueError(f"intervention trial lacks example_id: {path}")
        if example_id not in examples:
            raise KeyError(
                f"intervention example is absent from Experience Set: "
                f"{example_id}"
            )
        if example_id not in evidence_by_example:
            order.append(example_id)
            evidence_by_example[example_id] = []
        trial_ref = path.parent.name
        evidence_by_example[example_id].append(
            (trial_ref, _reference_observation(artifact, trial_ref))
        )

    if not order:
        raise ValueError("conformance replay requires intervention trials")
    return tuple(
        ConformanceCase(
            example=examples[example_id],
            trial_refs=tuple(
                item[0] for item in evidence_by_example[example_id]
            ),
            reference_observations=tuple(
                item[1] for item in evidence_by_example[example_id]
            ),
        )
        for example_id in order
    )


def aggregate_conformance(
    *,
    cases: Iterable[ConformanceCase],
    findings: Iterable[ConformanceFinding],
    finding_refs: Iterable[str],
) -> ConformanceSummary:
    """Apply the per-example faithful and global failure rules."""

    case_items = tuple(cases)
    finding_items = tuple(findings)
    refs = tuple(finding_refs)
    if len(refs) != len(finding_items):
        raise ValueError("conformance finding refs must match findings")

    expected = {
        (
            case.example.example_id,
            f"r{replicate_index:03d}",
        )
        for case in case_items
        for replicate_index in range(CONFORMANCE_REPLICATES)
    }
    indexed: dict[tuple[str, str], ConformanceFinding] = {}
    for finding in finding_items:
        try:
            example_id, replicate_id = finding.candidate_run_ref.rsplit(
                "/",
                maxsplit=1,
            )
        except ValueError as exc:
            raise ValueError(
                "candidate_run_ref must be <example_id>/<replicate_id>"
            ) from exc
        key = (example_id, replicate_id)
        if key in indexed:
            raise ValueError(
                f"duplicate conformance finding: {finding.candidate_run_ref}"
            )
        indexed[key] = finding
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        raise ValueError(
            f"conformance findings do not match replay suite; "
            f"missing={missing}, extra={extra}"
        )

    counts = Counter(item.verdict for item in finding_items)
    hard_failures = {
        "runtime_error",
        "implementation_mismatch",
    }
    compiler_feedback = _unique(
        item.repair_obligation
        for item in finding_items
        if item.verdict in hard_failures
    )
    per_example: dict[str, dict[str, Any]] = {}
    missing_faithful = []
    for case in case_items:
        example_id = case.example.example_id
        local = [
            indexed[(example_id, f"r{index:03d}")]
            for index in range(CONFORMANCE_REPLICATES)
        ]
        local_counts = Counter(item.verdict for item in local)
        faithful_count = local_counts["faithful"]
        per_example[example_id] = {
            "faithful_count": faithful_count,
            "verdict_counts": dict(local_counts),
            "passed": faithful_count >= 1,
        }
        if faithful_count < 1:
            missing_faithful.append(example_id)
            compiler_feedback.extend(
                _unique(
                    item.repair_obligation
                    for item in local
                    if item.verdict in {"not_observed", "inconclusive"}
                )
            )

    decision = (
        "pass"
        if not (set(counts) & hard_failures) and not missing_faithful
        else "revise_implementation"
    )
    return ConformanceSummary(
        decision=decision,
        finding_counts=dict(counts),
        per_example=per_example,
        compiler_feedback=tuple(_unique(compiler_feedback)),
        finding_refs=refs,
    )


def runtime_error_finding(
    *,
    case: ConformanceCase,
    replicate_id: str,
    error: str,
) -> ConformanceFinding:
    """Create a deterministic finding when no model review is possible."""

    compact_error = " ".join(error.split())[:350]
    return ConformanceFinding(
        trial_refs=list(case.trial_refs),
        candidate_run_ref=f"{case.example.example_id}/{replicate_id}",
        verdict="runtime_error",
        observed_phases=[],
        assessment=f"Candidate rollout failed: {compact_error}",
        repair_obligation=(
            "Repair the compiled Harness so the complete Actor rollout "
            f"finishes without this runtime failure: {compact_error}"
        ),
    )


def _reference_observation(
    artifact: dict[str, Any],
    trial_ref: str,
) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    trial = resources.get("intervention_trial")
    if not isinstance(trial, dict):
        raise ValueError(
            f"intervention artifact lacks intervention_trial: {trial_ref}"
        )
    return {
        "trial_ref": trial_ref,
        "phase_plan": trial.get("phase_plan"),
        "activation_counts": trial.get("activation_counts"),
        "context_changes": trial.get("context_changes"),
        "phase_effects": trial.get("phase_effects"),
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return value


def _unique(values: Iterable[str | None]) -> list[str]:
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )
