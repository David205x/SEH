"""Local model, rollout, evaluation, and Version Store effects."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from search_harness.adapter.intervention.prefix import (
    build_prefix_timeline,
    list_rollout_references,
    load_rollout_record,
)
from search_harness.evolution.backend import (
    LocalEvolutionBackend,
    LocalEvolutionBackendConfig,
)
from search_harness.evolution.types import CandidateArtifact
from search_harness.teacher.contracts import (
    CandidateReview,
    CompilerResult,
    EvidenceReview,
    FailureDirection,
    InterventionHypothesis,
    InterventionWorkerResult,
    MechanismDistillation,
    MechanismSpec,
    TrialReview,
)
from search_harness.teacher.native_runtime import NativeChatTeacherRuntime
from search_harness.teacher.intervention_runtime import (
    InterventionRoleRuntime,
)
from search_harness.teacher.research_cycle import (
    aggregate_trial_observations,
)
from search_harness.teacher.resources import TeacherResourceConfig
from search_harness.teacher.role_resources import (
    CandidateReviewResourceConfig,
    CompilerResourceConfig,
    InterventionResourceConfig,
)
from search_harness.versioning import (
    FileEdit,
    HarnessVersionStore,
    IterationSummary,
    ValidationReport,
)

from .domain import ControlState, EffectResult, WorkItem, WorkKind


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEACHER_TEMPLATE_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


@dataclass(frozen=True)
class LocalControlEffectsConfig:
    """Runtime configuration for the formal Controller's concrete effects."""

    experience_file: Path
    env_file: Path = Path(".env")
    actor_max_steps: int = 20
    teacher_max_turns: int = 20
    rollout_workers: int = 2
    rollouts_per_example: int = 1
    judge_workers: int = 8
    teacher_judge: bool = True
    show_progress: bool = True

    def __post_init__(self) -> None:
        positive = {
            "actor_max_steps": self.actor_max_steps,
            "teacher_max_turns": self.teacher_max_turns,
            "rollout_workers": self.rollout_workers,
            "rollouts_per_example": self.rollouts_per_example,
            "judge_workers": self.judge_workers,
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")


class LocalControlEffects:
    """Connect the eight v2 roles to rollouts and transactional versioning."""

    def __init__(
        self,
        *,
        store: HarnessVersionStore,
        config: LocalControlEffectsConfig,
    ) -> None:
        self.store = store
        self.config = config
        self.runtime = NativeChatTeacherRuntime(
            env_file=config.env_file,
            max_turns=config.teacher_max_turns,
        )
        self.intervention_runtime = InterventionRoleRuntime(
            env_file=config.env_file,
            max_steps_per_activation=config.teacher_max_turns,
            teacher_judge=config.teacher_judge,
        )
        self.backend = LocalEvolutionBackend(
            store=store,
            config=LocalEvolutionBackendConfig(
                env_file=config.env_file,
                actor_max_steps=config.actor_max_steps,
                rollout_workers=config.rollout_workers,
                rollouts_per_example=config.rollouts_per_example,
                judge_workers=config.judge_workers,
                teacher_judge=config.teacher_judge,
                show_progress=config.show_progress,
            ),
        )

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        """Dispatch exactly one bounded work kind."""

        work_dir.mkdir(parents=True, exist_ok=True)
        handler = getattr(self, f"_execute_{work.kind.value}")
        return await handler(work=work, state=state, work_dir=work_dir)

    async def _execute_evaluate_incumbent(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        version_id = _required_payload_string(work, "version_id")
        self._require_latest(version_id)
        evaluation = self.backend.evaluate_accepted(
            version_id=version_id,
            experience_file=self.config.experience_file,
            output_dir=work_dir / "report",
        )
        return _evaluation_result(evaluation)

    async def _execute_analyze_failure(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.runtime.run(
            template_root=_template("failure_analyst"),
            role_input={
                "analysis_focus": work.payload.get("analysis_focus"),
            },
            resource_config=TeacherResourceConfig(
                report_dir=_ref_path(work, "report_dir"),
                rollout_file=_ref_path(work, "rollout_file"),
                actor_plugins_root=self.store.plugins_dir,
            ),
        )
        output = FailureDirection.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"failure_artifact": str(path)},
        )

    async def _execute_research_hypothesis(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        continuation = work.payload.get("research_continuation")
        if continuation is None:
            failure = _role_output(
                _read_json(_ref_path(work, "failure_artifact"))
            )
            artifact = await self.runtime.run(
                template_root=_template("hypothesis_researcher"),
                role_input={"problem_direction": failure},
                resource_config=TeacherResourceConfig(
                    report_dir=_ref_path(work, "report_dir"),
                    rollout_file=_ref_path(work, "rollout_file"),
                    actor_plugins_root=self.store.plugins_dir,
                ),
            )
        else:
            if not isinstance(continuation, dict):
                raise TypeError("research_continuation must be an object")
            artifact = await self.runtime.continue_researcher(
                previous_artifact=_read_json(
                    _ref_path(work, "hypothesis_artifact")
                ),
                feedback_source=_required_string(
                    continuation,
                    "feedback_source",
                ),
                feedback=_required_object(continuation, "feedback"),
                trial_files=_trial_paths(work, required=False),
            )
        output = InterventionHypothesis.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"hypothesis_artifact": str(path)},
        )

    async def _execute_select_trial(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        failure = FailureDirection.model_validate(
            _role_output(_read_json(_ref_path(work, "failure_artifact")))
        )
        hypothesis = InterventionHypothesis.model_validate(
            _role_output(_read_json(_ref_path(work, "hypothesis_artifact")))
        )
        used = {
            str(item)
            for item in work.payload.get("used_assignments", [])
        }
        assignment_count = int(work.payload.get("assignment_count", 0))
        rollout_file = _ref_path(work, "rollout_file")
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
                assignment = {
                    "trial_objective": _trial_objective(
                        hypothesis,
                        work.payload.get("prior_obligation"),
                    ),
                    "example_id": example_id,
                    "replicate_id": replicate_id,
                    "prefix_id": prefix_id,
                    "prohibited_content": [],
                }
                selection = {
                    "status": "selected",
                    "assignment": assignment,
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

    async def _execute_execute_trial(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        assignment = _required_payload_object(work, "assignment")
        hypothesis = _role_output(
            _read_json(_ref_path(work, "hypothesis_artifact"))
        )
        artifact = await self.intervention_runtime.run(
            template_root=_template("intervention_worker"),
            role_input={
                "hypothesis": hypothesis,
                **assignment,
            },
            resource_config=TeacherResourceConfig(
                intervention=InterventionResourceConfig(
                    rollout_file=_ref_path(work, "rollout_file"),
                    actor_plugins_root=self.store.plugins_dir,
                    env_file=self.config.env_file,
                    actor_max_steps=self.config.actor_max_steps,
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
            {
                "worker_artifact": str(path),
            },
        )

    async def _execute_review_evidence(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        trial_paths = _trial_paths(work)
        trial_artifacts = [_read_json(path) for path in trial_paths]
        aggregate = aggregate_trial_observations(
            trial_artifacts,
            trial_paths,
        )
        hypothesis = _role_output(
            _read_json(_ref_path(work, "hypothesis_artifact"))
        )
        trial_reviews: list[TrialReview] = []
        trial_review_refs: dict[str, str] = {}
        for index, trial_path in enumerate(trial_paths, start=1):
            trial_ref = trial_path.parent.name
            review_key = f"trial_review_{index:03d}_artifact"
            if review_key in work.input_refs:
                trial_review_path = _ref_path(work, review_key)
                trial_review_artifact = _read_json(trial_review_path)
                stored_input = trial_review_artifact.get("input")
                if (
                    not isinstance(stored_input, dict)
                    or stored_input.get("hypothesis") != hypothesis
                    or stored_input.get("trial_ref") != trial_ref
                ):
                    raise ValueError(
                        "persisted Trial Reviewer artifact does not match "
                        f"the frozen hypothesis and trial: {review_key}"
                    )
            else:
                trial_review_artifact = await self.runtime.run(
                    template_root=_template("trial_reviewer"),
                    role_input={
                        "hypothesis": hypothesis,
                        "trial_ref": trial_ref,
                    },
                    resource_config=TeacherResourceConfig(
                        trial_files=[trial_path]
                    ),
                )
                trial_review_path = _write_json(
                    work_dir
                    / "trial_reviews"
                    / f"trial_review_{index:03d}.json",
                    trial_review_artifact,
                )
            trial_review = TrialReview.model_validate(
                trial_review_artifact.get("output")
            )
            trial_reviews.append(trial_review)
            if trial_review.trial_ref != trial_ref:
                raise ValueError(
                    "Trial Reviewer output reference differs from its "
                    f"assigned trial: {trial_review.trial_ref} != {trial_ref}"
                )
            trial_review_refs[review_key] = str(trial_review_path)

        artifact = await self.runtime.run(
            template_root=_template("evidence_reviewer"),
            role_input={
                "hypothesis": hypothesis,
                "aggregate_observations": aggregate,
                "trial_reviews": [
                    review.model_dump(mode="json")
                    for review in trial_reviews
                ],
                "prior_obligation": work.payload.get(
                    "prior_obligation"
                ),
            },
            resource_config=TeacherResourceConfig(),
        )
        output = EvidenceReview.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {
                "reviewer_artifact": str(path),
                **trial_review_refs,
            },
        )

    async def _execute_distill_mechanism(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.runtime.run(
            template_root=_template("mechanism_distiller"),
            role_input={
                "hypothesis": _role_output(
                    _read_json(_ref_path(work, "hypothesis_artifact"))
                ),
                "review": _role_output(
                    _read_json(_ref_path(work, "reviewer_artifact"))
                ),
                "evidence_refs": [
                    path.parent.name for path in _trial_paths(work)
                ],
                "capability_constraints": list(
                    work.payload.get("capability_constraints", [])
                ),
            },
            resource_config=TeacherResourceConfig(
                trial_files=_trial_paths(work)
            ),
        )
        output = MechanismDistillation.model_validate(artifact.get("output"))
        role_path = _write_json(work_dir / "role.json", artifact)
        refs = {"distiller_artifact": str(role_path)}
        if output.decision == "distilled":
            mechanisms = artifact.get("validated_mechanisms")
            if not isinstance(mechanisms, dict):
                raise TypeError(
                    "distilled artifact lacks validated_mechanisms"
                )
            mechanism = MechanismSpec.model_validate(
                mechanisms.get(output.mechanism_ref)
            )
            mechanism_path = _write_json(
                work_dir / "mechanism.json",
                mechanism.model_dump(mode="json"),
            )
            refs["mechanism_file"] = str(mechanism_path)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            refs,
        )

    async def _execute_compile_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        mechanism = MechanismSpec.model_validate(
            _read_json(_ref_path(work, "mechanism_file"))
        )
        artifact = await self.runtime.run(
            template_root=_template("compiler"),
            role_input={
                "mechanism": mechanism.model_dump(mode="json"),
                "implementation_constraints": list(
                    work.payload.get("implementation_constraints", [])
                ),
                "validation_feedback": list(
                    work.payload.get("validation_feedback", [])
                ),
            },
            resource_config=TeacherResourceConfig(
                compiler=CompilerResourceConfig(
                    parent_plugins_root=self.store.plugins_dir,
                    env_file=self.config.env_file,
                )
            ),
        )
        output = CompilerResult.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"compiler_artifact": str(path)},
        )

    async def _execute_stage_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        compiler = _read_json(_ref_path(work, "compiler_artifact"))
        candidate = _compiler_candidate(compiler)
        candidate_digest = _required_string(
            candidate,
            "candidate_digest",
        )
        parent_version = _required_current_version(state)
        existing = self._find_candidate_iteration(
            parent_version=parent_version,
            candidate_digest=candidate_digest,
        )
        if existing is not None and existing.status == "rejected":
            validation = self._iteration_validation(
                existing.iteration_id
            )
            return EffectResult(
                outcome={
                    "status": "validation_failed",
                    "iteration_id": existing.iteration_id,
                    "candidate_digest": candidate_digest,
                    "validation": validation,
                },
                artifact_refs={},
            )
        if existing is None:
            session = self.store.start_iteration(
                parent_version=parent_version,
                metadata={
                    "controller_candidate_digest": candidate_digest,
                },
            )
            changed_files = _required_object(
                candidate,
                "changed_files",
            )
            edits = [
                FileEdit(
                    operation=(
                        "delete" if content is None else "write"
                    ),
                    path=path,
                    content=content,
                )
                for path, content in changed_files.items()
            ]
            if not edits:
                session.reject("Compiler submitted an empty transaction.")
                validation = {
                    "passed": False,
                    "errors": ["Compiler submitted an empty transaction."],
                }
                return EffectResult(
                    outcome={
                        "status": "validation_failed",
                        "iteration_id": session.iteration_id,
                        "candidate_digest": candidate_digest,
                        "validation": validation,
                    },
                    artifact_refs={},
                )
            session.apply_patch(edits)
        else:
            session = self.store.resume_iteration(existing.iteration_id)

        if session.digest != candidate_digest:
            raise ValueError(
                "Version Store candidate digest does not match Compiler "
                f"artifact: {session.digest} != {candidate_digest}"
            )
        validation_report = session.validate(
            env_file=self.config.env_file
        )
        validation = _validation_dict(validation_report)
        validation_path = _write_json(
            work_dir / "validation.json",
            validation,
        )
        refs = {
            "validation_artifact": str(validation_path),
        }
        if not validation_report.passed:
            session.reject(
                "Controller validation failed: "
                + "; ".join(validation_report.errors)
            )
            return EffectResult(
                outcome={
                    "status": "validation_failed",
                    "iteration_id": session.iteration_id,
                    "candidate_digest": session.digest,
                    "validation": validation,
                },
                artifact_refs=refs,
            )
        return EffectResult(
            outcome={
                "status": "valid",
                "iteration_id": session.iteration_id,
                "candidate_digest": session.digest,
                "validation": validation,
            },
            artifact_refs=refs,
        )

    async def _execute_evaluate_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        candidate = self._candidate_artifact(work, state)
        evaluation = self.backend.evaluate_candidate(
            candidate=candidate,
            experience_file=self.config.experience_file,
            output_dir=work_dir / "report",
        )
        return _evaluation_result(
            evaluation,
            prefix="candidate_",
        )

    async def _execute_review_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        mechanism = MechanismSpec.model_validate(
            _read_json(_ref_path(work, "mechanism_file"))
        )
        compiler = _read_json(_ref_path(work, "compiler_artifact"))
        compiler_output = CompilerResult.model_validate(
            compiler.get("output")
        )
        validation_summary = {
            "compiler_validation": _required_payload_object(
                work,
                "validation_summary",
            ),
            "incumbent_metrics": _required_payload_object(
                work,
                "incumbent_metrics",
            ),
            "candidate_metrics": _required_payload_object(
                work,
                "candidate_metrics",
            ),
        }
        session = self.store.resume_iteration(
            _required_payload_string(work, "iteration_id")
        )
        with session.stage() as candidate_plugins_root:
            artifact = await self.runtime.run(
                template_root=_template("candidate_reviewer"),
                role_input={
                    "mechanism": mechanism.model_dump(mode="json"),
                    "validation_summary": validation_summary,
                    "implementation_summary": (
                        compiler_output.implementation_summary
                    ),
                    "unresolved_risk": compiler_output.unresolved_risk,
                    "historical_experience": [],
                },
                resource_config=TeacherResourceConfig(
                    candidate_review=CandidateReviewResourceConfig(
                        incumbent_report_dir=_ref_path(
                            work,
                            "report_dir",
                        ),
                        candidate_report_dir=_ref_path(
                            work,
                            "candidate_report_dir",
                        ),
                        incumbent_rollout_file=_ref_path(
                            work,
                            "rollout_file",
                        ),
                        candidate_rollout_file=_ref_path(
                            work,
                            "candidate_rollout_file",
                        ),
                        incumbent_plugins_root=self.store.plugins_dir,
                        candidate_plugins_root=candidate_plugins_root,
                    )
                ),
            )
        output = CandidateReview.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"candidate_reviewer_artifact": str(path)},
        )

    async def _execute_promote_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        iteration_id = _required_payload_string(work, "iteration_id")
        accepted = next(
            (
                version
                for version in self.store.list_versions()
                if version.iteration_id == iteration_id
            ),
            None,
        )
        if accepted is None:
            session = self.store.resume_iteration(iteration_id)
            review = _required_payload_object(work, "candidate_review")
            compiler = _read_json(_ref_path(work, "compiler_artifact"))
            compiler_output = CompilerResult.model_validate(
                compiler.get("output")
            )
            accepted = session.accept(
                summary=compiler_output.implementation_summary,
                evaluation={
                    "metrics": _required_payload_object(
                        work,
                        "candidate_metrics",
                    ),
                    "candidate_review": review,
                    "promotion_gate": _required_payload_object(
                        work,
                        "promotion_gate",
                    ),
                },
                env_file=self.config.env_file,
            )
        receipt = {
            "version_id": accepted.version_id,
            "iteration_id": iteration_id,
            "candidate_digest": accepted.digest,
        }
        path = _write_json(work_dir / "promotion.json", receipt)
        return EffectResult(
            outcome=receipt,
            artifact_refs={"promotion_artifact": str(path)},
        )

    async def _execute_reject_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        iteration_id = _required_payload_string(work, "iteration_id")
        summary = next(
            (
                item
                for item in self.store.list_iterations()
                if item.iteration_id == iteration_id
            ),
            None,
        )
        if summary is None:
            raise KeyError(f"unknown candidate iteration: {iteration_id}")
        if summary.status == "pending":
            review = _required_payload_object(work, "candidate_review")
            gate = _required_payload_object(work, "promotion_gate")
            reasons = gate.get("reasons")
            reason = (
                "; ".join(str(value) for value in reasons)
                if isinstance(reasons, list) and reasons
                else _required_string(review, "reason")
            )
            self.store.resume_iteration(iteration_id).reject(
                reason,
                evaluation={
                    "metrics": _required_payload_object(
                        work,
                        "candidate_metrics",
                    ),
                    "candidate_review": review,
                    "promotion_gate": gate,
                },
            )
        elif summary.status == "accepted":
            raise RuntimeError(
                f"cannot reject accepted iteration: {iteration_id}"
            )
        receipt = {
            "status": "rejected",
            "iteration_id": iteration_id,
        }
        path = _write_json(work_dir / "rejection.json", receipt)
        return EffectResult(
            outcome=receipt,
            artifact_refs={"rejection_artifact": str(path)},
        )

    def _candidate_artifact(
        self,
        work: WorkItem,
        state: ControlState,
    ) -> CandidateArtifact:
        compiler = _read_json(_ref_path(work, "compiler_artifact"))
        output = CompilerResult.model_validate(compiler.get("output"))
        return CandidateArtifact(
            iteration_id=_required_payload_string(work, "iteration_id"),
            parent_version=_required_current_version(state),
            candidate_digest=_required_payload_string(
                work,
                "candidate_digest",
            ),
            compiler_log=_ref_path(work, "compiler_artifact"),
            summary=output.implementation_summary,
            validation_passed=True,
            validation=_required_payload_object(
                work,
                "validation_summary",
            ),
            clarification=None,
        )

    def _require_latest(self, version_id: str) -> None:
        versions = self.store.list_versions()
        if not versions or versions[-1].version_id != version_id:
            raise ValueError(
                f"Controller version is not latest accepted: {version_id}"
            )

    def _find_candidate_iteration(
        self,
        *,
        parent_version: str,
        candidate_digest: str,
    ) -> IterationSummary | None:
        matches: list[IterationSummary] = []
        for summary in self.store.list_iterations():
            events = self.store.get_iteration_events(
                summary.iteration_id
            )
            first = events[0]
            metadata = first.payload.get("metadata")
            if (
                first.payload.get("parent_version") == parent_version
                and isinstance(metadata, dict)
                and metadata.get("controller_candidate_digest")
                == candidate_digest
            ):
                matches.append(summary)
        if not matches:
            return None
        pending = [item for item in matches if item.status == "pending"]
        return pending[-1] if pending else matches[-1]

    def _iteration_validation(
        self,
        iteration_id: str,
    ) -> dict[str, Any]:
        for event in reversed(
            self.store.get_iteration_events(iteration_id)
        ):
            if event.event_type == "validation_completed":
                return dict(event.payload)
        return {
            "passed": False,
            "errors": ["Candidate iteration was rejected before validation."],
        }


def _template(role_id: str) -> Path:
    return TEACHER_TEMPLATE_ROOT / role_id / "plugins"


def _evaluation_result(
    evaluation: Any,
    *,
    prefix: str = "",
) -> EffectResult:
    metrics = dict(evaluation.metrics)
    tokens = metrics.get("tokens")
    total_tokens = (
        tokens.get("total_tokens", 0)
        if isinstance(tokens, dict)
        else 0
    )
    return EffectResult(
        outcome={"metrics": metrics},
        artifact_refs={
            f"{prefix}rollout_file": str(
                evaluation.rollout_file.resolve()
            ),
            f"{prefix}report_dir": str(
                evaluation.report_dir.resolve()
            ),
        },
        usage={"total_tokens": _non_negative_int(total_tokens)},
    )


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


def _trial_paths(
    work: WorkItem,
    *,
    required: bool = True,
) -> list[Path]:
    paths = [
        Path(value).resolve()
        for key, value in sorted(work.input_refs.items())
        if (
            key.startswith("trial_")
            and key.removeprefix("trial_").isdigit()
        )
    ]
    if required and not paths:
        raise ValueError("work requires at least one persisted trial")
    return paths


def _trial_objective(
    hypothesis: InterventionHypothesis,
    obligation: object,
) -> str:
    parts = [
        hypothesis.evaluation.primary_signal,
        hypothesis.evaluation.success_condition,
        hypothesis.evaluation.falsifier,
    ]
    if isinstance(obligation, str) and obligation.strip():
        parts.append(obligation)
    return " | ".join(parts)


def _compiler_candidate(artifact: dict[str, Any]) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    if not isinstance(resources, dict):
        raise TypeError("Compiler artifact lacks resource_artifacts")
    candidate = resources.get("compiler_candidate")
    if not isinstance(candidate, dict):
        raise TypeError(
            "submitted Compiler artifact lacks compiler_candidate"
        )
    validation = candidate.get("validation")
    if not isinstance(validation, dict) or not validation.get("passed"):
        raise ValueError(
            "Compiler submitted a candidate without passing its local "
            "validation"
        )
    return dict(candidate)


def _validation_dict(report: ValidationReport) -> dict[str, Any]:
    value = asdict(report)
    for key in (
        "added_paths",
        "modified_paths",
        "removed_paths",
        "errors",
    ):
        value[key] = list(value[key])
    return value


def _ref_path(work: WorkItem, name: str) -> Path:
    try:
        value = work.input_refs[name]
    except KeyError as exc:
        raise ValueError(
            f"{work.kind.value} work lacks input ref '{name}'"
        ) from exc
    return Path(value).resolve()


def _required_payload_string(work: WorkItem, name: str) -> str:
    return _required_string(work.payload, name)


def _required_payload_object(
    work: WorkItem,
    name: str,
) -> dict[str, Any]:
    return _required_object(work.payload, name)


def _required_current_version(state: ControlState) -> str:
    if state.current_version is None:
        raise RuntimeError("Controller state lacks current_version")
    return state.current_version


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def _required_object(
    value: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _role_output(artifact: dict[str, Any]) -> dict[str, Any]:
    return _required_object(artifact, "output")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


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
