"""Shadow Teacher judgment-landscape experiment tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from experiments.run_shadow_judge_landscape import (
    build_classification_corpus,
    build_summary,
    validate_classification,
)
from search_harness.integrations.openai_compatible import OpenAICompatibleConfig


def _judgment(
    ref: str,
    *,
    original_score: int,
    shadow_score: int,
    assessment: str,
) -> dict:
    example_id, replicate_id = ref.split("/", maxsplit=1)
    return {
        "ref": ref,
        "case": {
            "example_id": example_id,
            "replicate_id": replicate_id,
            "question": "Question?",
            "golden_answer": "gold",
            "predicted_answer": "prediction",
        },
        "original": {"score": original_score, "score_source": "teacher"},
        "shadow": {
            "score": shadow_score,
            "assessment": assessment,
            "error": None,
            "metadata": {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                }
            },
        },
        "attempts": [
            {
                "metadata": {
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    }
                }
            }
        ],
    }


class ShadowJudgeLandscapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.judgments = [
            _judgment(
                "a/r000",
                original_score=0,
                shadow_score=0,
                assessment="The prediction names a different entity.",
            ),
            _judgment(
                "b/r000",
                original_score=1,
                shadow_score=1,
                assessment="The prediction is an accepted alias.",
            ),
        ]

    def test_corpus_keeps_all_assessments_and_result_facts(self) -> None:
        corpus = build_classification_corpus(self.judgments)

        self.assertEqual(2, len(corpus))
        self.assertEqual("The prediction names a different entity.", corpus[0]["assessment"])
        self.assertNotIn("metadata", corpus[0])

    def test_classification_requires_every_failure_exactly_once(self) -> None:
        corpus = build_classification_corpus(self.judgments)
        result = {
            "parsed_output": {
                "failure_categories": [{"category_id": "C1"}],
                "failure_assignments": [
                    {"ref": "a/r000", "category_id": "C1"}
                ],
            }
        }

        validation = validate_classification(result, corpus)

        self.assertTrue(validation["valid"])
        self.assertEqual({"C1": 1}, validation["category_counts"])

    def test_summary_aggregates_agreement_text_and_usage(self) -> None:
        corpus = build_classification_corpus(self.judgments)
        summary = build_summary(
            source_path=Path("per_rollout.jsonl"),
            model_config=OpenAICompatibleConfig(
                base_url="https://teacher.invalid",
                model_id="teacher-test",
            ),
            judgments=self.judgments,
            classification=None,
            corpus=corpus,
            classifier_config=OpenAICompatibleConfig(
                base_url="https://teacher.invalid",
                model_id="teacher-test",
                thinking_mode="disabled",
            ),
        )

        self.assertEqual(1.0, summary["score_agreement"]["overall"])
        self.assertEqual(30, summary["judge_api_usage"]["totals"]["total_tokens"])
        self.assertEqual(2, summary["assessment_text"]["unique_count"])


if __name__ == "__main__":
    unittest.main()
