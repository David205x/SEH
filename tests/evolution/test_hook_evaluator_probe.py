"""Hook evaluator feasibility probe tests."""

from __future__ import annotations

import unittest

from search_harness.evolution.research.hook_evaluator_probe import (
    HookEvaluatorFixture,
    HookEvaluatorProbeRequest,
    run_hook_evaluator_probe,
)
from search_harness.evolution.research.roles.contracts import (
    MechanismDecisionContract,
)
from search_harness.framework import HookModelRequest, HookModelResponse


class _ScriptedBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)
        self.requests: list[HookModelRequest] = []

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(
            raw_output=next(self.outputs),
            metadata={
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                }
            },
        )


class HookEvaluatorProbeTest(unittest.TestCase):
    def test_bounds_repetitions(self) -> None:
        with self.assertRaises(ValueError):
            HookEvaluatorProbeRequest(
                predicate_ref="pre_final.answer_support",
                decision_contract=_contract(),
                fixtures=(
                    HookEvaluatorFixture("positive", "positive", {}),
                    HookEvaluatorFixture("negative", "negative", {}),
                ),
                repetitions=4,
            )

    def test_requires_positive_negative_and_uncertain_fixtures(self) -> None:
        with self.assertRaises(ValueError):
            HookEvaluatorProbeRequest(
                predicate_ref="pre_final.answer_support",
                decision_contract=_contract(),
                fixtures=(
                    HookEvaluatorFixture("positive", "positive", {}),
                ),
            )

    def test_reports_match_consistency_parse_failures_and_usage(self) -> None:
        backend = _ScriptedBackend(
            [
                '{"label":"positive"}',
                '{"label":"positive"}',
                '{"label":"negative"}',
                '{"label":"uncertain"}',
                '{"label":"uncertain"}',
                "not-json",
            ]
        )
        request = HookEvaluatorProbeRequest(
            predicate_ref="pre_final.answer_support",
            decision_contract=_contract(),
            fixtures=(
                HookEvaluatorFixture(
                    "positive",
                    "positive",
                    {"candidate": "A concrete unsupported answer."},
                ),
                HookEvaluatorFixture(
                    "negative",
                    "negative",
                    {"candidate": "The evidence is insufficient."},
                ),
                HookEvaluatorFixture(
                    "uncertain",
                    "uncertain",
                    {"candidate": "Conflicting support is present."},
                ),
            ),
            repetitions=2,
        )

        summary = run_hook_evaluator_probe(request=request, backend=backend)

        self.assertEqual(len(backend.requests), 6)
        self.assertAlmostEqual(summary.label_match_rate, 4 / 6)
        self.assertEqual(summary.consistent_fixture_count, 1)
        self.assertEqual(summary.parse_failure_count, 1)
        self.assertEqual(summary.usage["total_tokens"], 72)
        self.assertEqual(
            summary.fixture_summaries[1]["observed_label_counts"],
            {"negative": 1, "uncertain": 1},
        )
        self.assertIn(
            "Positive: The input directly satisfies the predicate.",
            backend.requests[0].model_input.messages[0].content,
        )
        self.assertNotIn(
            "expected_label",
            backend.requests[0].model_input.messages[1].content,
        )

    def test_builds_balanced_fixtures_from_decision_evidence(self) -> None:
        request = HookEvaluatorProbeRequest.from_decision_contract(
            predicate_ref="pre_final.answer_support",
            decision_contract=_contract(),
        )

        self.assertEqual(
            [fixture.fixture_id for fixture in request.fixtures],
            ["positive-001", "negative-001", "uncertain-001"],
        )
        self.assertEqual(
            request.fixtures[2].input_payload,
            {"observation": "Evidence is conflicting."},
        )


def _contract() -> MechanismDecisionContract:
    return MechanismDecisionContract(
        predicate="The candidate asserts an unsupported answer.",
        positive_rule="The input directly satisfies the predicate.",
        negative_rule="The input directly contradicts the predicate.",
        uncertain_rule="The available input cannot decide the predicate.",
        output_labels=["positive", "negative", "uncertain"],
        evidence_coverage={
            "positive": ["An unsupported answer is asserted."],
            "negative": ["The candidate explicitly declines to answer."],
            "uncertain": ["Evidence is conflicting."],
        },
    )


if __name__ == "__main__":
    unittest.main()
