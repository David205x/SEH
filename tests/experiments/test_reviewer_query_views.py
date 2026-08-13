"""Focused tests for shadow Reviewer model-visible views."""

from __future__ import annotations

import unittest
import json
from pathlib import Path

from experiments.teacher_query_views.prompt import ShadowMechanismDistillerPrompt
from experiments.teacher_query_views.views import (
    render_distillation_trial_detail,
    render_evidence_reviewer_input,
    render_mechanism_distiller_input,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
    TeacherResources,
)
from search_harness.evolution.research.roles.contracts import (
    MechanismDistillerInput,
)
from search_harness.evolution.research.roles.loader import load_teacher_agent_spec


class ReviewerQueryViewTest(unittest.TestCase):
    def test_evidence_view_omits_model_call_statistics(self) -> None:
        value = {
            "hypothesis": {"phase_plan": []},
            "trial_reviews": [],
            "coverage_summary": {"phase_coverage": []},
            "budget": {},
            "aggregate_observations": {
                "trial_count": 1,
                "source_full_model_calls": 2,
                "items": [
                    {
                        "trial_ref": "trial_001",
                        "example_id": "e1",
                        "source_full_model_calls": 2,
                    }
                ],
            },
        }
        rendered = render_evidence_reviewer_input(value, {})
        self.assertIn("trial_count", rendered)
        self.assertNotIn("model_calls", rendered)

    def test_distiller_dossier_keeps_exact_mutation_and_removes_raw_runs(self) -> None:
        value = {
            "hypothesis": {"phase_plan": [{"phase": "post_tool"}]},
            "review": {"decision": "ready_to_distill"},
            "trial_reviews": [
                {
                    "trial_ref": "trial_001",
                    "predicate_observations": [
                        {
                            "phase": "post_tool",
                            "predicate_label": "positive",
                            "phase_execution": "intervention_applied",
                        }
                    ],
                    "assessment": "supported",
                }
            ],
            "coverage_summary": {},
            "evidence_refs": ["trial_001"],
            "budget": {},
            "capability_constraints": [],
        }
        trials = {
            "trial_001": {
                "source": {
                    "example_id": "e1",
                    "replicate_id": "r1",
                    "fork_step": 1,
                    "fork_phase": "post_tool",
                    "source_run": {
                        "question": "Which item is missing?",
                        "state": {"model_inputs": ["large raw state"]},
                    },
                },
                "worker_result": {
                    "activated_phases": ["post_tool"],
                    "modified_phases": ["post_tool"],
                },
                "context_changes": [
                    {
                        "scope": "source_boundary",
                        "phase": "post_tool",
                        "action": {
                            "kind": "apply_context_patch",
                            "payload": {
                                "operations": [
                                    {
                                        "operation": "insert",
                                        "content": "Search for the missing item.",
                                    }
                                ]
                            },
                            "reason": "missing evidence",
                        },
                        "model_input_before": {"messages": ["raw"]},
                    }
                ],
                "phase_effects": [
                    {
                        "next_model_decision": {
                            "kind": "tool_call",
                            "tool_name": "search",
                        }
                    }
                ],
                "comparison": {
                    "source": {"execution": {"model_calls": 2, "tool_calls": 1}},
                    "branch": {"score": 1, "execution": {"tool_calls": 1}},
                },
            }
        }
        rendered = render_mechanism_distiller_input(
            value,
            trials,
            {"mechanism_drafts": {"draft_count": 0}},
        )
        self.assertIn("Search for the missing item.", rendered)
        self.assertIn("tool_call", rendered)
        self.assertNotIn("large raw state", rendered)
        self.assertNotIn("model_input_before", rendered)
        self.assertNotIn("model_calls", rendered)

    def test_distiller_detail_is_a_focused_catalog(self) -> None:
        rendered = render_distillation_trial_detail(
            {
                "trial_ref": "trial_001",
                "source": {
                    "selector": {"example_id": "e1"},
                    "run": {"status": "completed", "events": []},
                },
                "branch_run": {"status": "completed", "events": []},
                "context_changes": [],
                "worker_events": [],
                "phase_effects": [],
                "comparison": {},
            }
        )
        self.assertIn("Distillation Trial Detail", rendered)
        self.assertIn("trial_001", rendered)
        self.assertNotIn("omitted", rendered)


class ShadowDistillerAssemblyTest(unittest.TestCase):
    def test_shadow_distiller_assembles_from_saved_artifact(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source_path = (
            root
            / "runs"
            / "evolution"
            / "20260809_base"
            / "artifacts"
            / "distill_mechanism-ddd6d5dc4c4fb458"
            / "role.json"
        )
        source = json.loads(source_path.read_text(encoding="utf-8"))
        resources = TeacherResources.from_config(
            TeacherResourceConfig.model_validate(source["resource_config"])
        )
        spec = load_teacher_agent_spec(
            root
            / "experiments"
            / "teacher_query_views"
            / "templates"
            / "mechanism_distiller",
            runtime_context=resources,
            role_id="mechanism_distiller",
            role_version=1,
        )
        validated = MechanismDistillerInput.model_validate(source["input"])
        resources.bind_role_input(validated)
        rendered = spec.prompt.render_input(
            validated,
            resources.model_context("mechanism_distiller"),
        )
        self.assertIsInstance(spec.prompt, ShadowMechanismDistillerPrompt)
        self.assertIn("Distillation Evidence Dossier", rendered)
        names = [tool.name for tool in spec.tools.tools]
        self.assertIn("get_distillation_trial_detail", names)
        self.assertNotIn("list_trial_evidence", names)
        self.assertNotIn("get_trial_event", names)


if __name__ == "__main__":
    unittest.main()
