"""Candidate Mechanism conformance replay and review effects."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.conformance import (
    CONFORMANCE_REPLICATES,
    ConformanceCase,
    aggregate_conformance,
    load_conformance_cases,
    runtime_error_finding,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    ConformanceFinding,
    MechanismSpec,
)
from search_harness.evolution.research.roles.runner import RoleRunner

from .domain import EffectResult
from .evaluation import CandidateArtifact, LocalEvaluationBackend


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
        rollout_file = work_dir / "candidate_replays.jsonl"
        rollout_summary = await asyncio.to_thread(
            self.backend.rollout_candidate_examples,
            candidate=candidate,
            examples=tuple(case.example for case in cases),
            experience_file=self.experience_file,
            output_file=rollout_file,
            rollouts_per_example=CONFORMANCE_REPLICATES,
        )
        records = _read_jsonl(rollout_file)
        indexed_records = _index_rollout_records(records)
        semaphore = asyncio.Semaphore(self.judge_workers)

        async def review_record(
            case: ConformanceCase,
            replicate_id: str,
            record: dict[str, Any],
            finding_index: int,
        ) -> tuple[ConformanceFinding, Path, int]:
            runner_error = record.get("runner_error")
            if isinstance(runner_error, dict):
                finding = runtime_error_finding(
                    case=case,
                    replicate_id=replicate_id,
                    error=(
                        f"{runner_error.get('type', 'RunnerError')}: "
                        f"{runner_error.get('message', '')}"
                    ),
                )
                artifact = {
                    "runtime": "deterministic_runner_error",
                    "output": finding.model_dump(mode="json"),
                    "usage": {"total_tokens": 0},
                }
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
                            "replicate_id": replicate_id,
                            "candidate_trajectory": (
                                _conformance_trajectory(record)
                            ),
                        },
                        resource_config=TeacherResourceConfig(),
                    )
                finding = ConformanceFinding.model_validate(
                    artifact.get("output")
                )
                expected_run_ref = (
                    f"{case.example.example_id}/{replicate_id}"
                )
                if finding.candidate_run_ref != expected_run_ref:
                    raise ValueError(
                        "Conformance Reviewer returned the wrong "
                        f"candidate_run_ref: "
                        f"{finding.candidate_run_ref} != "
                        f"{expected_run_ref}"
                    )
                if finding.trial_refs != list(case.trial_refs):
                    raise ValueError(
                        "Conformance Reviewer changed its assigned trial_refs"
                    )
                allowed_phases = {
                    rule.phase for rule in mechanism.phase_rules
                }
                unexpected_phases = (
                    set(finding.observed_phases) - allowed_phases
                )
                if unexpected_phases:
                    relevant_phases = [
                        phase
                        for phase in finding.observed_phases
                        if phase in allowed_phases
                    ]
                    finding_payload = finding.model_dump(mode="json")
                    finding_payload["observed_phases"] = relevant_phases
                    if (
                        finding.verdict == "faithful"
                        and not relevant_phases
                    ):
                        finding_payload.update(
                            {
                                "verdict": "inconclusive",
                                "assessment": (
                                    "The review named only phases outside "
                                    "the supplied MechanismSpec, so it did "
                                    "not establish implementation fidelity."
                                ),
                                "repair_obligation": (
                                    "Make the mechanism's declared phase "
                                    "activation observable in the complete "
                                    "Candidate rollout."
                                ),
                            }
                        )
                    finding = ConformanceFinding.model_validate(
                        finding_payload
                    )
            path = _write_json(
                work_dir
                / "findings"
                / f"finding_{finding_index:03d}.json",
                artifact,
            )
            usage = artifact.get("usage")
            tokens = (
                usage.get("total_tokens", 0)
                if isinstance(usage, dict)
                else 0
            )
            return finding, path, _non_negative_int(tokens)

        jobs = []
        finding_index = 0
        for case in cases:
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
                jobs.append(
                    review_record(
                        case,
                        replicate_id,
                        record,
                        finding_index,
                    )
                )
        reviewed = await asyncio.gather(*jobs)
        findings = [item[0] for item in reviewed]
        finding_paths = [item[1] for item in reviewed]
        summary = aggregate_conformance(
            cases=cases,
            findings=findings,
            finding_refs=[str(path) for path in finding_paths],
        )
        summary_path = _write_json(
            work_dir / "summary.json",
            {**summary.to_dict(), "rollout": rollout_summary},
        )
        refs = {
            "conformance_rollout_file": str(rollout_file.resolve()),
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
                "total_tokens": (
                    sum(item[2] for item in reviewed)
                    + _rollout_total_tokens(records)
                )
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
        "example_count": len(per_example),
        "passed_example_count": passed,
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


def _conformance_trajectory(record: dict[str, Any]) -> dict[str, Any]:
    example = record.get("example")
    example = example if isinstance(example, dict) else {}
    return {
        "example": {
            "example_id": example.get("example_id"),
            "question": example.get("question"),
        },
        "replicate": record.get("replicate"),
        "harness": record.get("harness"),
        "run": record.get("run"),
        "runner_error": record.get("runner_error"),
    }


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
