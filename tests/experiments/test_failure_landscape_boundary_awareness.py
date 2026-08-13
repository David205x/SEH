from __future__ import annotations

import unittest

from experiments.run_failure_landscape_boundary_awareness import (
    _cross_validate_frozen_sources,
    _freeze_landscape,
)


class FailureLandscapeBoundaryAwarenessTests(unittest.TestCase):
    def test_cross_validates_three_frozen_views(self) -> None:
        judgments = [
            {
                "case": {
                    "example_id": "e1",
                    "replicate_id": "r000",
                    "question": "q",
                    "golden_answer": "g",
                    "predicted_answer": "p",
                }
            }
        ]
        evaluation_cases = [
            {
                "example_id": "e1",
                "question": "q",
                "golden_answer": "g",
                "replicates": [
                    {"replicate_id": "r000", "predicted_answer": "p"}
                ],
            }
        ]
        rollouts = [
            {
                "example": {
                    "example_id": "e1",
                    "question": "q",
                    "answer": "g",
                },
                "replicate": {"replicate_id": "r000"},
                "run": {"answer": "p"},
            }
        ]

        result = _cross_validate_frozen_sources(
            judgments=judgments,
            evaluation_cases=evaluation_cases,
            rollouts=rollouts,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["matched_replicate_count"], 1)

    def test_freezes_assignments_and_recomputes_counts(self) -> None:
        cases = [
            {
                "example_id": "e1",
                "failed_rollouts": 3,
                "failure_stability": "stable",
            },
            {
                "example_id": "e2",
                "failed_rollouts": 1,
                "failure_stability": "unstable",
            },
        ]
        parsed = {
            "categories": [
                {
                    "category_id": "C1",
                    "label": "wrong entity",
                    "definition": "The answer names a different entity.",
                    "exclusions": ["Alias wording for the reference entity."],
                }
            ],
            "assignments": [
                {"example_id": "e1", "category_id": "C1"},
                {"example_id": "e2", "category_id": "unknown"},
            ],
            "quality_audit": {},
            "limits": [],
        }

        landscape, validation = _freeze_landscape(cases, parsed)

        self.assertTrue(validation["valid"])
        self.assertEqual(landscape["totals"]["failed_rollouts"], 4)
        self.assertEqual(landscape["categories"][0]["stability"]["stable"], 1)
        self.assertEqual(
            landscape["reserved_assignments"]["unknown"]["example_ids"],
            ["e2"],
        )

    def test_rejects_missing_assignment(self) -> None:
        cases = [
            {
                "example_id": "e1",
                "failed_rollouts": 3,
                "failure_stability": "stable",
            }
        ]

        with self.assertRaisesRegex(ValueError, "do not cover all examples"):
            _freeze_landscape(
                cases,
                {"categories": [], "assignments": []},
            )

    def test_drops_unreferenced_empty_category(self) -> None:
        cases = [
            {
                "example_id": "e1",
                "failed_rollouts": 3,
                "failure_stability": "stable",
            }
        ]
        category = {
            "label": "wrong entity",
            "definition": "The answer names a different entity.",
            "exclusions": ["An alias of the reference entity."],
        }

        landscape, validation = _freeze_landscape(
            cases,
            {
                "categories": [
                    {"category_id": "C1"} | category,
                    {"category_id": "C2"} | category,
                ],
                "assignments": [
                    {"example_id": "e1", "category_id": "C1"}
                ],
            },
        )

        self.assertEqual(len(landscape["categories"]), 1)
        self.assertEqual(validation["dropped_empty_categories"], ["C2"])


if __name__ == "__main__":
    unittest.main()
