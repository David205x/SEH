"""Tests for the shadow Mechanism Distiller A/B runner."""

from __future__ import annotations

import unittest

from experiments.run_distiller_dossier_ab import _comparison, extract_metrics


class DistillerDossierABTest(unittest.TestCase):
    def test_extract_metrics_separates_evidence_and_draft_tools(self) -> None:
        artifact = {
            "output": {"decision": "distilled"},
            "output_contract": {"id": "mechanism_distillation"},
            "tool_calls": [
                {"name": "get_distillation_trial_detail", "content": "detail"},
                {"name": "create_mechanism_draft", "content": "created"},
                {
                    "name": "submit_mechanism_distillation",
                    "content": "submitted",
                },
            ],
            "usage": {
                "requests": 3,
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "calls": [{"prompt_tokens": 30}],
            },
        }
        metrics = extract_metrics(artifact)
        self.assertEqual(1, metrics["evidence_query_calls"])
        self.assertEqual(1, metrics["detail_query_calls"])
        self.assertEqual(1, metrics["draft_tool_calls"])
        self.assertEqual(30, metrics["first_prompt_tokens"])

    def test_comparison_uses_shadow_to_formal_token_ratio(self) -> None:
        aggregate = {
            "formal": {
                "runs": 2,
                "completed": 2,
                "first_submit_passed": 1,
                "means": {"total_tokens": 100},
            },
            "shadow": {
                "runs": 2,
                "completed": 2,
                "first_submit_passed": 2,
                "means": {"total_tokens": 75},
            },
        }
        comparison = _comparison(aggregate)
        self.assertEqual(0.75, comparison["total_token_ratio"])


if __name__ == "__main__":
    unittest.main()
