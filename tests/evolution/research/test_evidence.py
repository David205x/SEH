"""Intervention Trial evidence aggregation tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from search_harness.evolution.research.evidence import (
    aggregate_trial_observations,
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


def _trial_artifact() -> dict[str, object]:
    return {
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
