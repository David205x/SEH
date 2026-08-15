"""Candidate Mechanism conformance replay and review effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from search_harness.evolution.research.conformance import (
    CONFORMANCE_REPLICATES,
    ConformanceCase,
    aggregate_conformance,
    load_conformance_cases,
    project_conformance_trajectory,
    runtime_error_finding,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    ConformanceFinding,
    ConformanceReviewBatch,
    MechanismSpec,
)
from search_harness.evolution.research.roles.runner import RoleRunner

from .domain import EffectResult
from .evaluation import CandidateArtifact, LocalEvaluationBackend


class ConformanceBatchFailed(RuntimeError):
    """Expose durable diagnostics and incurred usage for a failed review batch."""

    def __init__(
        self,
        message: str,
        *,
        failure_artifact: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.failure_artifact = failure_artifact


@dataclass(frozen=True)
class _ReviewedFinding:
    finding: ConformanceFinding
    path: Path
    incurred_tokens: int


@dataclass(frozen=True)
class _ReviewedBatch:
    findings: tuple[_ReviewedFinding, ...]
    incurred_tokens: int


class _FindingReviewFailed(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_path: Path,
        incurred_tokens: int,
    ) -> None:
        super().__init__(message)
        self.failure_path = failure_path
        self.incurred_tokens = incurred_tokens


class ConformanceEffects:
    """Replay a Candidate and review its fidelity to one Mechanism."""

    def __init__(
        self,
        *,
        backend: LocalEvaluationBackend,
        role_runner: RoleRunner,
        experience_file: Path,
        reviewer_template_root: Path,
        judge_workers: int,
    ) -> None:
        if judge_workers < 1:
            raise ValueError("conformance judge_workers must be positive")
        self.backend = backend
        self.role_runner = role_runner
        self.experience_file = experience_file
        self.reviewer_template_root = reviewer_template_root
        self.judge_workers = judge_workers

    async def verify(
        self,
        *,
        mechanism: MechanismSpec,
        trial_files: list[Path],
        candidate: CandidateArtifact,
        work_dir: Path,
    ) -> EffectResult:
        """Run required replays, review each trajectory, and aggregate them."""

        cases = load_conformance_cases(
            experience_file=self.experience_file,
            trial_files=trial_files,
        )
        suite_fingerprint = _suite_fingerprint(
            candidate=candidate,
            mechanism=mechanism,
            trial_files=trial_files,
            experience_file=self.experience_file,
        )
        checkpoint_dir = (
            work_dir.parent
            / "conformance_checkpoints"
            / suite_fingerprint[:24]
        )
        rollout_file = checkpoint_dir / "candidate_replays.jsonl"
        suite_path = checkpoint_dir / "suite.json"
        incurred_tokens = 0
        try:
            if suite_path.is_file():
                suite = _read_json(suite_path)
                if suite.get("fingerprint") != suite_fingerprint:
                    raise ValueError(
                        "Conformance checkpoint fingerprint does not match"
                    )
                if not rollout_file.is_file():
                    raise FileNotFoundError(
                        "Conformance checkpoint has no Candidate replay file"
                    )
                rollout_summary = suite.get("rollout_summary")
                if not isinstance(rollout_summary, dict):
                    raise TypeError(
                        "Conformance checkpoint rollout_summary must be an object"
                    )
            else:
                checkpoint_dir.mkdir(parents=True, exist_ok=True)
                rollout_summary = await asyncio.to_thread(
                    self.backend.rollout_candidate_examples,
                    candidate=candidate,
                    examples=tuple(case.example for case in cases),
                    experience_file=self.experience_file,
                    output_file=rollout_file,
                    rollouts_per_example=CONFORMANCE_REPLICATES,
                )
                records = _read_jsonl(rollout_file)
                rollout_tokens = _rollout_total_tokens(records)
                incurred_tokens += rollout_tokens
                _write_json_atomic(
                    suite_path,
                    {
                        "schema_version": 1,
                        "fingerprint": suite_fingerprint,
                        "candidate_attempt_id": candidate.candidate_attempt_id,
                        "candidate_digest": candidate.candidate_digest,
                        "rollout_summary": rollout_summary,
                        "rollout_tokens": rollout_tokens,
                    },
                )
            records = _read_jsonl(rollout_file)
        except Exception as exc:
            if (
                incurred_tokens == 0
                and not suite_path.is_file()
                and rollout_file.is_file()
            ):
                try:
                    incurred_tokens += _rollout_total_tokens(
                        _read_jsonl(rollout_file)
                    )
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
            raise _batch_failure(
                stage="candidate_replay",
                exc=exc,
                checkpoint_dir=checkpoint_dir,
                incurred_tokens=incurred_tokens,
            ) from exc

        local_report_dir = checkpoint_dir / "local_evaluation"
        local_rollout_report = local_report_dir / "per_rollout.jsonl"
        try:
            if local_rollout_report.is_file():
                evaluated_rollouts = _read_jsonl(local_rollout_report)
            else:
                local_report = await asyncio.to_thread(
                    self.backend.evaluate_existing_rollouts,
                    rollout_file=rollout_file,
                    output_dir=local_report_dir,
                )
                incurred_tokens += _teacher_judge_total_tokens(local_report)
                evaluated_rollouts = list(local_report.get("rollouts", []))
            local_evaluations = _index_local_evaluations(evaluated_rollouts)
        except Exception as exc:
            raise _batch_failure(
                stage="local_efficacy_evaluation",
                exc=exc,
                checkpoint_dir=checkpoint_dir,
                incurred_tokens=incurred_tokens,
            ) from exc

        try:
            indexed_records = _index_rollout_records(records)
        except Exception as exc:
            raise _batch_failure(
                stage="candidate_replay_validation",
                exc=exc,
                checkpoint_dir=checkpoint_dir,
                incurred_tokens=incurred_tokens,
            ) from exc
        semaphore = asyncio.Semaphore(self.judge_workers)

        async def review_case(
            case: ConformanceCase,
            case_index: int,
            records_for_case: list[tuple[str, dict[str, Any], int]],
        ) -> _ReviewedBatch:
            artifact: dict[str, Any] | None = None
            batch_tokens = 0
            first_finding_index = records_for_case[0][2]
            expected_run_ref = f"{case.example.example_id}/batch"
            prepared = []
            for replicate_id, record, finding_index in records_for_case:
                trajectory = project_conformance_trajectory(
                    record,
                    evaluation=local_evaluations.get(
                        (case.example.example_id, replicate_id)
                    ),
                )
                run_ref = f"{case.example.example_id}/{replicate_id}"
                prepared.append(
                    {
                        "replicate_id": replicate_id,
                        "record": record,
                        "finding_index": finding_index,
                        "run_ref": run_ref,
                        "trajectory": trajectory,
                        "input_digest": _finding_input_digest(
                            mechanism=mechanism,
                            trial_refs=case.trial_refs,
                            reference_observations=case.reference_observations,
                            candidate_run_ref=run_ref,
                            trajectory=trajectory,
                        ),
                        "path": checkpoint_dir
                        / "findings"
                        / f"finding_{finding_index:03d}.json",
                    }
                )
            try:
                completed_by_id: dict[str, _ReviewedFinding] = {}
                for item in prepared:
                    path = item["path"]
                    if not path.is_file():
                        continue
                    checkpoint = _read_json(path)
                    if checkpoint.get("input_digest") != item["input_digest"]:
                        raise ValueError(
                            "Conformance Finding checkpoint input changed: "
                            f"{path}"
                        )
                    finding = ConformanceFinding.model_validate(
                        checkpoint.get("output")
                    )
                    if finding.candidate_run_ref != item["run_ref"]:
                        raise ValueError(
                            "Conformance Finding checkpoint identity changed: "
                            f"{path}"
                        )
                    completed_by_id[item["replicate_id"]] = _ReviewedFinding(
                        finding,
                        path.resolve(),
                        0,
                    )
                if len(completed_by_id) == len(prepared):
                    return _ReviewedBatch(
                        tuple(
                            completed_by_id[item["replicate_id"]]
                            for item in prepared
                        ),
                        0,
                    )

                model_items = [
                    item
                    for item in prepared
                    if not isinstance(item["record"].get("runner_error"), dict)
                ]
                batch_reviews = {}
                batch_path = (
                    checkpoint_dir
                    / "batches"
                    / f"batch_{case_index:03d}.json"
                )
                if model_items:
                    batch_digest = _conformance_batch_input_digest(
                        mechanism=mechanism,
                        trial_refs=case.trial_refs,
                        reference_observations=case.reference_observations,
                        example_id=case.example.example_id,
                        trajectories=[
                            {
                                "replicate_id": item["replicate_id"],
                                "candidate_trajectory_view": item["trajectory"],
                            }
                            for item in model_items
                        ],
                    )
                    if batch_path.is_file():
                        batch_checkpoint = _read_json(batch_path)
                        if batch_checkpoint.get("input_digest") != batch_digest:
                            raise ValueError(
                                "Conformance batch checkpoint input changed: "
                                f"{batch_path}"
                            )
                        batch = ConformanceReviewBatch.model_validate(
                            batch_checkpoint.get("output")
                        )
                    else:
                        async with semaphore:
                            artifact = await self.role_runner.run(
                                template_root=self.reviewer_template_root,
                                role_id="conformance_reviewer",
                                role_version=1,
                                role_input={
                                    "mechanism": mechanism.model_dump(mode="json"),
                                    "trial_refs": list(case.trial_refs),
                                    "reference_observations": list(
                                        case.reference_observations
                                    ),
                                    "example_id": case.example.example_id,
                                    "candidate_trajectory_views": [
                                        {
                                            "replicate_id": item["replicate_id"],
                                            "candidate_trajectory_view": item[
                                                "trajectory"
                                            ],
                                        }
                                        for item in model_items
                                    ],
                                },
                                resource_config=TeacherResourceConfig(),
                            )
                        batch_tokens = _artifact_total_tokens(artifact)
                        batch = ConformanceReviewBatch.model_validate(
                            artifact.get("output")
                        )
                        _write_json_atomic(
                            batch_path,
                            {
                                "schema_version": 1,
                                "status": "completed",
                                "input_digest": batch_digest,
                                "example_id": case.example.example_id,
                                "output": batch.model_dump(mode="json"),
                                "role_artifact": artifact,
                                "usage": {"total_tokens": batch_tokens},
                            },
                        )
                    expected_ids = [
                        item["replicate_id"] for item in model_items
                    ]
                    actual_ids = [
                        finding.replicate_id for finding in batch.findings
                    ]
                    if actual_ids != expected_ids:
                        raise ValueError(
                            "Conformance batch findings must match supplied "
                            f"replicate order; expected={expected_ids}, "
                            f"actual={actual_ids}"
                        )
                    batch_reviews = {
                        finding.replicate_id: finding
                        for finding in batch.findings
                    }

                for item in prepared:
                    replicate_id = item["replicate_id"]
                    if replicate_id in completed_by_id:
                        continue
                    runner_error = item["record"].get("runner_error")
                    if isinstance(runner_error, dict):
                        finding = runtime_error_finding(
                            case=case,
                            replicate_id=replicate_id,
                            error=(
                                f"{runner_error.get('type', 'RunnerError')}: "
                                f"{runner_error.get('message', '')}"
                            ),
                        )
                        artifact_ref = None
                    else:
                        review = batch_reviews[replicate_id]
                        finding = ConformanceFinding(
                            **review.model_dump(
                                mode="python",
                                exclude={"replicate_id"},
                            ),
                            trial_refs=list(case.trial_refs),
                            candidate_run_ref=item["run_ref"],
                        )
                        artifact_ref = str(batch_path.resolve())
                    finding = _normalize_finding_phases(
                        finding=finding,
                        mechanism=mechanism,
                    )
                    _write_json_atomic(
                        item["path"],
                        {
                            "schema_version": 2,
                            "status": "completed",
                            "input_digest": item["input_digest"],
                            "identity": {
                                "candidate_run_ref": item["run_ref"],
                                "trial_refs": list(case.trial_refs),
                            },
                            "output": finding.model_dump(mode="json"),
                            "role_artifact_ref": artifact_ref,
                            "usage": {"total_tokens": 0},
                        },
                    )
                    completed_by_id[replicate_id] = _ReviewedFinding(
                        finding,
                        item["path"].resolve(),
                        0,
                    )
                return _ReviewedBatch(
                    tuple(
                        completed_by_id[item["replicate_id"]]
                        for item in prepared
                    ),
                    batch_tokens,
                )
            except Exception as exc:
                failure_artifact = getattr(exc, "failure_artifact", None)
                if artifact is None and isinstance(failure_artifact, dict):
                    artifact = failure_artifact
                batch_tokens = max(
                    batch_tokens,
                    _artifact_total_tokens(artifact),
                )
                failure_path = _write_finding_failure(
                    checkpoint_dir=checkpoint_dir,
                    finding_index=first_finding_index,
                    candidate_run_ref=expected_run_ref,
                    trial_refs=case.trial_refs,
                    input_digest=_json_digest(
                        {
                            "example_id": case.example.example_id,
                            "finding_inputs": [
                                item["input_digest"] for item in prepared
                            ],
                        }
                    ),
                    exc=exc,
                    role_artifact=artifact,
                    incurred_tokens=batch_tokens,
                )
                raise _FindingReviewFailed(
                    f"{expected_run_ref}: {type(exc).__name__}: {exc}",
                    failure_path=failure_path,
                    incurred_tokens=batch_tokens,
                ) from exc

        jobs = []
        finding_index = 0
        for case_index, case in enumerate(cases, start=1):
            records_for_case = []
            for replicate_index in range(CONFORMANCE_REPLICATES):
                finding_index += 1
                replicate_id = f"r{replicate_index:03d}"
                key = (case.example.example_id, replicate_id)
                record = indexed_records.get(key)
                if record is None:
                    record = {
                        "runner_error": {
                            "type": "MissingReplay",
                            "message": (
                                "Candidate replay batch ended before this "
                                "required replicate was written."
                            ),
                        }
                    }
                records_for_case.append(
                    (replicate_id, record, finding_index)
                )
            jobs.append(review_case(case, case_index, records_for_case))
        reviewed_results = await asyncio.gather(*jobs, return_exceptions=True)
        failures = [
            item
            for item in reviewed_results
            if isinstance(item, BaseException)
        ]
        batches = [
            item for item in reviewed_results if isinstance(item, _ReviewedBatch)
        ]
        completed = [
            finding
            for batch in batches
            for finding in batch.findings
        ]
        incurred_tokens += sum(item.incurred_tokens for item in batches)
        incurred_tokens += sum(
            item.incurred_tokens
            for item in failures
            if isinstance(item, _FindingReviewFailed)
        )
        if failures:
            raise _batch_failure(
                stage="review_findings",
                exc=RuntimeError(
                    f"{len(failures)} of {len(jobs)} Conformance batches failed"
                ),
                checkpoint_dir=checkpoint_dir,
                incurred_tokens=incurred_tokens,
                finding_failures=failures,
            )

        findings = [item.finding for item in completed]
        finding_paths = [item.path for item in completed]
        try:
            summary = aggregate_conformance(
                cases=cases,
                findings=findings,
                finding_refs=[str(path) for path in finding_paths],
            )
            summary_path = _write_json_atomic(
                checkpoint_dir / "summary.json",
                {**summary.to_dict(), "rollout": rollout_summary},
            )
        except Exception as exc:
            raise _batch_failure(
                stage="aggregate_findings",
                exc=exc,
                checkpoint_dir=checkpoint_dir,
                incurred_tokens=incurred_tokens,
            ) from exc
        refs = {
            "conformance_rollout_file": str(rollout_file.resolve()),
            "conformance_local_evaluation": str(
                local_report_dir.resolve()
            ),
            "conformance_summary_artifact": str(summary_path),
            **{
                f"conformance_finding_{index:03d}": str(path)
                for index, path in enumerate(finding_paths, start=1)
            },
        }
        return EffectResult(
            outcome={
                "decision": summary.decision,
                "summary": summary.to_dict(),
            },
            artifact_refs=refs,
            usage={
                "total_tokens": incurred_tokens,
            },
        )


def summarize_conformance_review(
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Project a full Conformance Summary into Candidate Review input."""

    per_example = summary.get("per_example")
    per_example = per_example if isinstance(per_example, dict) else {}
    passed = sum(
        isinstance(value, dict) and value.get("passed") is True
        for value in per_example.values()
    )
    return {
        "decision": summary.get("decision"),
        "finding_counts": summary.get("finding_counts"),
        "failure_layer_counts": summary.get("failure_layer_counts"),
        "recommended_route_counts": summary.get("recommended_route_counts"),
        "example_count": len(per_example),
        "passed_example_count": passed,
        "local_efficacy_counts": summary.get("local_efficacy_counts"),
        "local_efficacy_gate": summary.get("local_efficacy_gate"),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(
                f"JSONL record must be an object: {path}:{line_number}"
            )
        records.append(value)
    return records


def _index_rollout_records(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed = {}
    for record in records:
        example = record.get("example")
        replicate = record.get("replicate")
        if not isinstance(example, dict) or not isinstance(replicate, dict):
            raise ValueError("conformance rollout lacks example or replicate")
        key = (
            str(example.get("example_id")),
            str(replicate.get("replicate_id")),
        )
        if key in indexed:
            raise ValueError(f"duplicate conformance rollout: {key}")
        indexed[key] = record
    return indexed


def _index_local_evaluations(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed = {}
    for record in records:
        example_id = record.get("example_id")
        replicate_id = record.get("replicate_id")
        if not isinstance(example_id, str) or not isinstance(
            replicate_id,
            str,
        ):
            raise ValueError("local Evaluation result lacks rollout identity")
        teacher = record.get("teacher")
        teacher = teacher if isinstance(teacher, dict) else {}
        indexed[(example_id, replicate_id)] = {
            "score": record.get("score"),
            "score_source": record.get("score_source"),
            "teacher_assessment": teacher.get("assessment"),
            "run_status": record.get("run_status"),
        }
    return indexed


def _teacher_judge_total_tokens(report: dict[str, Any]) -> int:
    total = 0
    rollouts = report.get("rollouts")
    rollouts = rollouts if isinstance(rollouts, list) else []
    for rollout in rollouts:
        if not isinstance(rollout, dict):
            continue
        teacher = rollout.get("teacher")
        teacher = teacher if isinstance(teacher, dict) else {}
        metadata = teacher.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        usage = metadata.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        reported = usage.get("total_tokens")
        if isinstance(reported, int) and not isinstance(reported, bool):
            total += max(0, reported)
            continue
        total += _non_negative_int(
            usage.get("prompt_tokens", usage.get("prompt_eval_count"))
        )
        total += _non_negative_int(
            usage.get(
                "completion_tokens",
                usage.get("eval_count"),
            )
        )
    return total


def _rollout_total_tokens(records: list[dict[str, Any]]) -> int:
    total = 0
    for record in records:
        run = record.get("run")
        if not isinstance(run, dict):
            continue
        trace = run.get("trace")
        if not isinstance(trace, list):
            continue
        for event in trace:
            if not isinstance(event, dict) or event.get("event_type") not in {
                "model_output",
                "hook_model_output",
            }:
                continue
            payload = event.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            metadata = payload.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            usage = metadata.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            value = usage.get("total_tokens")
            if isinstance(value, int) and not isinstance(value, bool):
                total += max(0, value)
                continue
            prompt = usage.get(
                "prompt_tokens",
                usage.get("prompt_eval_count", 0),
            )
            completion = usage.get(
                "completion_tokens",
                usage.get("eval_count", 0),
            )
            total += _non_negative_int(prompt)
            total += _non_negative_int(completion)
    return total


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{uuid4().hex[:8]}.tmp"
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path.resolve()


def _suite_fingerprint(
    *,
    candidate: CandidateArtifact,
    mechanism: MechanismSpec,
    trial_files: list[Path],
    experience_file: Path,
) -> str:
    payload = {
        "conformance_input_schema": 5,
        "candidate_attempt_id": candidate.candidate_attempt_id,
        "candidate_digest": candidate.candidate_digest,
        "mechanism": mechanism.model_dump(mode="json"),
        "experience_digest": _file_digest(experience_file),
        "trials": [
            {
                "path": str(path.resolve()),
                "digest": _file_digest(path),
            }
            for path in trial_files
        ],
    }
    return _json_digest(payload)


def _finding_input_digest(
    *,
    mechanism: MechanismSpec,
    trial_refs: tuple[str, ...],
    reference_observations: tuple[dict[str, Any], ...],
    candidate_run_ref: str,
    trajectory: dict[str, Any],
) -> str:
    return _json_digest(
        {
            "mechanism": mechanism.model_dump(mode="json"),
            "trial_refs": list(trial_refs),
            "reference_observations": list(reference_observations),
            "candidate_run_ref": candidate_run_ref,
            "candidate_trajectory_view": trajectory,
        }
    )


def _conformance_batch_input_digest(
    *,
    mechanism: MechanismSpec,
    trial_refs: tuple[str, ...],
    reference_observations: tuple[dict[str, Any], ...],
    example_id: str,
    trajectories: list[dict[str, Any]],
) -> str:
    return _json_digest(
        {
            "mechanism": mechanism.model_dump(mode="json"),
            "trial_refs": list(trial_refs),
            "reference_observations": list(reference_observations),
            "example_id": example_id,
            "candidate_trajectory_views": trajectories,
        }
    )


def _normalize_finding_phases(
    *,
    finding: ConformanceFinding,
    mechanism: MechanismSpec,
) -> ConformanceFinding:
    """Remove undeclared phases and prevent an empty faithful finding."""

    allowed_phases = {rule.phase for rule in mechanism.phase_rules}
    relevant_phases = [
        phase for phase in finding.observed_phases if phase in allowed_phases
    ]
    if relevant_phases == finding.observed_phases:
        return finding
    payload = finding.model_dump(mode="json")
    payload["observed_phases"] = relevant_phases
    if finding.verdict == "faithful" and not relevant_phases:
        payload.update(
            {
                "verdict": "inconclusive",
                "assessment": (
                    "The review named only phases outside the supplied "
                    "MechanismSpec, so it did not establish implementation "
                    "fidelity."
                ),
                "repair_obligation": (
                    "Make the mechanism's declared phase activation observable "
                    "in the complete Candidate rollout."
                ),
                "failure_layer": "integration",
                "decisive_input_summary": (
                    "The review named no declared mechanism phase observable "
                    "in this rollout."
                ),
                "recommended_route": "implementation",
            }
        )
    return ConformanceFinding.model_validate(payload)


def _json_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_total_tokens(artifact: object) -> int:
    if not isinstance(artifact, dict):
        return 0
    usage = artifact.get("usage")
    if not isinstance(usage, dict):
        return 0
    return _non_negative_int(usage.get("total_tokens"))


def _write_finding_failure(
    *,
    checkpoint_dir: Path,
    finding_index: int,
    candidate_run_ref: str,
    trial_refs: tuple[str, ...],
    input_digest: str,
    exc: Exception,
    role_artifact: dict[str, Any] | None,
    incurred_tokens: int,
) -> Path:
    return _write_json_atomic(
        checkpoint_dir
        / "failures"
        / f"finding_{finding_index:03d}_{uuid4().hex[:8]}.json",
        {
            "schema_version": 1,
            "status": "failed",
            "stage": "review_finding",
            "input_digest": input_digest,
            "identity": {
                "candidate_run_ref": candidate_run_ref,
                "trial_refs": list(trial_refs),
            },
            "error": _error_diagnostic(exc),
            "role_artifact": role_artifact,
            "usage": {"total_tokens": incurred_tokens},
        },
    )


def _batch_failure(
    *,
    stage: str,
    exc: Exception,
    checkpoint_dir: Path,
    incurred_tokens: int,
    finding_failures: list[BaseException] | None = None,
) -> ConformanceBatchFailed:
    failures = []
    for failure in finding_failures or []:
        item = {
            "type": type(failure).__name__,
            "message": str(failure),
        }
        if isinstance(failure, _FindingReviewFailed):
            item["failure_artifact"] = str(failure.failure_path)
            item["total_tokens"] = failure.incurred_tokens
        failures.append(item)
    artifact = {
        "schema_version": 1,
        "status": "failed",
        "role": {"id": "conformance_reviewer", "version": 1},
        "stage": stage,
        "error": _error_diagnostic(exc),
        "finding_failures": failures,
        "checkpoint_dir": str(checkpoint_dir.resolve()),
        "usage": {"total_tokens": incurred_tokens},
    }
    return ConformanceBatchFailed(
        f"Conformance batch failed during {stage}: {exc}",
        failure_artifact=artifact,
    )


def _error_diagnostic(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
