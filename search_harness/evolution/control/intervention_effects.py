"""Intervention trial selection and branch execution effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from search_harness.evolution.research.intervention.prefix import (
    build_prefix_timeline,
    list_rollout_references,
    load_rollout_record,
)
from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.resources.stores import (
    InterventionResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    FailureDirection,
    InterventionHypothesis,
    InterventionWorkerInput,
    InterventionWorkerResult,
)

from .domain import EffectResult


class InterventionBatchFailed(RuntimeError):
    """Expose durable diagnostics and usage for a failed Trial batch."""

    def __init__(
        self,
        message: str,
        *,
        failure_artifact: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.failure_artifact = failure_artifact


@dataclass(frozen=True)
class _ExecutedAssignment:
    assignment_key: str
    output: dict[str, Any]
    artifact_key: str
    path: Path
    incurred_tokens: int


class _AssignmentExecutionFailed(RuntimeError):
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


class InterventionEffects:
    """Select evidence prefixes and execute assigned Intervention trials."""

    def __init__(
        self,
        *,
        role_runner: InterventionRoleRunner,
        worker_template_root: Path,
        student_template_root: Path,
        env_file: Path,
        student_max_steps: int,
    ) -> None:
        self.role_runner = role_runner
        self.worker_template_root = worker_template_root
        self.student_template_root = student_template_root
        self.env_file = env_file
        self.student_max_steps = student_max_steps

    def select_trial(
        self,
        *,
        failure: FailureDirection,
        hypothesis: InterventionHypothesis,
        rollout_file: Path,
        used_assignments: set[str],
        assignment_count: int,
        trial_batch_size: int,
        remaining_trial_budget: int,
        remaining_assignment_budget: int,
        prior_obligation: object,
        work_dir: Path,
    ) -> EffectResult:
        """Select one deterministic example-first batch for a frozen hypothesis."""

        used = set(used_assignments)
        candidate_refs = tuple(dict.fromkeys(
            [
                *failure.evidence_refs,
                *list_rollout_references(rollout_file),
            ]
        ))
        selection_limit = min(
            _positive_int(trial_batch_size, "trial_batch_size"),
            _non_negative_budget(
                remaining_trial_budget,
                "remaining_trial_budget",
            ),
            _non_negative_budget(
                remaining_assignment_budget,
                "remaining_assignment_budget",
            ),
        )
        candidates: list[dict[str, Any]] = []
        for evidence_ref in candidate_refs:
            example_id, replicate_id = evidence_ref.split("/", maxsplit=1)
            record = load_rollout_record(
                rollout_file,
                example_id,
                replicate_id,
            )
            if not isinstance(record.get("run"), dict):
                continue
            for boundary in build_prefix_timeline(record):
                if boundary.get("phase") != hypothesis.fork_phase:
                    continue
                prefix_id = boundary.get("prefix_id")
                if not isinstance(prefix_id, int):
                    continue
                assignment_key = (
                    f"{example_id}/{replicate_id}/{prefix_id}"
                )
                if assignment_key in used:
                    continue
                candidates.append(
                    {
                        "key": assignment_key,
                        "example_id": example_id,
                        "replicate_id": replicate_id,
                        "prefix_id": prefix_id,
                    }
                )

        used_examples, used_replicates = _used_coverage(used)
        selected: list[dict[str, Any]] = []
        selected_keys: set[str] = set()
        batch_examples: set[str] = set()
        fresh_count = 0

        for candidate in candidates:
            if len(selected) >= selection_limit:
                break
            example_id = str(candidate["example_id"])
            if example_id in used_examples or example_id in batch_examples:
                continue
            _select_candidate(
                candidate,
                selected=selected,
                selected_keys=selected_keys,
            )
            batch_examples.add(example_id)
            fresh_count += 1

        for candidate in candidates:
            if len(selected) >= selection_limit:
                break
            example_id = str(candidate["example_id"])
            replicate_id = str(candidate["replicate_id"])
            if example_id not in used_examples or example_id in batch_examples:
                continue
            if replicate_id in used_replicates.get(example_id, set()):
                continue
            if str(candidate["key"]) in selected_keys:
                continue
            _select_candidate(
                candidate,
                selected=selected,
                selected_keys=selected_keys,
            )
            batch_examples.add(example_id)

        for candidate in candidates:
            if len(selected) >= selection_limit:
                break
            if str(candidate["key"]) in selected_keys:
                continue
            _select_candidate(
                candidate,
                selected=selected,
                selected_keys=selected_keys,
            )

        if selected:
            objective = _trial_objective(hypothesis, prior_obligation)
            assignments = [
                {
                    "trial_objective": objective,
                    "example_id": candidate["example_id"],
                    "replicate_id": candidate["replicate_id"],
                    "prefix_id": candidate["prefix_id"],
                    "prohibited_content": [],
                }
                for candidate in selected
            ]
            used.update(selected_keys)
            assignment_count += len(assignments)
            selection = {
                "status": "selected",
                "selection_mode": "fresh" if fresh_count else "reuse",
                "assignments": assignments,
                "assignment_count": assignment_count,
                "used_assignments": sorted(used),
            }
            path = _write_json(work_dir / "selection.json", selection)
            return EffectResult(
                outcome=selection,
                artifact_refs={"selection_artifact": str(path)},
            )
        exhausted = {
            "status": "exhausted",
            "selection_mode": "reuse",
            "assignments": [],
            "assignment_count": assignment_count,
            "used_assignments": sorted(used),
        }
        path = _write_json(work_dir / "selection.json", exhausted)
        return EffectResult(
            outcome=exhausted,
            artifact_refs={"selection_artifact": str(path)},
        )

    async def execute_trial(
        self,
        *,
        assignment: dict[str, Any],
        hypothesis: dict[str, Any],
        rollout_file: Path,
        work_dir: Path,
    ) -> EffectResult:
        """Execute one assigned branch through the Intervention Role Runner."""

        artifact = await self.role_runner.run(
            template_root=self.worker_template_root,
            role_input={"hypothesis": hypothesis, **assignment},
            resource_config=TeacherResourceConfig(
                intervention=InterventionResourceConfig(
                    rollout_file=rollout_file,
                    student_template_root=self.student_template_root,
                    env_file=self.env_file,
                    student_max_steps=self.student_max_steps,
                )
            ),
        )
        output = InterventionWorkerResult.model_validate(
            artifact.get("output")
        )
        path = _write_json(work_dir / "trial.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"worker_artifact": str(path)},
        )

    async def execute_batch(
        self,
        *,
        assignments: list[dict[str, Any]],
        hypothesis: dict[str, Any],
        rollout_file: Path,
        max_workers: int,
        work_dir: Path,
    ) -> EffectResult:
        """Execute independent Assignments concurrently with stable checkpoints."""

        if not assignments:
            raise ValueError("Intervention Trial batch must not be empty")
        worker_limit = _positive_int(max_workers, "max_workers")
        validated_inputs = [
            InterventionWorkerInput.model_validate(
                {"hypothesis": hypothesis, **assignment}
            ).model_dump(mode="json")
            for assignment in assignments
        ]
        fingerprint = _batch_fingerprint(
            assignments=assignments,
            hypothesis=hypothesis,
            rollout_file=rollout_file,
        )
        checkpoint_dir = (
            work_dir.parent
            / "intervention_trial_checkpoints"
            / fingerprint[:24]
        )
        semaphore = asyncio.Semaphore(worker_limit)

        async def execute_assignment(
            index: int,
            assignment: dict[str, Any],
            expected_input: dict[str, Any],
        ) -> _ExecutedAssignment:
            assignment_key = _assignment_key(assignment)
            artifact_key = f"worker_artifact_{index:03d}"
            trial_dir = (
                checkpoint_dir
                / "trials"
                / f"trial_{fingerprint[:12]}_{index:03d}"
            )
            path = trial_dir / "trial.json"
            if path.is_file():
                artifact = _read_json(path)
                stored_input = InterventionWorkerInput.model_validate(
                    artifact.get("input")
                ).model_dump(mode="json")
                if stored_input != expected_input:
                    raise ValueError(
                        "Intervention Trial checkpoint input changed: "
                        f"{path}"
                    )
                output = InterventionWorkerResult.model_validate(
                    artifact.get("output")
                )
                return _ExecutedAssignment(
                    assignment_key=assignment_key,
                    output=output.model_dump(mode="json"),
                    artifact_key=artifact_key,
                    path=path.resolve(),
                    incurred_tokens=0,
                )

            try:
                async with semaphore:
                    result = await self.execute_trial(
                        assignment=assignment,
                        hypothesis=hypothesis,
                        rollout_file=rollout_file,
                        work_dir=trial_dir,
                    )
                path = Path(result.artifact_refs["worker_artifact"])
                return _ExecutedAssignment(
                    assignment_key=assignment_key,
                    output=dict(result.outcome["output"]),
                    artifact_key=artifact_key,
                    path=path,
                    incurred_tokens=_effect_total_tokens(result),
                )
            except Exception as exc:
                incurred_tokens = _exception_total_tokens(exc)
                failure_path = _write_json_atomic(
                    checkpoint_dir
                    / "failures"
                    / f"assignment_{index:03d}_{uuid4().hex[:8]}.json",
                    {
                        "schema_version": 1,
                        "status": "failed",
                        "assignment_key": assignment_key,
                        "error": _error_diagnostic(exc),
                        "role_artifact": getattr(
                            exc,
                            "failure_artifact",
                            None,
                        ),
                        "usage": {"total_tokens": incurred_tokens},
                    },
                )
                raise _AssignmentExecutionFailed(
                    f"{assignment_key}: {type(exc).__name__}: {exc}",
                    failure_path=failure_path,
                    incurred_tokens=incurred_tokens,
                ) from exc

        jobs = [
            execute_assignment(index, assignment, expected_input)
            for index, (assignment, expected_input) in enumerate(
                zip(assignments, validated_inputs, strict=True),
                start=1,
            )
        ]
        raw_results = await asyncio.gather(*jobs, return_exceptions=True)
        failures = [
            item for item in raw_results if isinstance(item, BaseException)
        ]
        completed = [
            item
            for item in raw_results
            if isinstance(item, _ExecutedAssignment)
        ]
        incurred_tokens = sum(item.incurred_tokens for item in completed)
        incurred_tokens += sum(
            item.incurred_tokens
            for item in failures
            if isinstance(item, _AssignmentExecutionFailed)
        )
        if failures:
            raise _intervention_batch_failure(
                checkpoint_dir=checkpoint_dir,
                failures=failures,
                incurred_tokens=incurred_tokens,
            )

        return EffectResult(
            outcome={
                "results": [
                    {
                        "assignment_key": item.assignment_key,
                        "output": item.output,
                        "artifact_key": item.artifact_key,
                    }
                    for item in completed
                ]
            },
            artifact_refs={
                item.artifact_key: str(item.path) for item in completed
            },
            usage={"total_tokens": incurred_tokens},
        )


def _trial_objective(
    hypothesis: InterventionHypothesis,
    prior_obligation: object,
) -> str:
    parts = [
        hypothesis.evaluation.primary_signal,
        hypothesis.evaluation.success_condition,
        hypothesis.evaluation.falsifier,
    ]
    if isinstance(prior_obligation, str) and prior_obligation.strip():
        parts.append(prior_obligation)
    return " | ".join(parts)


def _used_coverage(
    used_assignments: set[str],
) -> tuple[set[str], dict[str, set[str]]]:
    """Project exact Assignment keys into example and replicate coverage."""

    examples: set[str] = set()
    replicates: dict[str, set[str]] = {}
    for assignment_key in used_assignments:
        parts = assignment_key.split("/")
        if len(parts) != 3 or any(not part for part in parts):
            raise ValueError(
                "used assignment keys must use "
                "example_id/replicate_id/prefix_id format"
            )
        example_id, replicate_id, prefix_id = parts
        try:
            parsed_prefix = int(prefix_id)
        except ValueError as exc:
            raise ValueError(
                "used assignment prefix_id must be an integer"
            ) from exc
        if parsed_prefix < 1:
            raise ValueError("used assignment prefix_id must be positive")
        examples.add(example_id)
        replicates.setdefault(example_id, set()).add(replicate_id)
    return examples, replicates


def _select_candidate(
    candidate: dict[str, Any],
    *,
    selected: list[dict[str, Any]],
    selected_keys: set[str],
) -> None:
    selected.append(candidate)
    selected_keys.add(str(candidate["key"]))


def _assignment_key(assignment: dict[str, Any]) -> str:
    example_id = assignment.get("example_id")
    replicate_id = assignment.get("replicate_id")
    prefix_id = assignment.get("prefix_id")
    if not isinstance(example_id, str) or not example_id:
        raise TypeError("assignment example_id must be a non-empty string")
    if not isinstance(replicate_id, str) or not replicate_id:
        raise TypeError("assignment replicate_id must be a non-empty string")
    if not isinstance(prefix_id, int) or isinstance(prefix_id, bool):
        raise TypeError("assignment prefix_id must be an integer")
    if prefix_id < 1:
        raise ValueError("assignment prefix_id must be positive")
    return f"{example_id}/{replicate_id}/{prefix_id}"


def _batch_fingerprint(
    *,
    assignments: list[dict[str, Any]],
    hypothesis: dict[str, Any],
    rollout_file: Path,
) -> str:
    payload = {
        "intervention_batch_schema": 1,
        "assignments": assignments,
        "hypothesis": hypothesis,
        "rollout_file": str(rollout_file.resolve()),
        "rollout_digest": hashlib.sha256(rollout_file.read_bytes()).hexdigest(),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _intervention_batch_failure(
    *,
    checkpoint_dir: Path,
    failures: list[BaseException],
    incurred_tokens: int,
) -> InterventionBatchFailed:
    failure_items = []
    for failure in failures:
        item: dict[str, Any] = {
            "type": type(failure).__name__,
            "message": str(failure),
        }
        if isinstance(failure, _AssignmentExecutionFailed):
            item["failure_artifact"] = str(failure.failure_path)
            item["total_tokens"] = failure.incurred_tokens
        failure_items.append(item)
    artifact = {
        "schema_version": 1,
        "status": "failed",
        "role": {"id": "intervention_worker", "version": 1},
        "stage": "execute_trial_batch",
        "assignment_failures": failure_items,
        "checkpoint_dir": str(checkpoint_dir.resolve()),
        "usage": {"total_tokens": incurred_tokens},
    }
    return InterventionBatchFailed(
        f"Intervention Trial batch failed: {len(failures)} assignment(s)",
        failure_artifact=artifact,
    )


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


def _error_diagnostic(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }


def _effect_total_tokens(result: EffectResult) -> int:
    return _non_negative_int(result.usage.get("total_tokens"))


def _exception_total_tokens(exc: Exception) -> int:
    artifact = getattr(exc, "failure_artifact", None)
    if not isinstance(artifact, dict):
        return 0
    usage = artifact.get("usage")
    if not isinstance(usage, dict):
        return 0
    return _non_negative_int(usage.get("total_tokens"))


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_budget(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _role_result(
    output: dict[str, Any],
    artifact: dict[str, Any],
    refs: dict[str, str],
) -> EffectResult:
    usage = artifact.get("usage")
    total_tokens = (
        usage.get("total_tokens", 0)
        if isinstance(usage, dict)
        else 0
    )
    return EffectResult(
        outcome={"output": output},
        artifact_refs=refs,
        usage={"total_tokens": _non_negative_int(total_tokens)},
    )


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
