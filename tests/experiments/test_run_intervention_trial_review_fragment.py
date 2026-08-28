"""Intervention debug-fragment argument tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from experiments.run_intervention_trial_review_fragment import parse_args


class InterventionTrialReviewFragmentArgumentsTest(unittest.TestCase):
    def test_trial_reviews_remain_default(self) -> None:
        args = parse_args(["--run-dir", "runs/debug_fragments/example"])

        self.assertEqual(
            args.run_dir,
            Path("runs/debug_fragments/example"),
        )
        self.assertFalse(args.workers_only)

    def test_can_stop_after_intervention_workers(self) -> None:
        args = parse_args(
            [
                "--run-dir",
                "runs/debug_fragments/example",
                "--workers-only",
            ]
        )

        self.assertTrue(args.workers_only)


if __name__ == "__main__":
    unittest.main()
