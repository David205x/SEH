"""Teacher Research Role invocation effects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.experience_summary import (
    ExperienceSummaryRequest,
    materialize_capability_experience_product,
)
from search_harness.evolution.research.resources.stores import (
    CandidateComparisonStore,
    CandidateReviewResourceConfig,
    CompilerResourceConfig,
)
from search_harness.evolution.research.candidate_digest import (
    build_candidate_outcome_digest,
    write_candidate_outcome_digest,
)
from search_harness.evolution.research.hook_feasibility import (
    mechanism_requires_hook_feasibility,
)
from search_harness.evolution.research.roles.contracts import (
    CandidateReview,
    CapabilityExperienceSummary,
    CompilerResult,
    DirectionSummary,
    FailureDirection,
    HypothesisResearcherResult,
    MechanismDistillation,
    MechanismSpec,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)
from search_harness.evolution.versioning import TemplateVersionStore

from .domain import EffectResult


class ResearchRoleEffects:
    """Invoke non-Intervention Teacher Roles and persist their artifacts."""

    def __init__(
        self,
        *,
        role_runner: NativeChatRoleRunner,
        store: TemplateVersionStore,
        env_file: Path,
        teacher_template_root: Path,
        hook_feasibility_enabled: bool = False,
    ) -> None:
        self.role_runner = role_runner
        self.store = store
        self.env_file = env_file
        self.teacher_template_root = teacher_template_root
        self.hook_feasibility_enabled = hook_feasibility_enabled

    async def analyze_failure(
        self,
        *,
        analysis_focus: object,
        report_dir: Path,
        rollout_file: Path,
        recent_candidate: CandidateReviewResourceConfig | None = None,
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.role_runner.run(
            template_root=self._template("failure_analyst"),
            role_id="failure_analyst",
            role_version=1,
            role_input={"analysis_focus": analysis_focus},
            resource_config=TeacherResourceConfig(
                report_dir=report_dir,
                rollout_file=rollout_file,
                student_template_root=self.store.template_dir,
                candidate_review=recent_candidate,
            ),
        )
        output = FailureDirection.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"failure_artifact": str(path)},
        )

    async def research_hypothesis(
        self,
        *,
        problem_direction: dict[str, Any],
        report_dir: Path,
        rollout_file: Path,
        recent_candidate: CandidateReviewResourceConfig | None = None,
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.role_runner.run(
            template_root=self._template("hypothesis_researcher"),
            role_id="hypothesis_researcher",
            role_version=2,
            role_input={"problem_direction": problem_direction},
            resource_config=TeacherResourceConfig(
                report_dir=report_dir,
                rollout_file=rollout_file,
                student_template_root=self.store.template_dir,
                candidate_review=recent_candidate,
            ),
        )
        return _hypothesis_result(
            artifact,
            work_dir,
            initial_call=True,
        )

    async def continue_hypothesis(
        self,
        *,
        previous_artifact: dict[str, Any],
        feedback_source: str,
        feedback: dict[str, Any],
        trial_files: list[Path],
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.role_runner.continue_researcher(
            previous_artifact=previous_artifact,
            feedback_source=feedback_source,
            feedback=feedback,
            trial_files=trial_files,
        )
        return _hypothesis_result(artifact, work_dir, initial_call=False)

    async def distill_mechanism(
        self,
        *,
        hypothesis: dict[str, Any],
        review: dict[str, Any],
        trial_reviews: list[dict[str, Any]],
        coverage_summary: dict[str, Any],
        trial_files: list[Path],
        budget: dict[str, Any],
        capability_constraints: list[Any],
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.role_runner.run(
            template_root=self._template("mechanism_distiller"),
            role_id="mechanism_distiller",
            role_version=1,
            role_input={
                "hypothesis": hypothesis,
                "review": review,
                "trial_reviews": trial_reviews,
                "coverage_summary": coverage_summary,
                "evidence_refs": [
                    path.parent.name for path in trial_files
                ],
                "budget": budget,
                "capability_constraints": capability_constraints,
            },
            resource_config=TeacherResourceConfig(
                trial_files=trial_files,
                hook_probe_env_file=self.env_file,
            ),
        )
        output = MechanismDistillation.model_validate(
            artifact.get("output")
        )
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
        result = _role_result(
            output.model_dump(mode="json"),
            artifact,
            refs,
        )
        if output.decision != "distilled":
            return result
        return EffectResult(
            outcome={
                **result.outcome,
                "requires_hook_feasibility": (
                    self.hook_feasibility_enabled
                    and mechanism_requires_hook_feasibility(mechanism)
                ),
                "effect_goal": mechanism.effect_goal,
            },
            artifact_refs=result.artifact_refs,
            usage=result.usage,
        )

    async def compile_candidate(
        self,
        *,
        mechanism: MechanismSpec,
        student_model_experiments: list[dict[str, Any]],
        implementation_constraints: list[Any],
        validation_feedback: list[Any],
        work_dir: Path,
        continuation_candidate_file: Path | None = None,
        conformance_failures: list[dict[str, Any]] | None = None,
    ) -> EffectResult:
        artifact = await self.role_runner.run(
            template_root=self._template("compiler"),
            role_id="compiler",
            role_version=1,
            role_input={
                "mechanism": mechanism.model_dump(mode="json"),
                "student_model_experiments": student_model_experiments,
                "implementation_constraints": implementation_constraints,
                "validation_feedback": validation_feedback,
                "conformance_failures": conformance_failures or [],
            },
            resource_config=TeacherResourceConfig(
                hook_probe_env_file=self.env_file,
                compiler=CompilerResourceConfig(
                    parent_template_root=self.store.template_dir,
                    env_file=self.env_file,
                    continuation_candidate_file=(
                        continuation_candidate_file
                    ),
                )
            ),
        )
        output = CompilerResult.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        refs = {"compiler_artifact": str(path)}
        if output.decision == "submitted":
            resources = artifact.get("resource_artifacts")
            resources = resources if isinstance(resources, dict) else {}
            candidate = resources.get("compiler_candidate")
            if not isinstance(candidate, dict):
                raise ValueError(
                    "submitted Compiler artifact lacks compiler_candidate"
                )
            candidate = dict(candidate)
            experiments = resources.get("student_model_experiments")
            candidate["student_model_experiments"] = (
                [item for item in experiments if isinstance(item, dict)]
                if isinstance(experiments, list)
                else []
            )
            candidate_path = _write_json(
                work_dir / "candidate_workspace.json",
                candidate,
            )
            refs["compiler_candidate_file"] = str(candidate_path)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            refs,
        )

    async def review_candidate(
        self,
        *,
        mechanism: MechanismSpec,
        compiler_output: CompilerResult,
        validation_summary: dict[str, Any],
        candidate_attempt_id: str,
        incumbent_report_dir: Path,
        candidate_report_dir: Path,
        incumbent_rollout_file: Path,
        candidate_rollout_file: Path,
        work_dir: Path,
    ) -> EffectResult:
        comparison_config = CandidateReviewResourceConfig(
            incumbent_report_dir=incumbent_report_dir,
            candidate_report_dir=candidate_report_dir,
            incumbent_rollout_file=incumbent_rollout_file,
            candidate_rollout_file=candidate_rollout_file,
            incumbent_template_root=self.store.template_dir,
        )
        report_summaries = (
            incumbent_report_dir / "summary.json",
            candidate_report_dir / "summary.json",
        )
        if all(path.is_file() for path in report_summaries):
            outcome_digest = build_candidate_outcome_digest(
                store=CandidateComparisonStore.load(comparison_config),
                mechanism=mechanism.model_dump(mode="json"),
                implementation_summary=(
                    compiler_output.implementation_summary
                ),
            )
        elif any(path.exists() for path in report_summaries):
            raise FileNotFoundError(
                "Candidate outcome digest requires both Evaluation reports"
            )
        else:
            outcome_digest = {
                "schema_version": 1,
                "effect_goal": mechanism.effect_goal,
                "implementation_summary": (
                    compiler_output.implementation_summary
                ),
                "hook_activity": {},
                "nearby_cases": {},
                "status": "unavailable_in_synthetic_role_test",
            }
        digest_path = write_candidate_outcome_digest(
            work_dir / "candidate_outcome_digest.json",
            outcome_digest,
        )
        attempt = self.store.resume_candidate_attempt(candidate_attempt_id)
        with attempt.stage() as candidate_template_root:
            comparison_config = comparison_config.model_copy(
                update={"candidate_template_root": candidate_template_root}
            )
            artifact = await self.role_runner.run(
                template_root=self._template("candidate_reviewer"),
                role_id="candidate_reviewer",
                role_version=1,
                role_input={
                    "mechanism": mechanism.model_dump(mode="json"),
                    "validation_summary": validation_summary,
                    "implementation_summary": (
                        compiler_output.implementation_summary
                    ),
                    "candidate_outcome_digest": outcome_digest,
                    "unresolved_risk": compiler_output.unresolved_risk,
                    "historical_experience": [],
                },
                resource_config=TeacherResourceConfig(
                    candidate_review=comparison_config
                ),
            )
        output = CandidateReview.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {
                "candidate_reviewer_artifact": str(path),
                "candidate_outcome_digest": str(digest_path),
            },
            extra_outcome={"candidate_outcome_digest": outcome_digest},
        )

    async def summarize_capability(
        self,
        *,
        request: ExperienceSummaryRequest,
        work_dir: Path,
    ) -> EffectResult:
        """Run one independent Capability Summarization Pass."""

        artifact = await self.role_runner.run(
            template_root=self._template("capability_summarizer"),
            role_id="capability_summarizer",
            role_version=2,
            role_input=request.role_input.model_dump(mode="json"),
            resource_config=TeacherResourceConfig(
                experience_summary=request.resources
            ),
        )
        output = CapabilityExperienceSummary.model_validate(
            artifact.get("output")
        )
        product = materialize_capability_experience_product(request, output)
        role_path = _write_json(work_dir / "role.json", artifact)
        product_path = _write_json(
            work_dir / "capability_experience.json",
            product.model_dump(mode="json"),
        )
        return _role_result(
            product.model_dump(mode="json"),
            artifact,
            {
                "capability_summarizer_artifact": str(role_path),
                "capability_experience_artifact": str(product_path),
            },
        )

    async def summarize_direction(
        self,
        *,
        request: ExperienceSummaryRequest,
        work_dir: Path,
    ) -> EffectResult:
        """Run one independent Direction Summarization Pass."""

        artifact = await self.role_runner.run(
            template_root=self._template("direction_summarizer"),
            role_id="direction_summarizer",
            role_version=1,
            role_input=request.role_input.model_dump(mode="json"),
            resource_config=TeacherResourceConfig(
                experience_summary=request.resources
            ),
        )
        output = DirectionSummary.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {"direction_draft_artifact": str(path)},
        )

    def _template(self, role_id: str) -> Path:
        return self.teacher_template_root / role_id


def _hypothesis_result(
    artifact: dict[str, Any],
    work_dir: Path,
    *,
    initial_call: bool,
) -> EffectResult:
    output = HypothesisResearcherResult.model_validate(
        artifact.get("output")
    )
    if initial_call and output.scheme_action != "start_new":
        raise ValueError(
            "initial Hypothesis Researcher call must start a Research Scheme"
        )
    path = _write_json(work_dir / "role.json", artifact)
    return _role_result(
        output.model_dump(mode="json"),
        artifact,
        {"hypothesis_artifact": str(path)},
    )


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _role_result(
    output: dict[str, Any],
    artifact: dict[str, Any],
    refs: dict[str, str],
    extra_outcome: dict[str, Any] | None = None,
) -> EffectResult:
    usage = artifact.get("usage")
    total_tokens = (
        usage.get("total_tokens", 0)
        if isinstance(usage, dict)
        else 0
    )
    return EffectResult(
        outcome={"output": output, **(extra_outcome or {})},
        artifact_refs=refs,
        usage={"total_tokens": _non_negative_int(total_tokens)},
    )


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
