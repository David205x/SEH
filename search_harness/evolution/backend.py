"""基于现有 Actor、Critic、Compiler 的本地 Evolution backend。"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from search_harness.adapter.compiler import CompilerContext
from search_harness.adapter.compiler.runtime import (
    apply_compiler_result,
    build_compiler_loop,
    parse_compiler_result,
)
from search_harness.adapter.critic import CriticContext, parse_critic_result, CriticResult
from search_harness.adapter.critic.evidence import (
    validate_accepted_rollouts,
    validate_iteration_rollouts,
    validate_paired_rollouts,
)
from search_harness.adapter.critic.runtime import build_critic_loop
from search_harness.adapter.intervention import (
    DEFAULT_COORDINATOR_TASK,
    InterventionCoordinatorConfig,
    InterventionCoordinatorResult,
    InterventionCoordinatorRunner,
    InterventionRuntimeConfig,
)
from search_harness.evaluation import (
    HotpotQAEvaluator,
    TeacherBinaryJudge,
    evaluate_rollout_file,
    write_evaluation_report,
)
from search_harness.models import OpenAICompatibleConfig, OpenAICompatibleTextModel
from search_harness.paths import (
    COMPILER_TEMPLATE_ROOT,
    CRITIC_TEMPLATE_ROOT,
    INTERVENTION_COORDINATOR_TEMPLATE_ROOT,
)
from search_harness.runners.run_actor_once import build_loop
from search_harness.runners.run_dataset import open_harness_source, run_examples
from search_harness.versioning import HarnessVersionStore, IterationSession, content_digest

from .experience import file_digest, load_experience_set
from .types import (
    CandidateArtifact,
    CriticArtifact,
    EvaluationArtifact,
    InterventionArtifact, EvolutionBackend,
)


FAILURE_TASK = (
    "Analyze the current accepted Harness on the fixed Experience Set. Identify "
    "generalized repeated failures and return prioritized behavioral problem directions. "
    "Do not prescribe implementation mechanisms. Account for "
    "the supplied failed-attempt memory and do not repeat a rejected strategy unless "
    "new evidence justifies it."
)
REVIEW_TASK = (
    "Review the pending candidate against its accepted parent. Inspect the actual "
    "Harness change, aggregate score transitions, representative gains and regressions, "
    "execution errors and cost. Return review.decision=accept only when the evidence "
    "supports adopting the candidate; otherwise reject with a concrete reason."
)


@dataclass(frozen=True)
class LocalEvolutionBackendConfig:
    """真实 Evolution backend 的模型与插件配置。"""

    env_file: Path = Path(".env")
    critic_plugins_root: Path = CRITIC_TEMPLATE_ROOT
    compiler_plugins_root: Path = COMPILER_TEMPLATE_ROOT
    intervention_coordinator_plugins_root: Path = INTERVENTION_COORDINATOR_TEMPLATE_ROOT
    actor_model_role: str = "student"
    adapter_model_role: str = "teacher"
    actor_max_steps: int = 20
    critic_max_steps: int = 20
    critic_protocol_repair_limit: int = 2
    compiler_max_steps: int = 35
    compiler_validation_repair_limit: int = 4
    compiler_smoke_examples: int = 1
    intervention_max_steps: int = 40
    intervention_max_trials: int = 10
    rollout_workers: int = 2
    rollouts_per_example: int = 1
    judge_workers: int = 8
    teacher_judge: bool = True
    show_progress: bool = True

    def __post_init__(self) -> None:
        if self.rollout_workers < 1:
            raise ValueError("rollout_workers must be positive")
        if self.rollouts_per_example < 1:
            raise ValueError("rollouts_per_example must be positive")
        if self.judge_workers < 1:
            raise ValueError("judge_workers must be positive")
        if self.compiler_validation_repair_limit < 0:
            raise ValueError("compiler_validation_repair_limit must not be negative")
        if self.critic_protocol_repair_limit < 0:
            raise ValueError("critic_protocol_repair_limit must not be negative")
        if self.compiler_smoke_examples < 1:
            raise ValueError("compiler_smoke_examples must be positive")


class LocalEvolutionBackend(EvolutionBackend):
    """复用项目现有运行时完成 Evolution Runner 的外部操作。"""

    def __init__(
        self, *, store: HarnessVersionStore, config: LocalEvolutionBackendConfig
    ) -> None:
        self.store = store
        self.config = config

    def evaluate_accepted(
        self, *, version_id: str, experience_file: Path, output_dir: Path
    ) -> EvaluationArtifact:
        return self._rollout_and_evaluate(
            experience_file=experience_file,
            output_dir=output_dir,
            version_id=version_id,
            iteration_id=None,
        )

    def analyze_failures(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        failed_attempts: tuple[dict[str, Any], ...],
        output_file: Path,
    ) -> CriticArtifact:
        snapshot = self.store.resolve(version_id)
        context = CriticContext.load(
            report_dir=evaluation.report_dir,
            rollout_file=evaluation.rollout_file,
            harness_files=snapshot.files,
            harness_version=version_id,
        )
        validate_accepted_rollouts(
            context.rollout_records,
            store_root=self.store.root,
            checkpoint_store_id=self.store.checkpoint_store_id,
            version_id=version_id,
            digest=snapshot.digest,
            evidence_name="primary",
        )
        memory = json.dumps(failed_attempts, ensure_ascii=False)
        task = f"{FAILURE_TASK}\n\nGeneralized failed-attempt memory: {memory}"
        return self._run_critic(
            context=context,
            task=task,
            output_file=output_file,
            iteration=None,
        )

    def validate_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        output_dir: Path,
    ) -> InterventionArtifact:
        """Validate the highest-priority Critic direction through Coordinator trials."""

        return self._coordinate_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            output_dir=output_dir,
            previous_intervention=None,
            compiler_feedback=None,
        )

    def refine_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        previous_intervention: InterventionArtifact,
        compiler_feedback: str,
        output_dir: Path,
    ) -> InterventionArtifact:
        """Run additional Coordinator trials targeted at Compiler feedback."""

        return self._coordinate_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            output_dir=output_dir,
            previous_intervention=previous_intervention,
            compiler_feedback=compiler_feedback,
        )

    def continue_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        previous_intervention: InterventionArtifact,
        output_dir: Path,
    ) -> InterventionArtifact:
        """Continue an inconclusive direction with a fresh Worker-trial budget."""

        previous = previous_intervention.result
        task = (
            "Continue validating the same Critic problem direction. Inherit the prior "
            "trial ledger and do not repeat failed case-specific schemes. Treat the prior "
            "recommendation as the next experiment to execute, not merely as text to "
            "restate. Use this fresh trial budget to test a generic mechanism unchanged "
            "across distinct relevant examples and resolve the missing cross-case "
            "evidence. Return supported only when the accumulated ledger is directly "
            "compilable; otherwise report the strongest remaining limitation.\n\n"
            f"Prior analysis:\n{previous.analysis}\n\n"
            f"Prior recommendation:\n{previous.recommendation}"
        )
        return self._coordinate_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            output_dir=output_dir,
            previous_intervention=previous_intervention,
            compiler_feedback=None,
            task=task,
        )

    def _coordinate_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        output_dir: Path,
        previous_intervention: InterventionArtifact | None,
        compiler_feedback: str | None,
        task: str | None = None,
    ) -> InterventionArtifact:
        """Execute one initial or Compiler-requested Coordinator pass."""

        if not critic.result.problem_directions:
            raise ValueError("Critic has no problem direction to validate")
        parent = self.store.resolve(version_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        with self.store.stage(parent) as plugins_root:
            worker_config = InterventionRuntimeConfig(
                env_file=self.config.env_file,
                plugins_root=plugins_root,
                output_root=output_dir / "trials",
                student_model_role=self.config.actor_model_role,
                teacher_model_role=self.config.adapter_model_role,
                actor_max_steps=self.config.actor_max_steps,
                teacher_judge=self.config.teacher_judge,
            )
            coordinator = InterventionCoordinatorRunner(
                InterventionCoordinatorConfig(
                    env_file=self.config.env_file,
                    plugins_root=self.config.intervention_coordinator_plugins_root,
                    output_root=output_dir / "coordinator",
                    model_role=self.config.adapter_model_role,
                    max_steps=self.config.intervention_max_steps,
                    max_trials=self.config.intervention_max_trials,
                    worker=worker_config,
                )
            )
            artifact = coordinator.run(
                report_dir=evaluation.report_dir,
                critic_log=critic.log_file,
                direction_index=0,
                previous_intervention_log=(
                    previous_intervention.log_file
                    if previous_intervention is not None
                    else None
                ),
                compiler_feedback=compiler_feedback,
                task=task or (
                    "Address the Compiler clarification below by testing the missing "
                    "generic implementation behavior with additional Worker trials. "
                    "Return supported only when the revised recommendation is directly "
                    "compilable and every clarification item is answered by evidence.\n\n"
                    f"Compiler clarification:\n{compiler_feedback}"
                    if compiler_feedback is not None
                    else DEFAULT_COORDINATOR_TASK
                ),
            )
        return InterventionArtifact(
            log_file=Path(artifact["artifact_file"]),
            result=InterventionCoordinatorResult.from_dict(
                artifact["coordinator_result"]
            ),
        )

    def compile_candidate(
        self,
        *,
        parent_version: str,
        intervention: InterventionArtifact,
        output_file: Path,
        experience_file: Path | None = None,
    ) -> CandidateArtifact:
        parent = self.store.resolve(parent_version)
        context = CompilerContext.from_intervention_log(
            intervention_log=intervention.log_file,
            parent=parent,
        )
        common_inputs = {
            "intervention_log": str(intervention.log_file.resolve()),
            "critic_log": str(context.critic_log.resolve()),
            "direction_index": context.direction_index,
            "checkpoint_store": str(self.store.root),
            "checkpoint_store_id": self.store.checkpoint_store_id,
            "parent_version": parent_version,
            "compiler_plugins_root": str(self.config.compiler_plugins_root.resolve()),
            "model_role": self.config.adapter_model_role,
        }
        attempts: list[dict[str, Any]] = []
        repair_feedback: dict[str, Any] | None = None
        max_attempts = self.config.compiler_validation_repair_limit + 1
        for attempt_number in range(1, max_attempts + 1):
            session = self.store.start_iteration(
                parent_version=parent_version,
                metadata={
                    "role": "evolution_compiler",
                    "intervention_log": str(intervention.log_file.resolve()),
                    "critic_log": str(context.critic_log.resolve()),
                    "direction_index": context.direction_index,
                    "validation_attempt": attempt_number,
                },
            )
            inputs = {
                **common_inputs,
                "iteration_id": session.iteration_id,
                "validation_attempt": attempt_number,
            }
            loop = build_compiler_loop(
                compiler_context=context,
                plugins_root=self.config.compiler_plugins_root,
                env_file=self.config.env_file,
                model_role=self.config.adapter_model_role,
                max_steps=self.config.compiler_max_steps,
            )
            try:
                run = loop.run(_compiler_task(repair_feedback))
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                session.reject(f"Compiler execution failed: {error}")
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "inputs": inputs,
                        "compiler_result": None,
                        "validation": None,
                        "result_error": error,
                        "run": None,
                    }
                )
                self._write_log(
                    output_file,
                    {
                        **_adapter_log(inputs, None, None, error),
                        "compiler_result": None,
                        "critic_result": None,
                        "validation": None,
                        "attempts": attempts,
                    },
                )
                raise
            if run.answer is None:
                error = (
                    f"Compiler did not complete: {run.status.value}: {run.error}"
                )
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "inputs": inputs,
                        "compiler_result": None,
                        "validation": None,
                        "result_error": error,
                        "run": run.to_dict(),
                    }
                )
                session.reject(
                    error,
                    evaluation={"result_error": error},
                )
                self._write_log(
                    output_file,
                    {
                        **_adapter_log(inputs, None, run.to_dict(), error),
                        "compiler_result": None,
                        "critic_result": None,
                        "validation": None,
                        "attempts": attempts,
                    },
                )
                if attempt_number == max_attempts:
                    raise RuntimeError(error)
                repair_feedback = {"protocol_error": error}
                continue
            try:
                result = parse_compiler_result(run.answer)
            except (TypeError, ValueError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                attempt = {
                    "attempt": attempt_number,
                    "inputs": inputs,
                    "compiler_result": None,
                    "validation": None,
                    "result_error": error,
                    "raw_answer": run.answer,
                    "run": run.to_dict(),
                }
                attempts.append(attempt)
                session.reject(
                    "Compiler result failed protocol validation",
                    evaluation={"result_error": error},
                )
                self._write_log(
                    output_file,
                    {
                        **_adapter_log(inputs, None, run.to_dict(), error),
                        "compiler_result": None,
                        "critic_result": None,
                        "validation": None,
                        "attempts": attempts,
                    },
                )
                if attempt_number == max_attempts:
                    raise RuntimeError(
                        "Compiler result protocol repair exhausted: " f"{error}"
                    ) from exc
                repair_feedback = {
                    "protocol_error": error,
                }
                continue
            try:
                validation = apply_compiler_result(
                    session, result, env_file=self.config.env_file
                )
                validation_payload = (
                    asdict(validation) if validation is not None else None
                )
            except (RuntimeError, TypeError, ValueError) as exc:
                validation = None
                validation_payload = {
                    "passed": False,
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
            smoke = None
            if (
                validation is not None
                and validation.passed
                and experience_file is not None
            ):
                smoke = self._smoke_validate_candidate(
                    session=session,
                    experience_file=experience_file,
                )
                assert validation_payload is not None
                validation_payload["smoke"] = smoke
                if not smoke["passed"]:
                    validation_payload["passed"] = False
                    validation_payload["errors"] = [
                        *validation_payload.get("errors", []),
                        *smoke["errors"],
                    ]
            attempt = {
                "attempt": attempt_number,
                "inputs": inputs,
                "compiler_result": result.to_dict(),
                "validation": validation_payload,
                "smoke": smoke,
                "run": run.to_dict(),
            }
            attempts.append(attempt)
            passed = bool(validation_payload and validation_payload.get("passed"))
            if result.clarification is not None or passed or attempt_number == max_attempts:
                self._write_log(
                    output_file,
                    {
                        **_adapter_log(
                            inputs, result.to_dict(), run.to_dict(), None
                        ),
                        "compiler_result": result.to_dict(),
                        "critic_result": None,
                        "validation": validation_payload,
                        "attempts": attempts,
                    },
                )
                return CandidateArtifact(
                    iteration_id=session.iteration_id,
                    parent_version=parent_version,
                    candidate_digest=session.digest,
                    compiler_log=output_file,
                    summary=result.summary,
                    validation_passed=passed,
                    validation=validation_payload,
                    clarification=result.clarification,
                )

            assert validation_payload is not None
            session.reject(
                "Compiler patch failed deterministic validation",
                evaluation={"validation": validation_payload},
            )
            repair_feedback = {
                "previous_result": result.to_dict(),
                "validation": validation_payload,
            }

        raise AssertionError("compiler validation loop exhausted without a result")

    def _smoke_validate_candidate(
        self,
        *,
        session: IterationSession,
        experience_file: Path,
    ) -> dict[str, Any]:
        """Run a reproducibly sampled real Actor case against one pending candidate."""

        examples = load_experience_set(experience_file)
        model_config = OpenAICompatibleConfig.from_env(
            env_file=self.config.env_file,
            prefix=self.config.actor_model_role.upper(),
        )
        base_seed = model_config.seed if model_config.seed is not None else 0
        selection_seed = base_seed + int(session.digest[:8], 16)
        count = min(self.config.compiler_smoke_examples, len(examples))
        selected = random.Random(selection_seed).sample(list(examples), count)
        records: list[dict[str, Any]] = []
        errors: list[str] = []
        with session.stage() as plugins_root:
            for index, example in enumerate(selected):
                try:
                    loop = build_loop(
                        env_file=self.config.env_file,
                        model_role=self.config.actor_model_role,
                        plugins_root=plugins_root,
                        max_steps=self.config.actor_max_steps,
                        seed=base_seed + index,
                    )
                    run = loop.run(example.question)
                    record = {
                        "example_id": example.example_id,
                        "status": run.status.value,
                        "error": run.error,
                        "run": run.to_dict(),
                    }
                    if run.status.value != "completed":
                        errors.append(
                            f"smoke example {example.example_id} did not complete: "
                            f"{run.status.value}: {run.error}"
                        )
                except Exception as exc:
                    record = {
                        "example_id": example.example_id,
                        "status": "runner_error",
                        "error": f"{type(exc).__name__}: {exc}",
                        "run": None,
                    }
                    errors.append(
                        f"smoke example {example.example_id} runner error: "
                        f"{type(exc).__name__}: {exc}"
                    )
                records.append(record)
        return {
            "passed": not errors,
            "selection_seed": selection_seed,
            "requested_examples": self.config.compiler_smoke_examples,
            "records": records,
            "errors": errors,
        }

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
            iteration_id=candidate.iteration_id,
        )

    def review_candidate(
        self,
        *,
        candidate: CandidateArtifact,
        candidate_evaluation: EvaluationArtifact,
        parent_evaluation: EvaluationArtifact,
        output_file: Path,
    ) -> CriticArtifact:
        session = self.store.resume_iteration(candidate.iteration_id)
        with session.stage() as plugins_root:
            candidate_files = {
                path.relative_to(plugins_root).as_posix(): path.read_bytes()
                for path in sorted(plugins_root.rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts
            }
        normalized_files = {
            PurePosixPath(path): content for path, content in candidate_files.items()
        }
        context = CriticContext.load(
            report_dir=candidate_evaluation.report_dir,
            rollout_file=candidate_evaluation.rollout_file,
            harness_files=normalized_files,
            harness_version=f"pending:{candidate.iteration_id}",
        )
        validate_iteration_rollouts(
            context,
            iteration_id=candidate.iteration_id,
            candidate_digest=candidate.candidate_digest,
        )
        parent = self.store.resolve(candidate.parent_version)
        context = context.bind_comparison(
            report_dir=parent_evaluation.report_dir,
            rollout_file=parent_evaluation.rollout_file,
            harness_files=parent.files,
            harness_version=candidate.parent_version,
        )
        assert context.comparison is not None
        validate_accepted_rollouts(
            context.comparison.rollout_records,
            store_root=self.store.root,
            checkpoint_store_id=self.store.checkpoint_store_id,
            version_id=parent.version_id,
            digest=parent.digest,
            evidence_name="comparison",
        )
        validate_paired_rollouts(context)
        return self._run_critic(
            context=context,
            task=REVIEW_TASK,
            output_file=output_file,
            iteration={
                "iteration_id": candidate.iteration_id,
                "parent_version": candidate.parent_version,
                "candidate_digest": candidate.candidate_digest,
            },
        )

    def _rollout_and_evaluate(
        self,
        *,
        experience_file: Path,
        output_dir: Path,
        version_id: str | None,
        iteration_id: str | None,
    ) -> EvaluationArtifact:
        examples = load_experience_set(experience_file)
        rollout_file = output_dir.parent / f"{output_dir.name.removesuffix('_report')}_rollouts.jsonl"
        with open_harness_source(
            checkpoint_store=self.store.root,
            harness_version=version_id,
            iteration_id=iteration_id,
            env_file=self.config.env_file,
        ) as (plugins_root, source):
            model = OpenAICompatibleConfig.from_env(
                env_file=self.config.env_file,
                prefix=self.config.actor_model_role.upper(),
            )
            provenance = {
                "schema_version": 1,
                "dataset": {
                    "path": str(experience_file.resolve()),
                    "digest": file_digest(experience_file),
                    "selection": {"limit": len(examples), "order": "fixed"},
                },
                "model": {"role": self.config.actor_model_role, **model.provenance()},
                "harness": source.to_dict(),
                "execution": {
                    "rollout_workers": self.config.rollout_workers,
                    "rollouts_per_example": self.config.rollouts_per_example,
                    "seed_strategy": "base_plus_replicate_index",
                },
            }
            run_examples(
                examples=examples,
                loop_factory=lambda seed: build_loop(
                    env_file=self.config.env_file,
                    model_role=self.config.actor_model_role,
                    plugins_root=plugins_root,
                    max_steps=self.config.actor_max_steps,
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
            )
        evaluator = HotpotQAEvaluator()
        judge_factory = None
        if self.config.teacher_judge:
            judge_factory = lambda: TeacherBinaryJudge(
                OpenAICompatibleTextModel.from_env(
                    self.config.env_file, prefix="TEACHER"
                ),
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

    def _run_critic(
        self,
        *,
        context: CriticContext,
        task: str,
        output_file: Path,
        iteration: dict[str, Any] | None,
    ) -> CriticArtifact:
        inputs = {
            "report_dir": str(context.report_dir),
            "rollout_file": str(context.rollout_file),
            "actor_source": str(self.store.root),
            "checkpoint_store_id": self.store.checkpoint_store_id,
            "harness_version": context.harness_version,
            "harness_digest": content_digest(context.harness_files),
            "iteration": iteration,
            "critic_plugins_root": str(self.config.critic_plugins_root.resolve()),
            "model_role": self.config.adapter_model_role,
            "data_split": context.data_split,
            "comparison": (
                {
                    "report_dir": str(context.comparison.report_dir),
                    "rollout_file": str(context.comparison.rollout_file),
                    "harness_version": context.comparison.harness_version,
                    "harness_digest": content_digest(context.comparison.harness_files),
                }
                if context.comparison is not None
                else None
            ),
        }
        attempts: list[dict[str, Any]] = []
        current_task = task
        max_attempts = self.config.critic_protocol_repair_limit + 1
        for attempt_number in range(1, max_attempts + 1):
            loop = build_critic_loop(
                critic_context=context,
                plugins_root=self.config.critic_plugins_root,
                env_file=self.config.env_file,
                model_role=self.config.adapter_model_role,
                max_steps=self.config.critic_max_steps,
            )
            run = loop.run(current_task)
            error: str | None = None
            result: CriticResult | None = None
            if run.answer is None:
                error = f"Critic did not complete: {run.status.value}: {run.error}"
            else:
                try:
                    result = parse_critic_result(run.answer)
                except (TypeError, ValueError) as exc:
                    error = f"{type(exc).__name__}: {exc}"
            attempts.append(
                {
                    "attempt": attempt_number,
                    "result_error": error,
                    "raw_answer": run.answer,
                    "run": run.to_dict(),
                }
            )
            if result is not None:
                payload = _adapter_log(
                    inputs, result.to_dict(), run.to_dict(), None
                )
                payload["critic_result"] = result.to_dict()
                payload["attempts"] = attempts
                self._write_log(output_file, payload)
                return CriticArtifact(log_file=output_file, result=result)

            assert error is not None
            payload = _adapter_log(inputs, None, run.to_dict(), error)
            payload["attempts"] = attempts
            self._write_log(output_file, payload)
            if attempt_number == max_attempts:
                raise RuntimeError(
                    f"Critic result protocol repair exhausted: {error}"
                )
            current_task = (
                f"{task}\n\n"
                "The previous Critic session failed its required result schema. "
                "Reproduce the complete analysis from the bound evidence and return every "
                "required field explicitly. Do not invent defaults for missing evidence.\n\n"
                f"Protocol error:\n{error}"
            )

        raise AssertionError("critic protocol repair loop exhausted without a result")

    @staticmethod
    def _write_log(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _adapter_log(
    inputs: dict[str, Any],
    result: dict[str, Any] | None,
    run: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": inputs,
        "critic_result": result,
        "result_error": error,
        "run": run,
    }


def _compiler_task(repair_feedback: dict[str, Any] | None) -> str:
    task = (
        "Compile the Coordinator-supported intervention strategy into one smallest "
        "coherent atomic Harness plugin transaction."
    )
    if repair_feedback is None:
        return task
    if "protocol_error" in repair_feedback:
        return (
            f"{task}\n\n"
            "The previous Compiler session completed with an invalid result payload. "
            "Return a complete replacement transaction against the original parent. "
            "Follow the exact final-answer JSON shape from the system prompt; do not use "
            "Markdown fences or surrounding prose, and correctly JSON-escape all source "
            "file content.\n\n"
            f"Protocol error:\n{repair_feedback['protocol_error']}\n\n"
            "Reconstruct the patch from the bound Coordinator evidence and Harness files."
        )
    return (
        f"{task}\n\n"
        "The previous Compiler transaction failed framework validation or a real Actor "
        "smoke rollout. "
        "Use the report below as authoritative API feedback. Return a complete replacement "
        "transaction against the original parent Harness, not an incremental patch against "
        "the rejected candidate. Preserve the validated intervention semantics and repair "
        "only the implementation defects.\n\n"
        f"Previous attempt and validation report:\n"
        f"{json.dumps(repair_feedback, ensure_ascii=False)}"
    )
