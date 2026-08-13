"""Intervention Trial evidence aggregation tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from search_harness.evolution.research.evidence import (
    aggregate_trial_observations,
    summarize_evidence_coverage,
)
from search_harness.evolution.research.roles.contracts import (
    InterventionHypothesis,
    TrialReview,
)


class TrialEvidenceTest(unittest.TestCase):
    def test_aggregates_persisted_trial_observations(self) -> None:
        aggregate = aggregate_trial_observations(
            [_trial_artifact(), _trial_artifact()],
            [
                Path("trial_001/intervention.json"),
                Path("trial_002/intervention.json"),
            ],
        )

        self.assertEqual(aggregate["trial_count"], 2)
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
            [item["trial_ref"] for item in aggregate["items"]],
            ["trial_001", "trial_002"],
        )

    def test_rejects_mismatched_artifact_and_path_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "counts must match"):
            aggregate_trial_observations([_trial_artifact()], [])

    def test_summarizes_cross_case_phase_coverage(self) -> None:
        """验证跨案例与逐 phase 正负标签由程序统一计数。"""

        hypothesis = _hypothesis()
        artifacts = [
            _trial_artifact(example_id="example_1"),
            _trial_artifact(example_id="example_2"),
            _trial_artifact(example_id="example_4"),
            _trial_artifact(example_id="example_3"),
        ]
        reviews = [
            _trial_review("trial_001", "positive", "intervention_applied"),
            _trial_review("trial_002", "positive", "intervention_applied"),
            _trial_review(
                "trial_003", "negative", "correct_non_intervention"
            ),
            _trial_review(
                "trial_004", "negative", "correct_non_intervention"
            ),
        ]

        summary = summarize_evidence_coverage(
            hypothesis,
            artifacts,
            reviews,
        )

        self.assertTrue(summary.default_requirements_met)
        self.assertEqual(summary.observed_distinct_examples, 4)
        self.assertEqual(summary.phase_coverage[0].positive_count, 2)
        self.assertEqual(summary.phase_coverage[0].negative_count, 2)
        self.assertEqual(
            summary.phase_coverage[0].negative_distinct_examples,
            2,
        )

    def test_reports_each_unmet_default_requirement(self) -> None:
        """验证单案例正例不会被误报为足够蒸馏证据。"""

        summary = summarize_evidence_coverage(
            _hypothesis(),
            [_trial_artifact(example_id="example_1")],
            [_trial_review("trial_001", "positive", "intervention_applied")],
        )

        self.assertFalse(summary.default_requirements_met)
        self.assertEqual(len(summary.unmet_requirements), 3)


def _hypothesis() -> InterventionHypothesis:
    return InterventionHypothesis.model_validate(
        {
            "fork_phase": "post_tool",
            "phase_plan": [
                {
                    "phase": "post_tool",
                    "activation_condition": "The required fact is absent.",
                    "instruction": "Ask the Student to search once more.",
                    "expected_effect": "The Student searches again.",
                    "max_activations": 1,
                }
            ],
            "evaluation": {
                "primary_signal": "next_action",
                "success_condition": "The next action is a search.",
                "falsifier": "The next action is a final answer.",
            },
            "applicability": "Retrieval tasks with missing evidence.",
        }
    )


def _trial_review(
    trial_ref: str,
    label: str,
    execution: str,
) -> TrialReview:
    return TrialReview.model_validate(
        {
            "trial_ref": trial_ref,
            "predicate_observations": [
                {
                    "phase": "post_tool",
                    "predicate_label": label,
                    "decisive_observation": "The visible evidence decides it.",
                    "phase_execution": execution,
                    "observed_effect": "The next action was observed.",
                    "outcome_evidence": None,
                }
            ],
            "assessment": "The phase behavior was reviewed.",
        }
    )


def _trial_artifact(example_id: str = "example_1") -> dict[str, object]:
    return {
        "input": {"example_id": example_id},
        "output": {
            "result_kind": "executed",
            "activated_phases": ["post_tool"],
            "modified_phases": ["post_tool"],
            "unmet_phases": [],
        },
        "resource_artifacts": {
            "intervention_trial": {
                "activation_counts": {"post_tool": 1},
                "context_changes": [
                    {
                        "phase": "post_tool",
                        "action": {"kind": "append_context_message"},
                    }
                ],
                "comparison": {
                    "source": {
                        "status": "completed",
                        "answer": "source",
                        "execution": {"model_calls": 2, "tool_calls": 1},
                    },
                    "branch": {
                        "status": "completed",
                        "answer": "branch",
                        "execution": {"model_calls": 3, "tool_calls": 2},
                    },
                },
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
