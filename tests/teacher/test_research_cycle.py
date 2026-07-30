"""Standalone Researcher revision cycle tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from search_harness.teacher.research_cycle import (
    InterventionAssignment,
    ResearchRevisionCycle,
)
from search_harness.teacher.role_resources import InterventionResourceConfig


class StubRuntime:
    """Return fixed artifacts and record continuation feedback."""

    def __init__(
        self,
        *,
        run_artifact: dict[str, Any] | None = None,
        run_artifacts: list[dict[str, Any]] | None = None,
        revision_artifact: dict[str, Any] | None = None,
    ) -> None:
        self.run_artifact = run_artifact
        self.run_artifacts = list(run_artifacts or [])
        self.revision_artifact = revision_artifact
        self.run_calls: list[dict[str, Any]] = []
        self.continuation_calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        self.run_calls.append(kwargs)
        if self.run_artifacts:
            return self.run_artifacts.pop(0)
        if self.run_artifact is None:
            raise AssertionError("unexpected role run")
        return self.run_artifact

    async def continue_researcher(self, **kwargs: Any) -> dict[str, Any]:
        self.continuation_calls.append(kwargs)
        if self.revision_artifact is None:
            raise AssertionError("unexpected Researcher continuation")
        return self.revision_artifact

class ResearchRevisionCycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_continue_review_adds_trial_before_researcher_revision(
        self,
    ) -> None:
        """验证两条 trial 先独立审阅，再由一次总评恢复 Researcher。"""

        worker = StubRuntime(run_artifact=_worker_artifact("executed"))
        reviewer = StubRuntime(
            run_artifacts=[
                _trial_review_artifact(
                    "trial_001",
                    "The first trial followed the hypothesis.",
                ),
                _trial_review_artifact(
                    "trial_002",
                    "The second trial did not reproduce the effect.",
                ),
                _evidence_review_artifact("revise"),
            ],
        )
        researcher = StubRuntime(
            revision_artifact={"output": _hypothesis("Narrowed action.")}
        )
        cycle = ResearchRevisionCycle(
            researcher_runtime=researcher,  # type: ignore[arg-type]
            worker_runtime=worker,  # type: ignore[arg-type]
            reviewer_runtime=reviewer,  # type: ignore[arg-type]
        )

        with tempfile.TemporaryDirectory() as directory:
            outcome = await cycle.run_many(
                researcher_artifact={"output": _hypothesis("Initial action.")},
                assignments=[_assignment(), _assignment()],
                intervention_config=_intervention_config(),
                run_dir=Path(directory),
            )

        self.assertEqual(outcome.status, "hypothesis_revised_after_review")
        self.assertEqual(len(outcome.worker_artifacts), 2)
        self.assertEqual(len(outcome.trial_reviewer_artifacts), 2)
        self.assertEqual(len(outcome.reviewer_artifacts), 1)
        self.assertEqual(len(reviewer.run_calls), 3)
        self.assertEqual(
            reviewer.run_calls[2]["role_input"][
                "aggregate_observations"
            ]["trial_count"],
            2,
        )
        aggregate = reviewer.run_calls[2]["role_input"][
            "aggregate_observations"
        ]
        self.assertEqual(aggregate["source_full_tool_calls"], 2)
        self.assertEqual(aggregate["branch_continuation_tool_calls"], 4)
        self.assertEqual(aggregate["fully_activated_plan_count"], 2)
        self.assertEqual(aggregate["fully_modified_plan_count"], 2)
        self.assertEqual(
            aggregate["phase_activation_counts"],
            {"post_tool": 2},
        )
        self.assertEqual(
            aggregate["phase_modification_counts"],
            {"post_tool": 2},
        )
        self.assertEqual(
            len(researcher.continuation_calls[0]["trial_files"]),
            2,
        )

    async def test_review_revision_returns_to_same_researcher(self) -> None:
        """验证正常 Worker 证据经 Reviewer revise 后原样恢复 Researcher。"""

        worker = StubRuntime(run_artifact=_worker_artifact("executed"))
        reviewer = StubRuntime(
            run_artifacts=[
                _trial_review_artifact(
                    "trial_001",
                    "The intended process response did not occur.",
                ),
                _evidence_review_artifact("revise"),
            ]
        )
        researcher = StubRuntime(
            revision_artifact={"output": _hypothesis("Revised action.")}
        )
        cycle = ResearchRevisionCycle(
            researcher_runtime=researcher,  # type: ignore[arg-type]
            worker_runtime=worker,  # type: ignore[arg-type]
            reviewer_runtime=reviewer,  # type: ignore[arg-type]
        )

        with tempfile.TemporaryDirectory() as directory:
            outcome = await cycle.run(
                researcher_artifact={"output": _hypothesis("Initial action.")},
                assignment=_assignment(),
                intervention_config=_intervention_config(),
                run_dir=Path(directory),
            )

            self.assertTrue((Path(directory) / "cycle.json").is_file())
            self.assertTrue(outcome.worker_artifact.is_file())
            self.assertTrue(outcome.reviewer_artifact.is_file())
            self.assertTrue(outcome.researcher_revision_artifact.is_file())

        self.assertEqual(
            outcome.status,
            "hypothesis_revised_after_review",
        )
        self.assertEqual(
            researcher.continuation_calls[0]["feedback_source"],
            "evidence_reviewer",
        )
        self.assertEqual(
            researcher.continuation_calls[0]["feedback"]["decision"],
            "revise",
        )
        trial_reviewer_input = reviewer.run_calls[0]["role_input"]
        self.assertEqual(trial_reviewer_input["trial_ref"], "trial_001")
        reviewer_input = reviewer.run_calls[1]["role_input"]
        self.assertEqual(
            reviewer_input["trial_reviews"][0]["trial_ref"],
            "trial_001",
        )

    async def test_unsupported_hypothesis_skips_reviewer(self) -> None:
        """验证能力不支持的 Worker 结果直接恢复 Researcher。"""

        worker = StubRuntime(
            run_artifact=_worker_artifact("unsupported_hypothesis")
        )
        reviewer = StubRuntime()
        researcher = StubRuntime(
            revision_artifact={"output": _hypothesis("Supported action.")}
        )
        cycle = ResearchRevisionCycle(
            researcher_runtime=researcher,  # type: ignore[arg-type]
            worker_runtime=worker,  # type: ignore[arg-type]
            reviewer_runtime=reviewer,  # type: ignore[arg-type]
        )

        with tempfile.TemporaryDirectory() as directory:
            outcome = await cycle.run(
                researcher_artifact={"output": _hypothesis("Invalid action.")},
                assignment=_assignment(),
                intervention_config=_intervention_config(),
                run_dir=Path(directory),
            )

        self.assertEqual(
            outcome.status,
            "hypothesis_revised_after_worker",
        )
        self.assertFalse(reviewer.run_calls)
        self.assertEqual(
            researcher.continuation_calls[0]["feedback_source"],
            "intervention_worker",
        )

    async def test_unsuitable_assignment_returns_to_controller(self) -> None:
        """验证单个 prefix 不匹配只请求重新分配而不修改假设。"""

        worker = StubRuntime(
            run_artifact=_worker_artifact("unsuitable_assignment")
        )
        reviewer = StubRuntime()
        researcher = StubRuntime()
        cycle = ResearchRevisionCycle(
            researcher_runtime=researcher,  # type: ignore[arg-type]
            worker_runtime=worker,  # type: ignore[arg-type]
            reviewer_runtime=reviewer,  # type: ignore[arg-type]
        )

        with tempfile.TemporaryDirectory() as directory:
            outcome = await cycle.run(
                researcher_artifact={"output": _hypothesis("Valid action.")},
                assignment=_assignment(),
                intervention_config=_intervention_config(),
                run_dir=Path(directory),
            )

        self.assertEqual(outcome.status, "assignment_retry_required")
        self.assertFalse(reviewer.run_calls)
        self.assertFalse(researcher.continuation_calls)


def _hypothesis(intervention: str) -> dict[str, Any]:
    return {
        "fork_phase": "post_tool",
        "phase_plan": [
            {
                "phase": "post_tool",
                "activation_condition": (
                    "The visible result contains partial evidence."
                ),
                "instruction": intervention,
                "expected_effect": (
                    "The Actor performs another search."
                ),
                "max_activations": 1,
            }
        ],
        "evaluation": {
            "primary_signal": "next_output_kind",
            "success_condition": "The next output is a tool call.",
            "falsifier": "The next output is a final answer.",
            "secondary_metrics": [],
        },
        "applicability": "Multi-hop cases with partial evidence.",
    }


def _worker_artifact(result_kind: str) -> dict[str, Any]:
    action_kind = (
        "append_context_message"
        if result_kind == "executed"
        else "continue_without_change"
    )
    modified_phases = (
        ["post_tool"] if result_kind == "executed" else []
    )
    return {
        "input": {"trial_objective": "Test the frozen hypothesis."},
        "output": {
            "result_kind": result_kind,
            "activated_phases": ["post_tool"],
            "modified_phases": modified_phases,
            "unmet_phases": [],
        },
        "resource_artifacts": {
            "intervention_trial": {
                "source": {},
                "phase_plan": [
                    {
                        "phase": "post_tool",
                        "activation_condition": "Partial evidence is visible.",
                        "instruction": "Review the evidence gap.",
                        "expected_effect": "The Actor continues retrieval.",
                        "max_activations": 1,
                    }
                ],
                "activation_counts": {"post_tool": 1},
                "context_changes": [
                    {
                        "phase": "post_tool",
                        "action": {"kind": action_kind},
                    }
                ],
                "branch_run": {"status": "completed", "trace": []},
                "comparison": {
                    "source": {
                        "status": "completed",
                        "answer": "source",
                        "execution": {
                            "model_calls": 2,
                            "tool_calls": 1,
                        },
                    },
                    "branch": {
                        "status": "completed",
                        "answer": "branch",
                        "execution": {
                            "model_calls": 3,
                            "tool_calls": 2,
                        },
                    },
                },
            }
        },
    }


def _trial_review_artifact(
    trial_ref: str,
    assessment: str,
) -> dict[str, Any]:
    return {
        "output": {
            "trial_ref": trial_ref,
            "assessment": assessment,
        }
    }


def _evidence_review_artifact(decision: str) -> dict[str, Any]:
    return {
        "output": {
            "decision": decision,
            "phase_findings": [
                {
                    "phase": "post_tool",
                    "status": "unsupported",
                    "assessment": "The effect was not consistent.",
                }
            ],
            "assessment": "The hypothesis needs revision.",
            "key_risk": "The mechanism is inconsistent.",
            "next_obligation": (
                "Narrow the trigger." if decision == "continue" else None
            ),
        }
    }


def _assignment() -> InterventionAssignment:
    return InterventionAssignment(
        trial_objective="Test one action.",
        example_id="example_1",
        replicate_id="r000",
        prefix_id=5,
    )


def _intervention_config() -> InterventionResourceConfig:
    return InterventionResourceConfig(
        rollout_file=Path("rollouts.jsonl"),
        actor_plugins_root=Path("plugins"),
    )


if __name__ == "__main__":
    unittest.main()
