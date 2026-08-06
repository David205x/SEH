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
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)
from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
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

    def __post_init__(self) -> None:
        positive = {
            "student_max_steps": self.student_max_steps,
            "teacher_max_turns": self.teacher_max_turns,
            "rollout_workers": self.rollout_workers,
            "rollouts_per_example": self.rollouts_per_example,
            "judge_workers": self.judge_workers,
            "candidate_error_streak_limit": (
                self.candidate_error_streak_limit
            ),
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")


class LocalControlEffects:
    """Connect the nine v2 roles to rollouts and external effects."""

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
            _role_output(_read_json(_ref_path(work, "hypothesis_artifact")))
        )
        return self._intervention_effects().select_trial(
            failure=failure,
            hypothesis=hypothesis,
            rollout_file=_ref_path(work, "rollout_file"),
            used_assignments={
                str(item)
                for item in work.payload.get("used_assignments", [])
            },
            assignment_count=int(
                work.payload.get("assignment_count", 0)
            ),
            prior_obligation=work.payload.get("prior_obligation"),
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
        hypothesis = _role_output(
            _read_json(_ref_path(work, "hypothesis_artifact"))
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
        hypothesis = _role_output(
            _read_json(_ref_path(work, "hypothesis_artifact"))
        )
        persisted_reviews: dict[int, Path] = {}
        for index in range(1, len(trial_paths) + 1):
            review_key = f"trial_review_{index:03d}_artifact"
            if review_key in work.input_refs:
                persisted_reviews[index] = _ref_path(work, review_key)
        return await EvidenceReviewEffects(
            role_runner=self.role_runner,
            trial_reviewer_template_root=_template("trial_reviewer"),
            evidence_reviewer_template_root=_template(
                "evidence_reviewer"
            ),
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
        return await self._research_role_effects().distill_mechanism(
            hypothesis=_role_output(
                _read_json(_ref_path(work, "hypothesis_artifact"))
            ),
            review=_role_output(
                _read_json(_ref_path(work, "reviewer_artifact"))
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
        mechanism = MechanismSpec.model_validate(
            _read_json(_ref_path(work, "mechanism_file"))
        )
        return await self._research_role_effects().compile_candidate(
            mechanism=mechanism,
            implementation_constraints=list(
                work.payload.get("implementation_constraints", [])
            ),
            validation_feedback=list(
                work.payload.get("validation_feedback", [])
            ),
            continuation_candidate_file=(
                Path(work.input_refs["compiler_candidate_file"])
                if "compiler_candidate_file" in work.input_refs
                else None
            ),
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
            candidate_attempt_id=_required_payload_string(work, "candidate_attempt_id"),
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

    async def _execute_promote_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        candidate_attempt_id = _required_payload_string(work, "candidate_attempt_id")
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
        return self.candidate_versions.promote(
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

    async def _execute_reject_candidate(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        candidate_attempt_id = _required_payload_string(work, "candidate_attempt_id")
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
        return self.candidate_versions.reject(
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

    def _candidate_artifact(
        self,
        work: WorkItem,
        state: ControlState,
    ) -> CandidateArtifact:
        compiler = _read_json(_ref_path(work, "compiler_artifact"))
        output = CompilerResult.model_validate(compiler.get("output"))
        return CandidateArtifact(
            candidate_attempt_id=_required_payload_string(work, "candidate_attempt_id"),
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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value
