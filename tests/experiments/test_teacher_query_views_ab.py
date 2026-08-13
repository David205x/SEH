"""A/B Teacher query-view metric tests."""

from __future__ import annotations

import unittest

from experiments.run_teacher_query_views_ab import (
    _aggregate,
    _comparison,
    extract_metrics,
)


class TeacherQueryViewsABMetricsTest(unittest.TestCase):
    def test_extracts_turn_tool_result_and_retry_costs(self) -> None:
        artifact = {
            "role_budget": {"max_turns": 20},
            "usage": {
                "requests": 5,
                "input_tokens": 1000,
                "output_tokens": 100,
                "total_tokens": 1100,
                "prompt_cache_hit_tokens": 400,
                "prompt_cache_miss_tokens": 600,
            },
            "tool_calls": [
                {
                    "name": "get_student_trajectory",
                    "content": "abc",
                    "metadata": {},
                },
                {
                    "name": "get_trajectory_block",
                    "content": "12345",
                    "metadata": {"error_type": "tool_execution_error"},
                },
                {
                    "name": "submit_failure_direction",
                    "content": "invalid",
                    "metadata": {"error_type": "validation"},
                },
                {
                    "name": "submit_failure_direction",
                    "content": "accepted",
                    "metadata": {},
                },
            ],
        }

        metrics = extract_metrics(artifact)

        self.assertEqual(5, metrics["model_turns"])
        self.assertEqual(2, metrics["query_tool_calls"])
        self.assertEqual(8, metrics["tool_result_characters"])
        self.assertEqual(2, metrics["terminal_submit_calls"])
        self.assertEqual(1, metrics["terminal_retries"])
        self.assertEqual(1, metrics["tool_errors"])

    def test_aggregate_compares_shadow_against_formal(self) -> None:
        formal = _aggregate(
            [
                {
                    "status": "completed",
                    "model_turns": 4,
                    "query_tool_calls": 3,
                    "terminal_submit_calls": 1,
                    "terminal_retries": 0,
                    "tool_errors": 0,
                    "tool_result_characters": 1000,
                    "input_tokens": 2000,
                    "output_tokens": 200,
                    "total_tokens": 2200,
                    "cache_hit_tokens": 0,
                    "cache_miss_tokens": 2000,
                }
            ]
        )
        shadow = _aggregate(
            [
                {
                    "status": "completed",
                    "model_turns": 5,
                    "query_tool_calls": 5,
                    "terminal_submit_calls": 1,
                    "terminal_retries": 0,
                    "tool_errors": 0,
                    "tool_result_characters": 400,
                    "input_tokens": 1200,
                    "output_tokens": 250,
                    "total_tokens": 1450,
                    "cache_hit_tokens": 0,
                    "cache_miss_tokens": 1200,
                }
            ]
        )

        comparison = _comparison({"formal": formal, "shadow": shadow})

        self.assertEqual(2, comparison["query_tool_calls"]["shadow_minus_formal"])
        self.assertEqual(
            0.4,
            comparison["tool_result_characters"]["shadow_to_formal_ratio"],
        )
        self.assertEqual(
            0.6591,
            comparison["total_tokens"]["shadow_to_formal_ratio"],
        )


if __name__ == "__main__":
    unittest.main()
