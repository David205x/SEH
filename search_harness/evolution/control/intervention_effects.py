"""Intervention trial selection and branch execution effects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    InterventionWorkerResult,
)

from .domain import EffectResult


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
        prior_obligation: object,
        work_dir: Path,
    ) -> EffectResult:
        """Select the next unused rollout prefix matching the fork phase."""

        used = set(used_assignments)
        candidate_refs = dict.fromkeys(
            [
                *failure.evidence_refs,
                *list_rollout_references(rollout_file),
            ]
        )
        for evidence_ref in candidate_refs:
            example_id, replicate_id = evidence_ref.split("/", maxsplit=1)
            record = load_rollout_record(
                rollout_file,
                example_id,
                replicate_id,
            )
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
                used.add(assignment_key)
                assignment_count += 1
                selection = {
                    "status": "selected",
                    "assignment": {
                        "trial_objective": _trial_objective(
                            hypothesis,
                            prior_obligation,
                        ),
                        "example_id": example_id,
                        "replicate_id": replicate_id,
                        "prefix_id": prefix_id,
                        "prohibited_content": [],
                    },
                    "assignment_count": assignment_count,
                    "used_assignments": sorted(used),
                }
                path = _write_json(
                    work_dir / "selection.json",
                    selection,
                )
                return EffectResult(
                    outcome=selection,
                    artifact_refs={"selection_artifact": str(path)},
                )
        exhausted = {
            "status": "exhausted",
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
