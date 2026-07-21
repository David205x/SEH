from __future__ import annotations

import unittest

from search_harness.adapter.critic import CriticResult, CriticReview


class CriticResultTest(unittest.TestCase):
    def test_defaults_represent_analysis_without_follow_up(self) -> None:
        """Verifies the defaults represent analysis without follow up contract."""
        result = CriticResult(analysis="No stable Harness issue was found.")

        self.assertEqual(result.problem_directions, ())
        self.assertEqual(result.evidence_requests, ())
        self.assertEqual(
            result.to_dict(),
            {
                "analysis": "No stable Harness issue was found.",
                "problem_directions": [],
                "evidence_requests": [],
                "review": None,
            },
        )

    def test_parses_candidate_review_decision(self) -> None:
        """验证候选评审结论具有严格的 accept/reject 契约。"""
        result = CriticResult.from_dict(
            {
                "analysis": "The candidate has supported gains.",
                "problem_directions": [],
                "evidence_requests": [],
                "review": {"decision": "accept", "reason": "Net gains are attributable."},
            }
        )

        self.assertEqual(
            result.review,
            CriticReview(decision="accept", reason="Net gains are attributable."),
        )

    def test_serializes_problem_directions_and_evidence_requests(self) -> None:
        """验证问题方向与补充证据请求可稳定序列化。"""
        result = CriticResult(
            analysis="A repeated behavior may need a Hook.",
            problem_directions=(
                {
                    "problem": "Premature answers",
                    "observed_pattern": "Answers repeatedly stop early.",
                    "excluded_causes": [],
                    "desired_behavior": "Continue gathering evidence.",
                    "success_criteria": ["More evidence-complete answers."],
                    "constraints": [],
                },
            ),
            evidence_requests=("Run more Actor-only rollouts.",),
        )

        payload = result.to_dict()

        self.assertEqual(
            payload["problem_directions"],
            [
                {
                    "problem": "Premature answers",
                    "observed_pattern": "Answers repeatedly stop early.",
                    "excluded_causes": [],
                    "desired_behavior": "Continue gathering evidence.",
                    "success_criteria": ["More evidence-complete answers."],
                    "constraints": [],
                }
            ],
        )
        self.assertEqual(
            payload["evidence_requests"],
            ["Run more Actor-only rollouts."],
        )

    def test_rejects_missing_and_unknown_result_fields(self) -> None:
        """验证结构化结果不再用默认值掩盖缺字段或接受未知字段。"""

        with self.assertRaisesRegex(ValueError, "review"):
            CriticResult.from_dict(
                {
                    "analysis": "General issue.",
                    "problem_directions": [],
                    "evidence_requests": [],
                }
            )
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            CriticResult.from_dict(
                {
                    "analysis": "General issue.",
                    "problem_directions": [],
                    "evidence_requests": [],
                    "review": None,
                    "future_field": 1,
                }
            )


if __name__ == "__main__":
    unittest.main()
