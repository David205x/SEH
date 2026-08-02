"""Teacher Research Role invocation effects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.resources.stores import (
    CandidateReviewResourceConfig,
    CompilerResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    CandidateReview,
    CompilerResult,
    FailureDirection,
    InterventionHypothesis,
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
    ) -> None:
        self.role_runner = role_runner
        self.store = store
        self.env_file = env_file
        self.teacher_template_root = teacher_template_root

    async def analyze_failure(
        self,
        *,
        analysis_focus: object,
        report_dir: Path,
        rollout_file: Path,
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
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.role_runner.run(
            template_root=self._template("hypothesis_researcher"),
            role_id="hypothesis_researcher",
            role_version=1,
            role_input={"problem_direction": problem_direction},
            resource_config=TeacherResourceConfig(
                report_dir=report_dir,
                rollout_file=rollout_file,
                student_template_root=self.store.template_dir,
            ),
        )
        return _hypothesis_result(artifact, work_dir)

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
        return _hypothesis_result(artifact, work_dir)

    async def distill_mechanism(
        self,
        *,
        hypothesis: dict[str, Any],
        review: dict[str, Any],
        trial_files: list[Path],
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
                "evidence_refs": [
                    path.parent.name for path in trial_files
                ],
                "capability_constraints": capability_constraints,
            },
            resource_config=TeacherResourceConfig(
                trial_files=trial_files
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
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            refs,
        )

    async def compile_candidate(
        self,
        *,
        mechanism: MechanismSpec,
        implementation_constraints: list[Any],
        validation_feedback: list[Any],
        work_dir: Path,
    ) -> EffectResult:
        artifact = await self.role_runner.run(
            template_root=self._template("compiler"),
            role_id="compiler",
            role_version=1,
            role_input={
                "mechanism": mechanism.model_dump(mode="json"),
                "implementation_constraints": implementation_constraints,
                "validation_feedback": validation_feedback,
            },
            resource_config=TeacherResourceConfig(
                compiler=CompilerResourceConfig(
                    parent_template_root=self.store.template_dir,
                    env_file=self.env_file,
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
        attempt = self.store.resume_candidate_attempt(candidate_attempt_id)
        with attempt.stage() as candidate_template_root:
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
                    "unresolved_risk": compiler_output.unresolved_risk,
                    "historical_experience": [],
                },
                resource_config=TeacherResourceConfig(
                    candidate_review=CandidateReviewResourceConfig(
                        incumbent_report_dir=incumbent_report_dir,
                        candidate_report_dir=candidate_report_dir,
                        incumbent_rollout_file=incumbent_rollout_file,
                        candidate_rollout_file=candidate_rollout_file,
                        incumbent_template_root=self.store.template_dir,
                        candidate_template_root=candidate_template_root,
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

    def _template(self, role_id: str) -> Path:
        return self.teacher_template_root / role_id


def _hypothesis_result(
    artifact: dict[str, Any],
    work_dir: Path,
) -> EffectResult:
    output = InterventionHypothesis.model_validate(artifact.get("output"))
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


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
