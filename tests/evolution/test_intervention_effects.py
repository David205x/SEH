"""Controller Intervention trial effect tests."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import IsolatedAsyncioTestCase

from search_harness.evolution.control.intervention_effects import (
    InterventionEffects,
)
from search_harness.evolution.research.roles.contracts import (
    FailureDirection,
    InterventionHypothesis,
)

from tests.evolution.research.intervention.test_prefix import _write_rollout
from tests.evolution.research.intervention.test_role_runner import _hypothesis


class _RecordingInterventionRoleRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **values: Any) -> dict[str, Any]:
        self.calls.append(values)
        return _worker_artifact("executed")


class InterventionEffectsTest(IsolatedAsyncioTestCase):
    async def test_selects_prefix_and_executes_frozen_assignment(self) -> None:
        """Selection and execution preserve the registered trial objective."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout(rollout_file)
            runner = _RecordingInterventionRoleRunner()
            effects = InterventionEffects(
                role_runner=runner,  # type: ignore[arg-type]
                worker_template_root=root / "worker",
                student_template_root=root / "student",
                env_file=root / ".env",
                student_max_steps=4,
            )
            hypothesis = InterventionHypothesis.model_validate(
                _hypothesis()
            )
            selected = effects.select_trial(
                failure=FailureDirection(
                    pattern="The Student stops after partial evidence.",
                    applicability="Search trajectories with a missing fact.",
                    caveats=["Prevalence is unknown."],
                    evidence_refs=[
                        "example-1/r000",
                        "example-1/r001",
                    ],
                ),
                hypothesis=hypothesis,
                rollout_file=rollout_file,
                used_assignments=set(),
                assignment_count=0,
                prior_obligation="Cover the abandonment case.",
                work_dir=root / "selection",
            )
            assignment = selected.outcome["assignment"]
            executed = await effects.execute_trial(
                assignment=assignment,
                hypothesis=hypothesis.model_dump(mode="json"),
                rollout_file=rollout_file,
                work_dir=root / "trial",
            )

        self.assertEqual(assignment["prefix_id"], 5)
        self.assertEqual(
            assignment["trial_objective"],
            " | ".join(
                [
                    hypothesis.evaluation.primary_signal,
                    hypothesis.evaluation.success_condition,
                    hypothesis.evaluation.falsifier,
                    "Cover the abandonment case.",
                ]
            ),
        )
        self.assertEqual(executed.outcome["output"]["result_kind"], "executed")
        intervention = runner.calls[0]["resource_config"].intervention
        self.assertEqual(intervention.rollout_file, rollout_file)
        self.assertEqual(intervention.student_max_steps, 4)


def _worker_artifact(result_kind: str) -> dict[str, Any]:
    return {
        "output": {
            "result_kind": result_kind,
            "activated_phases": ["post_tool"],
            "modified_phases": ["post_tool"],
            "unmet_phases": [],
        },
        "resource_artifacts": {
            "intervention_trial": {
                "activation_counts": {"post_tool": 1},
                "context_changes": [],
                "comparison": {
                    "source": {"status": "completed"},
                    "branch": {"status": "completed"},
                },
            }
        },
        "usage": {"total_tokens": 0},
    }
