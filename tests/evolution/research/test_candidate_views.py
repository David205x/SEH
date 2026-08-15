"""Tests for the Candidate Reviewer evidence views."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from search_harness.evolution.research.candidate_views import (
    render_candidate_case,
    render_candidate_changes,
    render_candidate_harness_diff,
    render_candidate_trajectory_text,
    render_paired_candidate_trajectory,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
    TeacherResources,
)
from search_harness.evolution.research.roles.contracts import CandidateReviewerInput
from search_harness.evolution.research.roles.loader import load_teacher_agent_spec


class CandidateReviewerViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[3]
        cls.source_path = (
            cls.root
            / "runs"
            / "evolution"
            / "20260809_base"
            / "artifacts"
            / "review_candidate-44975b9f03d18331"
            / "role.json"
        )
        cls.source = json.loads(cls.source_path.read_text(encoding="utf-8"))
        cls.resource_config = dict(cls.source["resource_config"])
        candidate_review = dict(cls.resource_config["candidate_review"])
        candidate_review["candidate_template_root"] = str(
            cls.root
            / "runs"
            / "evolution"
            / "20260809_base"
            / "artifacts"
            / "shadow_candidate_inputs"
            / "compile_candidate-3a3f216dd03e3bfe"
            / "template"
        )
        cls.resource_config["candidate_review"] = candidate_review

    def setUp(self) -> None:
        self.resources = TeacherResources.from_config(
            TeacherResourceConfig.model_validate(
                self.resource_config
            )
        )

    def test_template_assembles_and_deduplicates_initial_metrics(self) -> None:
        role_input = CandidateReviewerInput.model_validate(
            self.source["input"]
        )
        self.resources.bind_role_input(role_input)
        spec = load_teacher_agent_spec(
            self.root / "harness_templates" / "teacher" / "candidate_reviewer",
            runtime_context=self.resources,
            role_id="candidate_reviewer",
            role_version=1,
        )
        rendered = spec.prompt.render_input(
            role_input,
            self.resources.model_context("candidate_reviewer"),
        )
        self.assertEqual("CandidateReviewerPrompt", type(spec.prompt).__name__)
        self.assertEqual(
            [
                "list_candidate_changes",
                "get_candidate_case",
                "get_paired_student_trajectory",
                "get_candidate_harness_diff",
                "get_candidate_trajectory_text",
            ],
            [tool.name for tool in spec.tools.tools],
        )
        self.assertEqual(1, rendered.count("answers.accuracy"))
        self.assertNotIn("mean_model_calls", rendered)
        self.assertNotIn("candidate_digest", rendered)

    def test_changed_first_view_omits_unchanged_rows_by_default(self) -> None:
        rendered = render_candidate_changes(
            self.resources.candidate_review,
            page=1,
            page_size=100,
            change="any",
        )
        self.assertIn("selected=17", rendered)
        self.assertIn("| 7 | 10 | 58 |", rendered)
        data_rows = [line for line in rendered.splitlines() if line.startswith("| 5")]
        self.assertFalse(any("| unchanged |" in line for line in data_rows))

    def test_case_pairs_replicates_and_removes_model_calls(self) -> None:
        rendered = render_candidate_case(
            self.resources.candidate_review,
            "5a822d4655429926c1cdae45",
        )
        self.assertIn("Replicate outcome map", rendered)
        self.assertIn("regressed", rendered)
        self.assertIn("Gary Busey", rendered)
        self.assertIn("candidate_hook_activity", rendered)
        self.assertNotIn("model_calls", rendered)
        self.assertNotIn("reasoning_content", rendered)

    def test_paired_trajectory_keeps_effect_and_removes_raw_repetition(self) -> None:
        rendered = render_paired_candidate_trajectory(
            self.resources.candidate_review,
            example_id="5a822d4655429926c1cdae45",
            replicate_id="r000",
        )
        self.assertIn("Hook-effect events", rendered)
        self.assertIn("content appended before entering Student context", rendered)
        self.assertIn("Gary Busey", rendered)
        self.assertNotIn('"event_type":"model_input"', rendered)
        self.assertNotIn("reasoning_content", rendered)
        self.assertNotIn('"results"', rendered)
        self.assertNotIn('"omitted"', rendered)

    def test_exact_text_is_available_by_event_reference(self) -> None:
        rendered = render_candidate_trajectory_text(
            self.resources.candidate_review,
            example_id="5a822d4655429926c1cdae45",
            replicate_id="r000",
            side="candidate",
            event_index=5,
            field="hook_raw_output",
            offset=0,
            max_characters=4000,
        )
        self.assertIn("Candidate Trajectory Exact Text", rendered)
        self.assertIn("hook_raw_output", rendered)
        model_input = render_candidate_trajectory_text(
            self.resources.candidate_review,
            example_id="5a822d4655429926c1cdae45",
            replicate_id="r000",
            side="candidate",
            event_index=5,
            field="hook_model_input",
            offset=0,
            max_characters=4000,
        )
        self.assertIn("hook_model_input", model_input)

    def test_small_harness_diff_is_complete_without_digests(self) -> None:
        rendered = render_candidate_harness_diff(
            self.resources.candidate_review,
            path=None,
        )
        self.assertIn("second_entity_retrieval", rendered)
        self.assertNotIn("candidate_digest", rendered)
        self.assertNotIn("incumbent_digest", rendered)

if __name__ == "__main__":
    unittest.main()
