"""Standalone Researcher, Worker and Reviewer revision cycle."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    EvidenceReview,
    InterventionHypothesis,
    InterventionWorkerResult,
    TrialReview,
)
from .intervention_runtime import InterventionRoleRuntime
from .native_runtime import NativeChatTeacherRuntime
from .resources import TeacherResourceConfig
from .role_resources import InterventionResourceConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "intervention_worker"
    / "plugins"
)
REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "evidence_reviewer"
    / "plugins"
)
TRIAL_REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "trial_reviewer"
    / "plugins"
)


class InterventionAssignment(BaseModel):
    """Controller-selected trial assignment for one frozen hypothesis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    trial_objective: str = Field(min_length=1)
    example_id: str = Field(min_length=1)
    replicate_id: str = Field(min_length=1)
    prefix_id: int = Field(ge=1)
    prohibited_content: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ResearchRevisionOutcome:
    """Paths and semantic route produced by one standalone cycle."""

    status: str
    worker_artifact: Path
    reviewer_artifact: Path | None
    researcher_revision_artifact: Path | None
    result: dict[str, Any]
    worker_artifacts: tuple[Path, ...] = ()
    reviewer_artifacts: tuple[Path, ...] = ()
    trial_reviewer_artifacts: tuple[Path, ...] = ()


