"""Tests for Research Direction lineage identifiers."""

from __future__ import annotations

import unittest

from search_harness.evolution.identifiers import (
    make_failure_direction_id,
    make_mechanism_scheme_id,
    make_research_scheme_id,
)


class ResearchDirectionIdentifierTest(unittest.TestCase):
    def test_builds_three_layer_direction_identity(self) -> None:
        failure = make_failure_direction_id("run_1_g0001", 2)
        research = make_research_scheme_id(failure, 3)
        mechanism = make_mechanism_scheme_id(research)

        self.assertEqual(failure, "run_1_g0001_fd0002")
        self.assertEqual(research, "run_1_g0001_fd0002_rs0003")
        self.assertEqual(mechanism, "run_1_g0001_fd0002_rs0003_ms")

    def test_rejects_non_positive_indexes(self) -> None:
        with self.assertRaises(ValueError):
            make_failure_direction_id("run_1_g0001", 0)
        with self.assertRaises(ValueError):
            make_research_scheme_id("run_1_g0001_fd0001", 0)


if __name__ == "__main__":
    unittest.main()
