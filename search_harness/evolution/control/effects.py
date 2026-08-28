"""Local model, rollout, evaluation, and Version Store effects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.evolution.research.roles.contracts import (
    CompilerResult,
    FailureDirection,
    InterventionHypothesis,
    MechanismSpec,
)
from search_harness.evolution.research.experience_summary import (
    ExperienceSummaryRequest,
    build_conformance_capability_request,
    build_hook_feasibility_capability_request,
    build_promotion_direction_request,
    build_workflow_direction_request,
)
from search_harness.evolution.research.hook_feasibility import (
    HookFeasibilityProbeConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)
from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
)
from search_harness.evolution.research.resources.stores import (
    CandidateReviewResourceConfig,
)
from search_harness.evolution.versioning import (
    TemplateVersionStore,
)

from .evaluation import (
    CandidateArtifact,
    LocalEvaluationBackend,
    LocalEvaluationConfig,
)
from .candidate_version_effects import CandidateVersionEffects
from .conformance_effects import (
    ConformanceEffects,
    summarize_conformance_review,
)
from .evaluation_effects import EvaluationEffects
from .evidence_review_effects import EvidenceReviewEffects
from .intervention_effects import InterventionEffects
from .hook_feasibility_effects import HookFeasibilityEffects
from .research_role_effects import ResearchRoleEffects
from .domain import ControlState, EffectResult, WorkItem, WorkKind


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEACHER_TEMPLATE_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


@dataclass(frozen=True)
class LocalControlEffectsConfig:
    """Runtime configuration for the formal Controller's concrete effects."""

    experience_file: Path
    env_file: Path = Path(".env")
    student_max_steps: int = 20
    teacher_max_turns: int = 20
    rollout_workers: int = 2
    rollouts_per_example: int = 1
    judge_workers: int = 8
    teacher_judge: bool = True
    show_progress: bool = True
    candidate_error_streak_limit: int = 3
    intervention_extended_tools: bool = False
    hook_feasibility_enabled: bool = False
    hook_feasibility_max_cases: int = 6
    hook_feasibility_repetitions: int = 2
    hook_feasibility_thinking_modes: tuple[str, ...] | list[str] = (
        "enabled",
        "disabled",
    )

    def __post_init__(self) -> None:
        if not isinstance(self.hook_feasibility_enabled, bool):
            raise TypeError("hook_feasibility_enabled must be a boolean")
        if not isinstance(self.intervention_extended_tools, bool):
            raise TypeError("intervention_extended_tools must be a boolean")
        positive = {
            "student_max_steps": self.student_max_steps,
            "teacher_max_turns": self.teacher_max_turns,
            "rollout_workers": self.rollout_workers,
            "rollouts_per_example": self.rollouts_per_example,
            "judge_workers": self.judge_workers,
            "candidate_error_streak_limit": (
                self.candidate_error_streak_limit
            ),
            "hook_feasibility_max_cases": (
                self.hook_feasibility_max_cases
            ),
            "hook_feasibility_repetitions": (
                self.hook_feasibility_repetitions
            ),
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")
        HookFeasibilityProbeConfig(
            max_cases_per_phase=self.hook_feasibility_max_cases,
            repetitions=self.hook_feasibility_repetitions,
            thinking_modes=tuple(self.hook_feasibility_thinking_modes),
        )


class LocalControlEffects:
    """Connect formal evolution roles to rollouts and external effects."""

    def __init__(
        self,
        *,
        store: TemplateVersionStore,
        config: LocalControlEffectsConfig,
    ) -> None:
        self.store = store
        self.config = config
        self.role_runner = NativeChatRoleRunner(
            env_file=config.env_file,
            max_turns=config.teacher_max_turns,
        )
        self.intervention_role_runner = InterventionRoleRunner(
            env_file=config.env_file,
            max_steps_per_activation=config.teacher_max_turns,
            teacher_judge=config.teacher_judge,
            extended_worker_tools=config.intervention_extended_tools,
        )
        self.candidate_versions = CandidateVersionEffects(
            store=store,
            env_file=config.env_file,
        )
        self.backend = LocalEvaluationBackend(
            store=store,
            config=LocalEvaluationConfig(
                env_file=config.env_file,
                student_max_steps=config.student_max_steps,
                rollout_workers=config.rollout_workers,
                rollouts_per_example=config.rollouts_per_example,
                judge_workers=config.judge_workers,
                teacher_judge=config.teacher_judge,
                show_progress=config.show_progress,
                candidate_error_streak_limit=(
                    config.candidate_error_streak_limit
                ),
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
        return EvaluationEffects(
            store=self.store,
            backend=self.backend,
            experience_file=self.config.experience_file,
        ).evaluate_incumbent(
            version_id=version_id,
            work_dir=work_dir,
        )

    async def _execute_analyze_failure(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        return await self._research_role_effects().analyze_failure(
            analysis_focus=work.payload.get("analysis_focus"),
            report_dir=_ref_path(work, "report_dir"),
            rollout_file=_ref_path(work, "rollout_file"),
            recent_candidate=_recent_candidate_resource(work),
            work_dir=work_dir,
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
            return await self._research_role_effects().research_hypothesis(
                problem_direction=failure,
                report_dir=_ref_path(work, "report_dir"),
                rollout_file=_ref_path(work, "rollout_file"),
                recent_candidate=_recent_candidate_resource(work),
                work_dir=work_dir,
            )
        if not isinstance(continuation, dict):
            raise TypeError("research_continuation must be an object")
        return await self._research_role_effects().continue_hypothesis(
            previous_artifact=_read_json(
                _ref_path(work, "hypothesis_artifact")
            ),
            feedback_source=_required_string(
                continuation,
                "feedback_source",
            ),
            feedback=_required_object(continuation, "feedback"),
            trial_files=_trial_paths(work, required=False),
            work_dir=work_dir,
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
            _hypothesis_from_artifact(
                _read_json(_ref_path(work, "hypothesis_artifact"))
            )
        )
        limits = _required_payload_object(work, "trial_budget")
        max_trials = _required_positive_int(
            limits,
            "max_trials_per_hypothesis",
        )
        max_assignments = _required_positive_int(
            limits,
            "max_trial_assignments",
        )
        trial_count = _required_non_negative_int(work.payload, "trial_count")
        assignment_count = _required_non_negative_int(
            work.payload,
            "assignment_count",
        )
        if trial_count > max_trials or assignment_count > max_assignments:
            raise ValueError("Trial selection budget usage exceeds its maximum")
        return self._intervention_effects().select_trial(
            failure=failure,
            hypothesis=hypothesis,
            rollout_file=_ref_path(work, "rollout_file"),
            used_assignments={
                str(item)
                for item in work.payload.get("used_assignments", [])
            },
            assignment_count=assignment_count,
            trial_batch_size=_required_positive_int(
                limits,
                "trial_batch_size",
            ),
            remaining_trial_budget=max_trials - trial_count,
            remaining_assignment_budget=max_assignments - assignment_count,
            prior_obligation=work.payload.get("prior_obligation"),
            nearby_candidate_refs=_nearby_candidate_refs(work),
            work_dir=work_dir,
        )

    async def _execute_execute_trial(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        assignment = _required_payload_object(work, "assignment")
        hypothesis = _hypothesis_from_artifact(
            _read_json(_ref_path(work, "hypothesis_artifact"))
        )
        raw_pending = work.payload.get("pending_assignments")
        if raw_pending is not None:
            assignments = _object_list(
                raw_pending,
                "pending_assignments",
            )
            if not assignments or assignments[0] != assignment:
                raise ValueError(
                    "active Trial assignment must be the pending batch head"
                )
            return await self._intervention_effects().execute_batch(
                assignments=assignments,
                hypothesis=hypothesis,
                rollout_file=_ref_path(work, "rollout_file"),
                max_workers=self.config.rollout_workers,
                work_dir=work_dir,
            )
        return await self._intervention_effects().execute_trial(
            assignment=assignment,
            hypothesis=hypothesis,
            rollout_file=_ref_path(work, "rollout_file"),
            work_dir=work_dir,
        )

    async def _execute_review_evidence(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        trial_paths = _trial_paths(work)
        hypothesis = _hypothesis_from_artifact(
            _read_json(_ref_path(work, "hypothesis_artifact"))
        )
        persisted_reviews: dict[int, Path] = {}
        for index in range(1, len(trial_paths) + 1):
            review_key = f"trial_review_{index:03d}_artifact"
            if review_key in work.input_refs:
                persisted_reviews[index] = _ref_path(work, review_key)
                continue
            checkpoint = (
                work_dir
                / "trial_reviews"
                / f"trial_review_{index:03d}.json"
            )
            if checkpoint.is_file():
                persisted_reviews[index] = checkpoint.resolve()
        return await EvidenceReviewEffects(
            role_runner=self.role_runner,
            trial_reviewer_template_root=_template("trial_reviewer"),
            evidence_reviewer_template_root=_template(
                "evidence_reviewer"
            ),
            judge_workers=self.config.judge_workers,
        ).review(
            hypothesis=hypothesis,
            trial_paths=trial_paths,
            persisted_trial_reviews=persisted_reviews,
            budget=_evidence_review_budget(work, len(trial_paths)),
            prior_obligation=work.payload.get("prior_obligation"),
            work_dir=work_dir,
        )

    async def _execute_distill_mechanism(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        trial_paths = _trial_paths(work)
        reviewer_artifact = _read_json(
            _ref_path(work, "reviewer_artifact")
        )
        reviewer_input = reviewer_artifact.get("input")
        if not isinstance(reviewer_input, dict):
            raise TypeError("Evidence Reviewer artifact lacks structured input")
        return await self._research_role_effects().distill_mechanism(
            hypothesis=_hypothesis_from_artifact(
                _read_json(_ref_path(work, "hypothesis_artifact"))
            ),
            review=_role_output(reviewer_artifact),
            trial_reviews=list(reviewer_input.get("trial_reviews", [])),
            coverage_summary=dict(
                reviewer_input.get("coverage_summary", {})
            ),
            trial_files=trial_paths,
            budget=_evidence_review_budget(work, len(trial_paths)),
            capability_constraints=list(
                work.payload.get("capability_constraints", [])
            ),
            work_dir=work_dir,
        )

    async def _execute_compile_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        mechanism_payload = _read_json(_ref_path(work, "mechanism_file"))
        if _uses_legacy_mechanism_contract(mechanism_payload):
            return EffectResult(
                outcome={
                    "output": {
                        "decision": "needs_mechanism_revision",
                        "candidate_ref": None,
                        "implementation_summary": (
                            "The persisted Mechanism predates the operational "
                            "three-label decision contract."
                        ),
                        "unresolved_risk": (
                            "Legacy compatibility projection cannot supply "
                            "trial-grounded negative and uncertain boundaries."
                        ),
                        "next_obligation": (
                            "Redistill the mechanism from structured Trial "
                            "observations with explicit guards, positive, "
                            "negative, and uncertain rules, and phase-local "
                            "fallbacks."
                        ),
                    }
                }
            )
        mechanism = MechanismSpec.model_validate(mechanism_payload)
        student_model_experiments: list[dict[str, Any]] = []
        distiller_ref = work.input_refs.get("distiller_artifact")
        if distiller_ref is not None:
            distiller = _read_json(Path(distiller_ref))
            resource_artifacts = distiller.get("resource_artifacts")
            if isinstance(resource_artifacts, dict):
                raw_experiments = resource_artifacts.get(
                    "student_model_experiments"
                )
                if isinstance(raw_experiments, list):
                    student_model_experiments = [
                        item
                        for item in raw_experiments
                        if isinstance(item, dict)
                    ]
        feasibility_ref = work.input_refs.get(
            "hook_feasibility_artifact"
        )
        if feasibility_ref is not None:
            feasibility = _read_json(Path(feasibility_ref))
            resources = feasibility.get("resource_artifacts")
            probe = (
                resources.get("hook_feasibility_probe")
                if isinstance(resources, dict)
                else None
            )
            phase_probes = (
                probe.get("phase_probes")
                if isinstance(probe, dict)
                else None
            )
            if isinstance(phase_probes, list):
                known_signatures = {
                    item.get("experiment_signature")
                    for item in student_model_experiments
                }
                for phase_probe in phase_probes:
                    experiment = (
                        phase_probe.get("experiment")
                        if isinstance(phase_probe, dict)
                        else None
                    )
                    if not isinstance(experiment, dict):
                        continue
                    signature = experiment.get("experiment_signature")
                    if signature in known_signatures:
                        continue
                    student_model_experiments.append(experiment)
                    known_signatures.add(signature)
        continuation_ref = work.input_refs.get("compiler_candidate_file")
        if continuation_ref is not None:
            continuation_candidate = _read_json(Path(continuation_ref))
            raw_experiments = continuation_candidate.get(
                "student_model_experiments"
            )
            if isinstance(raw_experiments, list):
                known_signatures = {
                    item.get("experiment_signature")
                    for item in student_model_experiments
                }
                for item in raw_experiments:
                    if not isinstance(item, dict):
                        continue
                    signature = item.get("experiment_signature")
                    if signature in known_signatures:
                        continue
                    student_model_experiments.append(item)
                    known_signatures.add(signature)
        return await self._research_role_effects().compile_candidate(
            mechanism=mechanism,
            student_model_experiments=student_model_experiments,
            implementation_constraints=list(
                work.payload.get("implementation_constraints", [])
            ),
            validation_feedback=list(
                work.payload.get("validation_feedback", [])
            ),
            conformance_failures=_compiler_conformance_failures(work),
            continuation_candidate_file=(
                Path(work.input_refs["compiler_candidate_file"])
                if "compiler_candidate_file" in work.input_refs
                else None
            ),
            work_dir=work_dir,
        )

    async def _execute_verify_hook_feasibility(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        del state
        mechanism = MechanismSpec.model_validate(
            _read_json(_ref_path(work, "mechanism_file"))
        )
        return await HookFeasibilityEffects(
            role_runner=self.role_runner,
            reviewer_template_root=_template(
                "hook_feasibility_reviewer"
            ),
            env_file=self.config.env_file,
            probe_config=HookFeasibilityProbeConfig(
                max_cases_per_phase=(
                    self.config.hook_feasibility_max_cases
                ),
                repetitions=self.config.hook_feasibility_repetitions,
                thinking_modes=tuple(
                    self.config.hook_feasibility_thinking_modes
                ),
            ),
        ).verify(
            mechanism=mechanism,
            distiller_artifact=_read_json(
                _ref_path(work, "distiller_artifact")
            ),
            trial_paths=_trial_paths(work),
            rollout_file=_ref_path(work, "rollout_file"),
            work_dir=work_dir,
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
        return self.candidate_versions.stage(
            candidate=candidate,
            parent_version=_required_current_version(state),
            work=work,
            work_dir=work_dir,
        )

    async def _execute_evaluate_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        candidate = self._candidate_artifact(work, state)
        return EvaluationEffects(
            store=self.store,
            backend=self.backend,
            experience_file=self.config.experience_file,
        ).evaluate_candidate(
            candidate=candidate,
            work_dir=work_dir,
        )

    async def _execute_verify_conformance(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        mechanism = MechanismSpec.model_validate(
            _read_json(_ref_path(work, "mechanism_file"))
        )
        candidate = self._candidate_artifact(work, state)
        return await ConformanceEffects(
            backend=self.backend,
            role_runner=self.role_runner,
            experience_file=self.config.experience_file,
            reviewer_template_root=_template("conformance_reviewer"),
            judge_workers=self.config.judge_workers,
        ).verify(
            mechanism=mechanism,
            trial_files=_trial_paths(work),
            candidate=candidate,
            work_dir=work_dir,
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
            "mechanism_conformance": summarize_conformance_review(
                _required_payload_object(
                    work,
                    "conformance_summary",
                )
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
        return await self._research_role_effects().review_candidate(
            mechanism=mechanism,
            compiler_output=compiler_output,
            validation_summary=validation_summary,
            candidate_attempt_id=_required_candidate_attempt_id(work),
            incumbent_report_dir=_ref_path(work, "report_dir"),
            candidate_report_dir=_ref_path(
                work,
                "candidate_report_dir",
            ),
            incumbent_rollout_file=_ref_path(work, "rollout_file"),
            candidate_rollout_file=_ref_path(
                work,
                "candidate_rollout_file",
            ),
            work_dir=work_dir,
        )

    async def _execute_summarize_capability(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        """Build and execute one trigger-specific Capability Pass."""

        del state
        try:
            request = _capability_summary_request(work)
            if request is None:
                return EffectResult(
                    outcome={
                        "status": "not_eligible",
                        "source_event": _experience_source_event(work),
                    }
                )
            return await self._research_role_effects().summarize_capability(
                request=request,
                work_dir=work_dir,
            )
        except Exception as exc:
            return _summary_failure_result(work_dir, exc)

    async def _execute_summarize_direction(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        """Build and execute one trigger-specific Direction Pass."""

        del state
        try:
            request = _direction_summary_request(work)
            return await self._research_role_effects().summarize_direction(
                request=request,
                work_dir=work_dir,
            )
        except Exception as exc:
            return _summary_failure_result(work_dir, exc)

    async def _execute_promote_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        candidate_attempt_id = _required_candidate_attempt_id(work)
        completed = self.candidate_versions.promotion_result_if_completed(
            candidate_attempt_id=candidate_attempt_id,
            work_dir=work_dir,
        )
        if completed is not None:
            return completed
        compiler = _read_json(_ref_path(work, "compiler_artifact"))
        compiler_output = CompilerResult.model_validate(
            compiler.get("output")
        )
        result = self.candidate_versions.promote(
            candidate_attempt_id=candidate_attempt_id,
            implementation_summary=compiler_output.implementation_summary,
            candidate_metrics=_required_payload_object(
                work,
                "candidate_metrics",
            ),
            candidate_review=_required_payload_object(
                work,
                "candidate_review",
            ),
            promotion_gate=_required_payload_object(
                work,
                "promotion_gate",
            ),
            work_dir=work_dir,
        )
        return _enrich_candidate_digest(
            result=result,
            work=work,
            work_dir=work_dir,
        )

    async def _execute_reject_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        candidate_attempt_id = _required_candidate_attempt_id(work)
        completed = self.candidate_versions.rejection_result_if_completed(
            candidate_attempt_id=candidate_attempt_id,
            work_dir=work_dir,
        )
        if completed is not None:
            return completed
        conformance = work.payload.get("conformance_summary")
        if (
            isinstance(conformance, dict)
            and "candidate_review" not in work.payload
        ):
            return self.candidate_versions.reject(
                candidate_attempt_id=candidate_attempt_id,
                conformance_summary=conformance,
                candidate_review=None,
                promotion_gate=None,
                candidate_metrics=None,
                work_dir=work_dir,
            )
        result = self.candidate_versions.reject(
            candidate_attempt_id=candidate_attempt_id,
            conformance_summary=None,
            candidate_review=_required_payload_object(
                work,
                "candidate_review",
            ),
            promotion_gate=_required_payload_object(
                work,
                "promotion_gate",
            ),
            candidate_metrics=_required_payload_object(
                work,
                "candidate_metrics",
            ),
            work_dir=work_dir,
        )
        return _enrich_candidate_digest(
            result=result,
            work=work,
            work_dir=work_dir,
        )

    def _candidate_artifact(
        self,
        work: WorkItem,
        state: ControlState,
    ) -> CandidateArtifact:
        compiler = _read_json(_ref_path(work, "compiler_artifact"))
        output = CompilerResult.model_validate(compiler.get("output"))
        return CandidateArtifact(
            candidate_attempt_id=_required_candidate_attempt_id(work),
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

    def _intervention_effects(self) -> InterventionEffects:
        return InterventionEffects(
            role_runner=self.intervention_role_runner,
            worker_template_root=_template("intervention_worker"),
            student_template_root=self.store.template_dir,
            env_file=self.config.env_file,
            student_max_steps=self.config.student_max_steps,
        )

    def _research_role_effects(self) -> ResearchRoleEffects:
        return ResearchRoleEffects(
            role_runner=self.role_runner,
            store=self.store,
            env_file=self.config.env_file,
            teacher_template_root=TEACHER_TEMPLATE_ROOT,
            hook_feasibility_enabled=(
                self.config.hook_feasibility_enabled
            ),
        )


def _template(role_id: str) -> Path:
    return TEACHER_TEMPLATE_ROOT / role_id


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


def _required_candidate_attempt_id(work: WorkItem) -> str:
    candidate_attempt_id = work.lineage.candidate_attempt_id
    if candidate_attempt_id is None:
        raise ValueError(
            f"{work.kind.value} requires lineage candidate_attempt_id"
        )
    return candidate_attempt_id


def _required_payload_object(
    work: WorkItem,
    name: str,
) -> dict[str, Any]:
    return _required_object(work.payload, name)


def _required_current_version(state: ControlState) -> str:
    if state.current_version is None:
        raise RuntimeError("Controller state lacks current_version")
    return state.current_version


def _evidence_review_budget(
    work: WorkItem,
    persisted_trial_count: int,
) -> dict[str, Any]:
    limits = _required_payload_object(work, "trial_budget")
    max_trials = _required_positive_int(
        limits,
        "max_trials_per_hypothesis",
    )
    max_assignments = _required_positive_int(
        limits,
        "max_trial_assignments",
    )
    trials_used = _required_non_negative_int(work.payload, "trial_count")
    assignments_used = _required_non_negative_int(
        work.payload,
        "assignment_count",
    )
    if trials_used != persisted_trial_count:
        raise ValueError(
            "trial_count differs from persisted trial artifact count"
        )
    if trials_used > max_trials or assignments_used > max_assignments:
        raise ValueError("Evidence Review budget usage exceeds its maximum")
    trials_remaining = max_trials - trials_used
    assignments_remaining = max_assignments - assignments_used
    return {
        "max_trials_per_hypothesis": max_trials,
        "trials_used": trials_used,
        "trials_remaining": trials_remaining,
        "max_trial_assignments": max_assignments,
        "assignments_used": assignments_used,
        "assignments_remaining": assignments_remaining,
        "conclusion_required": (
            trials_remaining == 0 or assignments_remaining == 0
        ),
    }


def _compiler_conformance_failures(
    work: WorkItem,
) -> list[dict[str, Any]]:
    """Load compact, Reviewer-owned repair evidence for Compiler continuation."""

    summary = work.payload.get("conformance_summary")
    if not isinstance(summary, dict):
        return []
    raw_refs = summary.get("finding_refs")
    if not isinstance(raw_refs, list):
        return []
    failures = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, str) or not raw_ref.strip():
            continue
        finding_artifact = _read_json(Path(raw_ref))
        finding = finding_artifact.get("output")
        if not isinstance(finding, dict):
            continue
        if finding.get("verdict") == "faithful":
            continue
        failures.append(
            {
                key: finding.get(key)
                for key in (
                    "candidate_run_ref",
                    "verdict",
                    "assessment",
                    "repair_obligation",
                    "failure_layer",
                    "predicate_ref",
                    "expected_label",
                    "observed_label",
                    "decisive_input_summary",
                    "recommended_route",
                )
            }
        )
    return failures


def _recent_candidate_resource(
    work: WorkItem,
) -> CandidateReviewResourceConfig | None:
    """Build an optional read-only prior-Candidate evidence resource."""

    required = (
        "report_dir",
        "rollout_file",
        "candidate_report_dir",
        "candidate_rollout_file",
        "candidate_outcome_digest",
        "compiler_artifact",
    )
    if not all(name in work.input_refs for name in required):
        return None
    return CandidateReviewResourceConfig(
        incumbent_report_dir=_ref_path(work, "report_dir"),
        candidate_report_dir=_ref_path(work, "candidate_report_dir"),
        incumbent_rollout_file=_ref_path(work, "rollout_file"),
        candidate_rollout_file=_ref_path(work, "candidate_rollout_file"),
        outcome_digest_file=_ref_path(work, "candidate_outcome_digest"),
        compiler_artifact_file=_ref_path(work, "compiler_artifact"),
    )


def _nearby_candidate_refs(work: WorkItem) -> list[str]:
    """Load prioritized example/replicate refs from a prior Candidate digest."""

    raw_path = work.input_refs.get("candidate_outcome_digest")
    if raw_path is None:
        return []
    digest = _read_json(Path(raw_path))
    nearby = digest.get("nearby_cases")
    nearby = nearby if isinstance(nearby, dict) else {}
    refs = []
    for category in (
        "harmful_activation",
        "neutral_activation",
        "missed_target",
        "false_positive",
        "parse_failure",
        "unattributed_regression",
        "beneficial_activation",
    ):
        items = nearby.get(category)
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            example_id = item.get("example_id")
            replicate_id = item.get("replicate_id")
            if isinstance(example_id, str) and isinstance(replicate_id, str):
                refs.append(f"{example_id}/{replicate_id}")
    return list(dict.fromkeys(refs))


def _enrich_candidate_digest(
    *,
    result: EffectResult,
    work: WorkItem,
    work_dir: Path,
) -> EffectResult:
    """Append review and gate conclusions to a new immutable digest artifact."""

    raw_path = work.input_refs.get("candidate_outcome_digest")
    if raw_path is None:
        return result
    digest = _read_json(Path(raw_path))
    digest["candidate_review"] = work.payload.get("candidate_review")
    digest["promotion_gate"] = work.payload.get("promotion_gate")
    path = work_dir / "candidate_outcome_digest_final.json"
    path.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return EffectResult(
        outcome=dict(result.outcome),
        artifact_refs={
            **result.artifact_refs,
            "candidate_outcome_digest": str(path.resolve()),
        },
        usage=dict(result.usage),
    )


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def _uses_legacy_mechanism_contract(payload: dict[str, Any]) -> bool:
    """Identify readable legacy specs that must be redistilled before compile."""

    rules = payload.get("phase_rules")
    if not isinstance(rules, list) or not rules:
        return "trigger_condition" in payload
    return any(
        not isinstance(rule, dict) or "decision_contract" not in rule
        for rule in rules
    )


def _required_object(
    value: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _object_list(value: object, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a list")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"{name}[{index}] must be an object")
        result.append(dict(item))
    return result


def _required_positive_int(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise TypeError(f"{name} must be a positive integer")
    return item


def _required_non_negative_int(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise TypeError(f"{name} must be a non-negative integer")
    return item


def _role_output(artifact: dict[str, Any]) -> dict[str, Any]:
    return _required_object(artifact, "output")


def _hypothesis_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    output = _role_output(artifact)
    hypothesis = output.get("hypothesis")
    if not isinstance(hypothesis, dict):
        raise TypeError("Researcher artifact lacks an active hypothesis")
    return hypothesis


def _experience_source_event(work: WorkItem) -> str:
    return _required_payload_string(work, "experience_source_event")


def _capability_summary_request(
    work: WorkItem,
) -> ExperienceSummaryRequest | None:
    event = _experience_source_event(work)
    if event == "hook_feasibility.needs_research_revision":
        probe_path = _ref_path(work, "hook_feasibility_probe")
        return build_hook_feasibility_capability_request(
            _read_json(probe_path),
            source_ref="hook_feasibility_probe",
        )
    if event == "conformance.revise":
        findings: list[dict[str, Any]] = []
        refs: list[str] = []
        for key, raw_path in sorted(work.input_refs.items()):
            if not key.startswith("conformance_finding_"):
                continue
            artifact = _read_json(Path(raw_path))
            output = artifact.get("output")
            if isinstance(output, dict):
                findings.append(output)
                refs.append(key)
        return build_conformance_capability_request(
            findings,
            source_refs=refs,
            mechanism=(
                _read_json(_ref_path(work, "mechanism_file"))
                if "mechanism_file" in work.input_refs
                else None
            ),
        )
    if event in {
        "evidence_reviewer.reject",
        "evidence_reviewer.revise",
    }:
        # These sources are conditionally eligible only when their typed
        # artifacts contain repeatable direct evaluator decisions. The current
        # adapters intentionally decline aggregate Reviewer prose.
        return None
    raise ValueError(f"unsupported Capability source event: {event}")


def _direction_summary_request(work: WorkItem) -> ExperienceSummaryRequest:
    event = _experience_source_event(work)
    failure = _role_output(
        _read_json(_ref_path(work, "failure_artifact"))
    )
    researcher = _role_output(
        _read_json(_ref_path(work, "hypothesis_artifact"))
    )
    hypothesis = researcher.get("hypothesis")
    if not isinstance(hypothesis, dict):
        raise TypeError("Direction source lacks the active Research Scheme")
    failure_id = _required_payload_string(work, "failure_direction_id")
    research_id = _required_payload_string(work, "research_scheme_id")
    mechanism_id = work.payload.get("mechanism_scheme_id")
    if mechanism_id is not None and not isinstance(mechanism_id, str):
        raise TypeError("mechanism_scheme_id must be a string")
    mechanism = (
        _read_json(_ref_path(work, "mechanism_file"))
        if "mechanism_file" in work.input_refs
        else None
    )
    failure_summary = _failure_direction_summary(failure)
    research_summary = _research_scheme_summary(hypothesis)
    mechanism_summary = (
        _mechanism_scheme_summary(mechanism)
        if mechanism is not None
        else None
    )
    if event in {"promotion_gate.failed", "promotion_gate.passed"}:
        if mechanism is None or mechanism_id is None:
            raise ValueError("Promotion Direction requires a Mechanism Scheme")
        return build_promotion_direction_request(
            failure_direction_id=failure_id,
            failure_summary=failure_summary,
            research_scheme_id=research_id,
            research_summary=research_summary,
            mechanism_scheme_id=mechanism_id,
            mechanism_summary=mechanism_summary or "Current Mechanism Scheme.",
            mechanism_goal=str(mechanism.get("goal", "Goal not recorded.")),
            candidate_review=_required_payload_object(
                work,
                "candidate_review",
            ),
            promotion_gate=_required_payload_object(
                work,
                "promotion_gate",
            ),
            source_refs=_experience_source_refs(work),
        )
    source_outcome = _required_payload_object(
        work,
        "experience_source_outcome",
    )
    source_output = _required_object(source_outcome, "output")
    target_is_mechanism = event in {
        "hook_feasibility.needs_spec_revision",
        "compiler.needs_mechanism_revision",
        "compiler.implementation_blocked",
        "conformance.revise_mechanism",
        "candidate_reviewer.revise_mechanism",
        "candidate_reviewer.reject",
    }
    if target_is_mechanism and (mechanism is None or mechanism_id is None):
        raise ValueError(
            f"Direction event {event} requires a Mechanism Scheme"
        )
    expected = (
        str(mechanism.get("goal", "Goal not recorded."))
        if target_is_mechanism and mechanism is not None
        else research_summary
    )
    return build_workflow_direction_request(
        source_event=event,
        failure_direction_id=failure_id,
        failure_summary=failure_summary,
        research_scheme_id=research_id,
        research_summary=research_summary,
        mechanism_scheme_id=mechanism_id,
        mechanism_summary=mechanism_summary,
        expected=expected,
        source_output=source_output,
        source_refs=_experience_source_refs(work),
    )


def _failure_direction_summary(value: dict[str, Any]) -> str:
    pattern = str(value.get("pattern", "Pattern not recorded."))
    applicability = str(value.get("applicability", ""))
    return f"{pattern} Applicability: {applicability}"[:800]


def _research_scheme_summary(value: dict[str, Any]) -> str:
    evaluation = value.get("evaluation")
    primary = (
        evaluation.get("primary_signal")
        if isinstance(evaluation, dict)
        else None
    )
    phases = value.get("phase_plan")
    phase_names = [
        str(item.get("phase"))
        for item in phases
        if isinstance(item, dict) and item.get("phase")
    ] if isinstance(phases, list) else []
    return (
        f"Applicability: {value.get('applicability', 'not recorded')}; "
        f"phases: {', '.join(phase_names) or 'not recorded'}; "
        f"primary signal: {primary or 'not recorded'}"
    )[:800]


def _mechanism_scheme_summary(value: dict[str, Any]) -> str:
    return (
        f"Goal: {value.get('goal', 'not recorded')}; "
        f"expected behavior: {value.get('expected_behavior', 'not recorded')}; "
        f"fallback: {value.get('fallback', 'not recorded')}"
    )[:800]


def _experience_source_refs(work: WorkItem) -> list[str]:
    return sorted(
        key
        for key in work.input_refs
        if key in {
            "failure_artifact",
            "hypothesis_artifact",
            "reviewer_artifact",
            "distiller_artifact",
            "mechanism_file",
            "hook_feasibility_artifact",
            "hook_feasibility_probe",
            "compiler_artifact",
            "conformance_summary_artifact",
            "candidate_reviewer_artifact",
            "candidate_outcome_digest",
        }
    )


def _summary_failure_result(work_dir: Path, exc: Exception) -> EffectResult:
    failure = {
        "status": "failed",
        "error": f"{type(exc).__name__}: {exc}",
    }
    artifact = getattr(exc, "failure_artifact", None)
    if isinstance(artifact, dict):
        failure["role_failure"] = artifact
    path = work_dir / "summary.failed.json"
    path.write_text(
        json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    usage = artifact.get("usage") if isinstance(artifact, dict) else None
    total_tokens = (
        usage.get("total_tokens", 0)
        if isinstance(usage, dict)
        else 0
    )
    return EffectResult(
        outcome=failure,
        artifact_refs={"summary_failure_artifact": str(path.resolve())},
        usage={
            "total_tokens": (
                total_tokens if isinstance(total_tokens, int) else 0
            )
        },
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value