class ResearchRevisionCycle:
    """Run one assigned intervention and route feedback deterministically."""

    def __init__(
        self,
        *,
        researcher_runtime: NativeChatTeacherRuntime,
        worker_runtime: InterventionRoleRuntime,
        reviewer_runtime: NativeChatTeacherRuntime,
    ) -> None:
        self.researcher_runtime = researcher_runtime
        self.worker_runtime = worker_runtime
        self.reviewer_runtime = reviewer_runtime

    async def run(
        self,
        *,
        researcher_artifact: dict[str, Any],
        assignment: InterventionAssignment,
        intervention_config: InterventionResourceConfig,
        run_dir: Path,
    ) -> ResearchRevisionOutcome:
        """执行一个 assignment；多证据流程使用 ``run_many``。"""

        return await self.run_many(
            researcher_artifact=researcher_artifact,
            assignments=[assignment],
            intervention_config=intervention_config,
            run_dir=run_dir,
        )

    async def run_many(
        self,
        *,
        researcher_artifact: dict[str, Any],
        assignments: list[InterventionAssignment],
        intervention_config: InterventionResourceConfig,
        run_dir: Path,
    ) -> ResearchRevisionOutcome:
        """在冻结假设上执行 Worker、逐 trial 审阅和一次全局审阅。"""

        if not assignments:
            raise ValueError("Research revision cycle requires assignments")

        hypothesis = InterventionHypothesis.model_validate(
            researcher_artifact.get("output")
        )
        root = run_dir.resolve()
        worker_paths: list[Path] = []
        reviewer_paths: list[Path] = []
        trial_reviewer_paths: list[Path] = []
        executed_workers: list[dict[str, Any]] = []
        executed_paths: list[Path] = []
        worker_results: list[dict[str, Any]] = []
        trial_reviews: list[TrialReview] = []

        for index, assignment in enumerate(assignments, start=1):
            trial_ref = f"trial_{index:03d}"
            worker_path = root / "trials" / trial_ref / "worker.json"
            worker_artifact = await self.worker_runtime.run(
                template_root=WORKER_TEMPLATE,
                role_input={
                    "hypothesis": hypothesis.model_dump(mode="json"),
                    **assignment.model_dump(mode="json"),
                },
                resource_config=TeacherResourceConfig(
                    intervention=intervention_config
                ),
            )
            _write_artifact(worker_path, worker_artifact)
            worker_paths.append(worker_path)
            worker_result = InterventionWorkerResult.model_validate(
                worker_artifact.get("output")
            )
            worker_results.append(worker_result.model_dump(mode="json"))

            if worker_result.result_kind == "unsupported_hypothesis":
                revision_path = root / "researcher" / "revision_002.json"
                feedback = worker_result.model_dump(mode="json")
                revision = await self.researcher_runtime.continue_researcher(
                    previous_artifact=researcher_artifact,
                    feedback_source="intervention_worker",
                    feedback=feedback,
                    trial_files=[
                        *executed_paths,
                        *(
                            [worker_path]
                            if _has_intervention_trial(worker_artifact)
                            else []
                        ),
                    ],
                )
                _write_artifact(revision_path, revision)
                return self._finish(
                    root=root,
                    status="hypothesis_revised_after_worker",
                    worker_paths=worker_paths,
                    reviewer_paths=reviewer_paths,
                    trial_reviewer_paths=trial_reviewer_paths,
                    revision_path=revision_path,
                    result={
                        "workers": worker_results,
                        "trial_reviews": [
                            review.model_dump(mode="json")
                            for review in trial_reviews
                        ],
                        "review": None,
                        "researcher": revision["output"],
                    },
                )

            if worker_result.result_kind == "unsuitable_assignment":
                if index < len(assignments):
                    continue
                return self._finish(
                    root=root,
                    status="assignment_retry_required",
                    worker_paths=worker_paths,
                    reviewer_paths=reviewer_paths,
                    trial_reviewer_paths=trial_reviewer_paths,
                    revision_path=None,
                    result={
                        "workers": worker_results,
                        "trial_reviews": [
                            review.model_dump(mode="json")
                            for review in trial_reviews
                        ],
                        "review": None,
                    },
                )

            executed_workers.append(worker_artifact)
            executed_paths.append(worker_path)
            trial_reviewer_artifact = await self.reviewer_runtime.run(
                template_root=TRIAL_REVIEWER_TEMPLATE,
                role_input={
                    "hypothesis": hypothesis.model_dump(mode="json"),
                    "trial_ref": trial_ref,
                },
                resource_config=TeacherResourceConfig(
                    trial_files=[worker_path]
                ),
            )
            trial_reviewer_path = (
                root / "trial_reviews" / f"{trial_ref}.json"
            )
            _write_artifact(
                trial_reviewer_path,
                trial_reviewer_artifact,
            )
            trial_reviewer_paths.append(trial_reviewer_path)
            trial_reviews.append(
                TrialReview.model_validate(
                    trial_reviewer_artifact.get("output")
                )
            )

        if not executed_workers:
            return self._finish(
                root=root,
                status="assignment_retry_required",
                worker_paths=worker_paths,
                reviewer_paths=reviewer_paths,
                trial_reviewer_paths=trial_reviewer_paths,
                revision_path=None,
                result={
                    "workers": worker_results,
                    "trial_reviews": [],
                    "review": None,
                },
            )

        aggregate = aggregate_trial_observations(
            executed_workers,
            executed_paths,
        )
        reviewer_artifact = await self.reviewer_runtime.run(
            template_root=REVIEWER_TEMPLATE,
            role_input={
                "hypothesis": hypothesis.model_dump(mode="json"),
                "aggregate_observations": aggregate,
                "trial_reviews": [
                    review.model_dump(mode="json")
                    for review in trial_reviews
                ],
                "prior_obligation": None,
            },
            resource_config=TeacherResourceConfig(),
        )
        reviewer_path = root / "reviewer" / "review_001.json"
        _write_artifact(reviewer_path, reviewer_artifact)
        reviewer_paths.append(reviewer_path)
        latest_review = EvidenceReview.model_validate(
            reviewer_artifact.get("output")
        )
        review_payload = latest_review.model_dump(mode="json")

        revision_path: Path | None = None
        revision: dict[str, Any] | None = None
        if latest_review.decision in {"revise", "reject"}:
            status = "hypothesis_revised_after_review"
            revision_path = root / "researcher" / "revision_002.json"
            revision = await self.researcher_runtime.continue_researcher(
                previous_artifact=researcher_artifact,
                feedback_source="evidence_reviewer",
                feedback=review_payload,
                trial_files=executed_paths,
            )
            _write_artifact(revision_path, revision)
        elif latest_review.decision == "ready_to_distill":
            status = "ready_to_distill"
        else:
            status = "more_evidence_required"
        return self._finish(
            root=root,
            status=status,
            worker_paths=worker_paths,
            reviewer_paths=reviewer_paths,
            trial_reviewer_paths=trial_reviewer_paths,
            revision_path=revision_path,
            result={
                "workers": worker_results,
                "trial_reviews": [
                    review.model_dump(mode="json")
                    for review in trial_reviews
                ],
                "review": review_payload,
                **(
                    {"researcher": revision["output"]}
                    if revision is not None
                    else {}
                ),
            },
        )

    @staticmethod
    def _finish(
        *,
        root: Path,
        status: str,
        worker_paths: list[Path],
        reviewer_paths: list[Path],
        trial_reviewer_paths: list[Path],
        revision_path: Path | None,
        result: dict[str, Any],
    ) -> ResearchRevisionOutcome:
        worker_path = worker_paths[-1]
        reviewer_path = reviewer_paths[-1] if reviewer_paths else None
        summary = {
            "schema_version": 1,
            "status": status,
            "worker_artifact": str(worker_path),
            "worker_artifacts": [str(path) for path in worker_paths],
            "reviewer_artifact": (
                str(reviewer_path) if reviewer_path is not None else None
            ),
            "reviewer_artifacts": [
                str(path) for path in reviewer_paths
            ],
            "trial_reviewer_artifacts": [
                str(path) for path in trial_reviewer_paths
            ],
            "researcher_revision_artifact": (
                str(revision_path) if revision_path is not None else None
            ),
            "result": result,
        }
        _write_artifact(root / "cycle.json", summary)
        return ResearchRevisionOutcome(
            status=status,
            worker_artifact=worker_path,
            reviewer_artifact=reviewer_path,
            researcher_revision_artifact=revision_path,
            result=result,
            worker_artifacts=tuple(worker_paths),
            reviewer_artifacts=tuple(reviewer_paths),
            trial_reviewer_artifacts=tuple(trial_reviewer_paths),
        )


