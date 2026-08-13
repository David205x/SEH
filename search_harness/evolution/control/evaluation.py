"""Rollout and evaluation effects required by the v2 controller."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.datasets import DatasetExample
from search_harness.evaluation import (
    HotpotQAEvaluator,
    TeacherBinaryJudge,
    build_teacher_judge_model,
    evaluate_rollout_file,
    write_evaluation_report,
)
from search_harness.evaluation.rollouts import (
    open_harness_source,
    run_examples,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)
from search_harness.runners.run_agent_once import run_agent_once
from search_harness.evolution.versioning import TemplateVersionStore

from ..experience import file_digest, load_experience_set


@dataclass(frozen=True)
class EvaluationArtifact:
    """Persisted rollout and evaluation references."""

    rollout_file: Path
    report_dir: Path
    metrics: dict[str, Any]


@dataclass(frozen=True)
class CandidateArtifact:
    """Pending candidate data needed by controller-side evaluation."""

    candidate_attempt_id: str
    parent_version: str
    candidate_digest: str
    compiler_log: Path
    summary: str
    validation_passed: bool
    validation: dict[str, Any] | None = None
    clarification: str | None = None


@dataclass(frozen=True)
class LocalEvaluationConfig:
    """Student rollout and judge settings used by controller effects."""

    env_file: Path = Path(".env")
    student_model_role: str = "student"
    student_max_steps: int = 20
    rollout_workers: int = 2
    rollouts_per_example: int = 1
    judge_workers: int = 8
    teacher_judge: bool = True
    show_progress: bool = True
    candidate_error_streak_limit: int = 3

    def __post_init__(self) -> None:
        positive = {
            "student_max_steps": self.student_max_steps,
            "rollout_workers": self.rollout_workers,
            "rollouts_per_example": self.rollouts_per_example,
            "judge_workers": self.judge_workers,
            "candidate_error_streak_limit": self.candidate_error_streak_limit,
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")


class LocalEvaluationBackend:
    """Execute only the rollout and evaluation operations used by v2."""

    def __init__(
        self,
        *,
        store: TemplateVersionStore,
        config: LocalEvaluationConfig,
    ) -> None:
        self.store = store
        self.config = config

    def evaluate_accepted(
        self,
        *,
        version_id: str,
        experience_file: Path,
        output_dir: Path,
    ) -> EvaluationArtifact:
        return self._rollout_and_evaluate(
            experience_file=experience_file,
            output_dir=output_dir,
            version_id=version_id,
            candidate_attempt_id=None,
            max_consecutive_identical_errors=None,
        )

    def evaluate_candidate(
        self,
        *,
        candidate: CandidateArtifact,
        experience_file: Path,
        output_dir: Path,
    ) -> EvaluationArtifact:
        return self._rollout_and_evaluate(
            experience_file=experience_file,
            output_dir=output_dir,
            version_id=None,
            candidate_attempt_id=candidate.candidate_attempt_id,
            max_consecutive_identical_errors=(
                self.config.candidate_error_streak_limit
            ),
        )

    def rollout_candidate_examples(
        self,
        *,
        candidate: CandidateArtifact,
        examples: tuple[DatasetExample, ...],
        experience_file: Path,
        output_file: Path,
        rollouts_per_example: int,
    ) -> dict[str, Any]:
        """Run a pending candidate on a fixed conformance example subset."""

        if not examples:
            raise ValueError("candidate conformance examples must not be empty")
        with open_harness_source(
            version_store=self.store.root,
            candidate_attempt_id=candidate.candidate_attempt_id,
            env_file=self.config.env_file,
        ) as (template_root, source):
            model = OpenAICompatibleConfig.from_env(
                env_file=self.config.env_file,
                prefix=self.config.student_model_role.upper(),
            )
            provenance = {
                "schema_version": 1,
                "dataset": {
                    "path": str(experience_file.resolve()),
                    "digest": file_digest(experience_file),
                    "selection": {
                        "kind": "mechanism_conformance",
                        "example_ids": [example.example_id for example in examples],
                    },
                },
                "model": {
                    "role": self.config.student_model_role,
                    **model.provenance(),
                },
                "harness": source.to_dict(),
                "execution": {
                    "rollout_workers": self.config.rollout_workers,
                    "rollouts_per_example": rollouts_per_example,
                    "seed_strategy": "base_plus_replicate_index",
                },
            }
            summary = run_examples(
                examples=examples,
                run_agent=lambda seed, question: run_agent_once(
                    question,
                    env_file=self.config.env_file,
                    model_role=self.config.student_model_role,
                    template_root=template_root,
                    max_steps=self.config.student_max_steps,
                    seed=seed,
                ),
                output_file=output_file,
                limit=len(examples),
                fail_fast=False,
                show_progress=self.config.show_progress,
                harness_source=source.to_dict(),
                experiment_provenance=provenance,
                max_workers=self.config.rollout_workers,
                rollouts_per_example=rollouts_per_example,
                base_seed=model.seed,
                max_consecutive_identical_errors=rollouts_per_example,
            )
        return {
            "output_file": str(summary.output_file.resolve()),
            "requested_examples": summary.requested,
            "requested_rollouts": summary.requested_rollouts,
            "processed_rollouts": summary.processed,
            "runner_errors": summary.runner_errors,
            "stopped_early": summary.stopped_early,
            "stop_reason": summary.stop_reason,
        }

    def _rollout_and_evaluate(
        self,
        *,
        experience_file: Path,
        output_dir: Path,
        version_id: str | None,
        candidate_attempt_id: str | None,
        max_consecutive_identical_errors: int | None,
    ) -> EvaluationArtifact:
        examples = load_experience_set(experience_file)
        rollout_file = (
            output_dir.parent
            / f"{output_dir.name.removesuffix('_report')}_rollouts.jsonl"
        )
        with open_harness_source(
            version_store=self.store.root,
            harness_version=version_id,
            candidate_attempt_id=candidate_attempt_id,
            env_file=self.config.env_file,
        ) as (template_root, source):
            model = OpenAICompatibleConfig.from_env(
                env_file=self.config.env_file,
                prefix=self.config.student_model_role.upper(),
            )
            provenance = {
                "schema_version": 1,
                "dataset": {
                    "path": str(experience_file.resolve()),
                    "digest": file_digest(experience_file),
                    "selection": {"limit": len(examples), "order": "fixed"},
                },
                "model": {
                    "role": self.config.student_model_role,
                    **model.provenance(),
                },
                "harness": source.to_dict(),
                "execution": {
                    "rollout_workers": self.config.rollout_workers,
                    "rollouts_per_example": self.config.rollouts_per_example,
                    "seed_strategy": "base_plus_replicate_index",
                    "max_consecutive_identical_errors": (
                        max_consecutive_identical_errors
                    ),
                },
            }
            run_examples(
                examples=examples,
                run_agent=lambda seed, question: run_agent_once(
                    question,
                    env_file=self.config.env_file,
                    model_role=self.config.student_model_role,
                    template_root=template_root,
                    max_steps=self.config.student_max_steps,
                    seed=seed,
                ),
                output_file=rollout_file,
                limit=len(examples),
                fail_fast=False,
                show_progress=self.config.show_progress,
                harness_source=source.to_dict(),
                experiment_provenance=provenance,
                max_workers=self.config.rollout_workers,
                rollouts_per_example=self.config.rollouts_per_example,
                base_seed=model.seed,
                max_consecutive_identical_errors=(
                    max_consecutive_identical_errors
                ),
            )
        evaluator = HotpotQAEvaluator()
        judge_factory = None
        if self.config.teacher_judge:
            judge_factory = lambda: TeacherBinaryJudge(
                build_teacher_judge_model(env_file=self.config.env_file),
                evaluator,
            )
        report = evaluate_rollout_file(
            rollout_file,
            evaluator,
            teacher_judge_factory=judge_factory,
            judge_workers=self.config.judge_workers,
            show_progress=self.config.show_progress,
        )
        write_evaluation_report(report, output_dir)
        return EvaluationArtifact(
            rollout_file=rollout_file,
            report_dir=output_dir,
            metrics=dict(report["metrics"]),
        )
