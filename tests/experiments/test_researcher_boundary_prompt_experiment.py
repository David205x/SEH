from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.run_researcher_boundary_prompt_experiment import (
    _tree_digest,
    _validate_semantic_quotes,
    detect_future_fact_risk,
    select_first_compatible_prefix,
    validate_semantic_review,
    worker_config_with_thinking,
)
from search_harness.integrations.openai_compatible import OpenAICompatibleConfig


class ResearcherBoundaryPromptExperimentTests(unittest.TestCase):
    def test_automatic_scorer_surface_is_removed(self) -> None:
        source = Path(
            "experiments/run_researcher_boundary_prompt_experiment.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("score-researcher", source)
        self.assertNotIn("_AUTO_REVIEW_PROMPT", source)
        self.assertNotIn("automatic_review.json", source)

    def test_repair_prompt_meets_static_character_target(self) -> None:
        baseline = Path(
            "runs/experiments/researcher_boundary_prompt/20260813_023954/"
            "templates/boundary/hypothesis_researcher/prompt/system.md"
        ).read_text(encoding="utf-8")
        repair = Path(
            "experiments/teacher_query_views/templates/"
            "hypothesis_researcher/prompt/system.md"
        ).read_text(encoding="utf-8")

        self.assertLessEqual(len(repair), len(baseline) * 0.8)
        self.assertIn("zero/absent", repair)
        self.assertIn("caveated analog", repair)

    def test_semantic_review_missing_quote_fails_fast(self) -> None:
        criteria = {
            name: {
                "score": 1,
                "failure_quote": "confirmed fact",
                "hypothesis_quote": "preserved fact",
                "reason": "aligned",
            }
            for name in (
                "minimum_failure_predicate_preserved",
                "temporal_observability",
                "claim_phase_alignment",
                "neighbor_falsifiability",
                "worker_semantics",
                "scope_discipline",
            )
        }
        reviews = []
        for index in range(1, 19):
            reviews.append(
                {
                    "anonymous_id": f"A{index:02d}",
                    "criteria": json.loads(json.dumps(criteria)),
                    "total": 6,
                    "protocol_legal": True,
                    "case_leakage": False,
                    "preventive_claim_explicit": False,
                    "recovery_obligation_present": False,
                }
            )
        del reviews[0]["criteria"]["scope_discipline"]["failure_quote"]

        with self.assertRaises(TypeError):
            validate_semantic_review({"reviews": reviews})

    def test_semantic_review_quote_must_exist_in_anonymous_packet(self) -> None:
        experiment_root = Path("runs/experiments")
        experiment_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=experiment_root) as directory:
            root = Path(directory)
            review_dir = root / "researcher_review"
            review_dir.mkdir()
            packet = {
                "handoffs": [
                    {
                        "anonymous_id": "A01",
                        "failure_direction": {"pattern": "exact failure"},
                        "hypothesis": {"applicability": "exact hypothesis"},
                    }
                ]
            }
            (review_dir / "anonymous_packet.json").write_text(
                json.dumps(packet), encoding="utf-8"
            )
            criteria = {
                name: {
                    "score": 1,
                    "failure_quote": "not in packet",
                    "hypothesis_quote": "exact hypothesis",
                    "reason": "test",
                }
                for name in (
                    "minimum_failure_predicate_preserved",
                    "temporal_observability",
                    "claim_phase_alignment",
                    "neighbor_falsifiability",
                    "worker_semantics",
                    "scope_discipline",
                )
            }

            with self.assertRaisesRegex(ValueError, "failure quote is not exact"):
                _validate_semantic_quotes(
                    root,
                    {"reviews": [{"anonymous_id": "A01", "criteria": criteria}]},
                )
    def test_flags_post_tool_future_behavior(self) -> None:
        hypothesis = {
            "phase_plan": [
                {
                    "phase": "post_tool",
                    "activation_condition": (
                        "The first result covers one entity and the Student "
                        "will not search for the second entity."
                    ),
                }
            ]
        }

        self.assertEqual(1, len(detect_future_fact_risk(hypothesis)))

    def test_does_not_flag_phase_visible_history(self) -> None:
        hypothesis = {
            "phase_plan": [
                {
                    "phase": "post_tool",
                    "activation_condition": (
                        "Exactly one completed search is visible so far and "
                        "its result covers one entity."
                    ),
                }
            ]
        }

        self.assertEqual([], detect_future_fact_risk(hypothesis))

    def test_selects_first_compatible_prefix_deterministically(self) -> None:
        timeline = [
            {"prefix_id": 9, "phase": "post_tool"},
            {"prefix_id": 3, "phase": "post_tool"},
            {"prefix_id": 7, "phase": "pre_final"},
        ]

        self.assertEqual(3, select_first_compatible_prefix(timeline, "post_tool"))
        self.assertEqual(7, select_first_compatible_prefix(timeline, "pre_final"))
        self.assertIsNone(select_first_compatible_prefix(timeline, "pre_tool"))

    def test_worker_override_changes_only_thinking_mode(self) -> None:
        base = OpenAICompatibleConfig(
            base_url="https://api.deepseek.com",
            model_id="deepseek-v4-flash",
            api_key="secret",
            max_tokens=123,
            timeout=45,
            temperature=0.2,
            seed=91,
            thinking_mode="enabled",
        )

        disabled = worker_config_with_thinking(base, "disabled")

        self.assertEqual("disabled", disabled.thinking_mode)
        self.assertEqual(
            {**base.__dict__, "thinking_mode": "disabled"},
            disabled.__dict__,
        )

    def test_tree_digest_ignores_bytecode_and_detects_prompt_change(self) -> None:
        experiment_root = Path("runs/experiments")
        experiment_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=experiment_root) as directory:
            root = Path(directory)
            (root / "prompt").mkdir()
            prompt = root / "prompt" / "system.md"
            prompt.write_text("control", encoding="utf-8")
            before = _tree_digest(root)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "component.pyc").write_bytes(b"ignored")
            self.assertEqual(before, _tree_digest(root))
            prompt.write_text("boundary", encoding="utf-8")
            self.assertNotEqual(before, _tree_digest(root))

    def test_replicates_do_not_count_as_distinct_examples(self) -> None:
        assignments = [
            {"example_id": "e1", "replicate_id": "r000"},
            {"example_id": "e1", "replicate_id": "r001"},
            {"example_id": "e2", "replicate_id": "r000"},
        ]

        example_count = len({item["example_id"] for item in assignments})
        replicate_count = len(
            {
                (item["example_id"], item["replicate_id"])
                for item in assignments
            }
        )

        self.assertEqual(2, example_count)
        self.assertEqual(3, replicate_count)


if __name__ == "__main__":
    unittest.main()