def aggregate_trial_observations(
    worker_artifacts: list[dict[str, Any]],
    worker_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Summarize persisted Worker branch evidence for Reviewer input."""

    items = [_trial_observation(artifact) for artifact in worker_artifacts]
    if worker_paths is not None:
        if len(worker_paths) != len(items):
            raise ValueError(
                "worker artifact and path counts must match"
            )
        for item, path in zip(items, worker_paths):
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


_aggregate_observations = aggregate_trial_observations


def _trial_observation(worker_artifact: dict[str, Any]) -> dict[str, Any]:
    resources = worker_artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    trial = resources.get("intervention_trial")
    trial = trial if isinstance(trial, dict) else {}
    comparison = trial.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}
    source = comparison.get("source")
    source = source if isinstance(source, dict) else {}
    branch = comparison.get("branch")
    branch = branch if isinstance(branch, dict) else {}
    output = worker_artifact.get("output")
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
            and change["action"].get("kind")
            != "continue_without_change"
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


def _has_intervention_trial(artifact: dict[str, Any]) -> bool:
    resources = artifact.get("resource_artifacts")
    return (
        isinstance(resources, dict)
        and isinstance(resources.get("intervention_trial"), dict)
    )


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a standalone Researcher revision cycle.",
    )
    parser.add_argument("--researcher-artifact", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--rollout-file", type=Path, required=True)
    parser.add_argument("--actor-plugins-root", type=Path, required=True)
    parser.add_argument(
        "--assignments-file",
        type=Path,
        help="UTF-8 JSON array of InterventionAssignment objects.",
    )
    parser.add_argument("--example-id")
    parser.add_argument("--replicate-id")
    parser.add_argument("--prefix-id", type=int)
    parser.add_argument("--trial-objective")
    parser.add_argument("--prohibited-content", action="append", default=[])
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--actor-max-steps", type=int, default=8)
    parser.add_argument("--researcher-max-turns", type=int, default=15)
    parser.add_argument("--worker-max-turns", type=int, default=10)
    parser.add_argument("--reviewer-max-turns", type=int, default=10)
    args = parser.parse_args(argv)
    if args.assignments_file is None and any(
        value is None
        for value in (
            args.example_id,
            args.replicate_id,
            args.prefix_id,
            args.trial_objective,
        )
    ):
        parser.error(
            "provide --assignments-file or all single-assignment arguments"
        )
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    researcher_artifact = json.loads(
        args.researcher_artifact.read_text(encoding="utf-8-sig")
    )
    if not isinstance(researcher_artifact, dict):
        raise TypeError("Researcher artifact must contain a JSON object")
    cycle = ResearchRevisionCycle(
        researcher_runtime=NativeChatTeacherRuntime(
            env_file=args.env_file,
            max_turns=args.researcher_max_turns,
        ),
        worker_runtime=InterventionRoleRuntime(
            env_file=args.env_file,
            max_steps_per_activation=args.worker_max_turns,
        ),
        reviewer_runtime=NativeChatTeacherRuntime(
            env_file=args.env_file,
            max_turns=args.reviewer_max_turns,
        ),
    )
    assignments = _load_assignments(args)
    outcome = asyncio.run(
        cycle.run_many(
            researcher_artifact=researcher_artifact,
            assignments=assignments,
            intervention_config=InterventionResourceConfig(
                rollout_file=args.rollout_file,
                actor_plugins_root=args.actor_plugins_root,
                env_file=args.env_file,
                actor_max_steps=args.actor_max_steps,
            ),
            run_dir=args.run_dir,
        )
    )
    print(f"Research revision cycle completed: {outcome.status}")
    print(f"Cycle written to: {(args.run_dir / 'cycle.json').resolve()}")


def _load_assignments(args: argparse.Namespace) -> list[InterventionAssignment]:
    if args.assignments_file is None:
        return [
            InterventionAssignment(
                trial_objective=args.trial_objective,
                example_id=args.example_id,
                replicate_id=args.replicate_id,
                prefix_id=args.prefix_id,
                prohibited_content=args.prohibited_content,
            )
        ]
    payload = json.loads(
        args.assignments_file.read_text(encoding="utf-8-sig")
    )
    if not isinstance(payload, list):
        raise TypeError("assignments file must contain a JSON array")
    return [
        InterventionAssignment.model_validate(item)
        for item in payload
    ]


if __name__ == "__main__":
    main()
