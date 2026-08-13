"""Controller Research Role effect tests."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator
from unittest import IsolatedAsyncioTestCase

from search_harness.evolution.control.research_role_effects import (
    ResearchRoleEffects,
)
from search_harness.evolution.research.roles.contracts import CompilerResult

from tests.evolution.research.intervention.test_role_runner import _hypothesis
from tests.evolution.research.mechanism.test_compiler_capabilities import (
    _mechanism,
)


class _RecordingRoleRunner:
    def __init__(self, mechanism: dict[str, Any]) -> None:
        self.mechanism = mechanism
        self.calls: list[dict[str, Any]] = []
        self.continuations: list[dict[str, Any]] = []

    async def run(self, **values: Any) -> dict[str, Any]:
        self.calls.append(values)
        role_id = values["role_id"]
        outputs = {
            "failure_analyst": {
                "pattern": "The Student stops after partial evidence.",
                "applicability": "Search trajectories with a missing fact.",
                "caveats": ["Prevalence is unknown."],
                "evidence_refs": ["example-1/r000", "example-2/r000"],
            },
            "hypothesis_researcher": _hypothesis(),
            "mechanism_distiller": {
                "decision": "distilled",
                "mechanism_ref": "mechanism:test",
                "rationale": "The evidence supports a bounded mechanism.",
                "next_obligation": None,
            },
            "compiler": {
                "decision": "submitted",
                "candidate_ref": "candidate:test",
                "implementation_summary": "Implement the tested mechanism.",
                "unresolved_risk": None,
            },
            "candidate_reviewer": {
                "recommendation": "accept",
                "observed_effect": "The intended behavior was observed.",
                "reason": "Validation and evaluation support acceptance.",
                "next_obligation": None,
                "revision_target": None,
            },
        }
        artifact: dict[str, Any] = {
            "output": outputs[role_id],
            "usage": {"total_tokens": 3},
        }
        if role_id == "mechanism_distiller":
            artifact["validated_mechanisms"] = {
                "mechanism:test": self.mechanism
            }
        if role_id == "compiler":
            artifact["resource_artifacts"] = {
                "compiler_candidate": {
                    "candidate_ref": "candidate:test",
                    "summary": "Implement the tested mechanism.",
                    "parent_digest": "parent-digest",
                    "candidate_digest": "candidate-digest",
                    "changed_files": {
                        "extensions/test/component.py": "def build():\n    pass\n"
                    },
                    "queried_symbols": [],
                }
            }
        return artifact

    async def continue_researcher(
        self,
        **values: Any,
    ) -> dict[str, Any]:
        self.continuations.append(values)
        return {
            "output": _hypothesis(),
            "usage": {"total_tokens": 2},
        }


class _Store:
    def __init__(self, root: Path) -> None:
        self.template_dir = root / "student"
        self.candidate_dir = root / "candidate"

    def resume_candidate_attempt(self, candidate_attempt_id: str) -> "_Store":
        if candidate_attempt_id != "candidate_attempt:test":
            raise AssertionError(candidate_attempt_id)
        return self

    @contextmanager
    def stage(self) -> Iterator[Path]:
        yield self.candidate_dir


class ResearchRoleEffectsTest(IsolatedAsyncioTestCase):
    async def test_routes_all_non_intervention_research_roles(self) -> None:
        """Each Role receives its own Template, resources, and artifact key."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mechanism = _mechanism(
                trigger_phase="post_tool",
                decision_inputs=["tool_result"],
                required_capabilities=["read_stage_value"],
            )
            runner = _RecordingRoleRunner(
                mechanism.model_dump(mode="json")
            )
            effects = ResearchRoleEffects(
                role_runner=runner,  # type: ignore[arg-type]
                store=_Store(root),  # type: ignore[arg-type]
                env_file=root / ".env",
                teacher_template_root=root / "teacher",
            )
            failure = await effects.analyze_failure(
                analysis_focus=None,
                report_dir=root / "report",
                rollout_file=root / "rollouts.jsonl",
                work_dir=root / "failure",
            )
            hypothesis = await effects.research_hypothesis(
                problem_direction=failure.outcome["output"],
                report_dir=root / "report",
                rollout_file=root / "rollouts.jsonl",
                work_dir=root / "hypothesis",
            )
            continued = await effects.continue_hypothesis(
                previous_artifact={"output": hypothesis.outcome["output"]},
                feedback_source="evidence_reviewer",
                feedback={"decision": "revise"},
                trial_files=[root / "trial_001" / "trial.json"],
                work_dir=root / "continued",
            )
            distilled = await effects.distill_mechanism(
                hypothesis=continued.outcome["output"],
                review={"decision": "ready_to_distill"},
                trial_reviews=[
                    {
                        "trial_ref": "trial_001",
                        "assessment": "The intervention was observed.",
                    }
                ],
                coverage_summary={
                    "required_distinct_examples": 3,
                    "required_positive_per_phase": 2,
                    "required_negative_per_phase": 2,
                    "observed_distinct_examples": 3,
                    "phase_coverage": [],
                    "unmet_requirements": [],
                    "special_obligations": [],
                    "default_requirements_met": True,
                },
                trial_files=[root / "trial_001" / "trial.json"],
                budget={
                    "max_trials_per_hypothesis": 5,
                    "trials_used": 1,
                    "trials_remaining": 4,
                    "max_trial_assignments": 12,
                    "assignments_used": 1,
                    "assignments_remaining": 11,
                    "conclusion_required": False,
                },
                capability_constraints=[],
                work_dir=root / "distilled",
            )
            compiled = await effects.compile_candidate(
                mechanism=mechanism,
                implementation_constraints=[],
                validation_feedback=[],
                work_dir=root / "compiled",
            )
            reviewed = await effects.review_candidate(
                mechanism=mechanism,
                compiler_output=CompilerResult.model_validate(
                    compiled.outcome["output"]
                ),
                validation_summary={"passed": True},
                candidate_attempt_id="candidate_attempt:test",
                incumbent_report_dir=root / "incumbent-report",
                candidate_report_dir=root / "candidate-report",
                incumbent_rollout_file=root / "incumbent.jsonl",
                candidate_rollout_file=root / "candidate.jsonl",
                work_dir=root / "reviewed",
            )

        self.assertIn("mechanism_file", distilled.artifact_refs)
        self.assertIn("compiler_artifact", compiled.artifact_refs)
        self.assertIn("compiler_candidate_file", compiled.artifact_refs)
        self.assertIn("candidate_reviewer_artifact", reviewed.artifact_refs)
        self.assertEqual(
            [call["role_id"] for call in runner.calls],
            [
                "failure_analyst",
                "hypothesis_researcher",
                "mechanism_distiller",
                "compiler",
                "candidate_reviewer",
            ],
        )
        self.assertEqual(len(runner.continuations), 1)
        self.assertEqual(
            runner.continuations[0]["trial_files"],
            [root / "trial_001" / "trial.json"],
        )
