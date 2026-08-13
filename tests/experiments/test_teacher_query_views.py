"""Shadow Teacher query-view projection tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from experiments.teacher_query_views.judge import _parse_judgment
from experiments.teacher_query_views.intervention import (
    _shadow_activation_tools,
)
from experiments.teacher_query_views.views import (
    ShadowTrajectoryView,
    render_evaluation_case,
    render_student_behavior_interface,
    render_student_capability_view,
)
from search_harness.evolution.research.intervention.worker import (
    _ActivationState,
)
from search_harness.evolution.research.resources.base import (
    EvaluationEvidenceStore,
    TeacherResources,
)
from search_harness.evolution.research.roles.loader import (
    load_teacher_agent_spec,
)


class EvaluationCaseViewTest(unittest.TestCase):
    def test_compact_case_keeps_required_facts_only(self) -> None:
        case = {
            "example_id": "case-1",
            "question": "Which answer?",
            "stability": "stable_failure",
            "success_rate": 0.0,
            "answer_consistency": 1.0,
            "run_status": "completed",
            "replicates": [
                {
                    "replicate_id": "r000",
                    "score": 0,
                    "score_source": "teacher",
                    "predicted_answer": "wrong",
                    "run_status": "completed",
                    "runner_error": None,
                    "teacher": {
                        "score": 0,
                        "assessment": "The answer identifies a different entity.",
                        "raw_output": "private raw output",
                        "metadata": {"reasoning_content": "private reasoning"},
                    },
                    "execution": {
                        "steps": 2,
                        "model_calls": 2,
                        "tool_calls": 1,
                        "retriever_errors": 0,
                        "duplicate_queries": 0,
                        "tokens": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "total_tokens": 120,
                        },
                    },
                }
            ],
        }

        rendered = render_evaluation_case(case)

        self.assertIn("The answer identifies a different entity.", rendered)
        self.assertIn("input_tokens", rendered)
        self.assertIn("student_total_tokens", rendered)
        self.assertIn("n/a", rendered)
        self.assertIn("score` is the verdict", rendered)
        self.assertNotIn("private raw output", rendered)
        self.assertNotIn("private reasoning", rendered)
        self.assertNotIn("model_calls", rendered)


class TrajectoryViewTest(unittest.TestCase):
    def setUp(self) -> None:
        original = "original retrieved passage"
        effective = "rewritten retrieved passage"
        self.record = {
            "example": {"example_id": "case-1", "question": "Question?"},
            "replicate": {"replicate_id": "r000"},
            "run": {
                "status": "completed",
                "answer": "answer",
                "error": None,
                "trace": [
                    {
                        "index": 1,
                        "step": 1,
                        "event_type": "model_input",
                        "payload": {
                            "messages": [
                                {"role": "system", "content": "system"},
                                {"role": "user", "content": "Question?"},
                            ]
                        },
                    },
                    {
                        "index": 2,
                        "step": 1,
                        "event_type": "hook_model_output",
                        "payload": {
                            "hook_id": "rewrite",
                            "phase": "post_tool",
                            "purpose": "rewrite evidence",
                            "model_input": {"messages": ["large duplicate"]},
                            "raw_output": '{"decision":"positive"}',
                            "metadata": {"usage": {"total_tokens": 10}},
                        },
                    },
                    {
                        "index": 3,
                        "step": 1,
                        "event_type": "hook_applied",
                        "payload": {
                            "hook_id": "rewrite",
                            "phase": "post_tool",
                            "changes": [
                                {
                                    "key": "stage.tool_result",
                                    "before": {
                                        "name": "search",
                                        "content": original,
                                        "metadata": {"results": [original]},
                                    },
                                    "after": {
                                        "name": "search",
                                        "content": effective,
                                        "metadata": {"results": [original]},
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "index": 4,
                        "step": 1,
                        "event_type": "tool_result",
                        "payload": {
                            "name": "search",
                            "content": effective,
                            "metadata": {"results": [original]},
                        },
                    },
                    {
                        "index": 5,
                        "step": 2,
                        "event_type": "model_input",
                        "payload": {
                            "messages": [
                                {"role": "system", "content": "system"},
                                {"role": "user", "content": "Question?"},
                                {"role": "assistant", "content": "search"},
                                {"role": "user", "content": effective},
                            ]
                        },
                    },
                ],
            },
        }

    def test_view_separates_source_from_effective_content(self) -> None:
        view = ShadowTrajectoryView(self.record)

        rendered = view.render()

        self.assertIn('"delivery_status":"verified"', rendered)
        self.assertIn("STUDENT_VISIBLE", rendered)
        self.assertIn("RUNTIME_ONLY", rendered)
        self.assertNotIn('"omitted"', rendered)
        self.assertNotIn('"results"', rendered)
        self.assertNotIn("large duplicate", rendered)

        change = view.render_change("change_001")
        self.assertIn("source_refs", change)
        self.assertIn("effective_refs", change)

        source_matches = view.search_runtime_blocks(
            "original retrieved",
            max_matches=3,
        )
        self.assertIn("original retrieved passage", source_matches)

    def test_exact_block_can_be_read_by_reference(self) -> None:
        view = ShadowTrajectoryView(self.record)

        rendered = view.read_block(
            block_id=4,
            revision=1,
            offset=0,
            max_characters=100,
        )

        self.assertIn("rewritten retrieved passage", rendered)
        self.assertIn("STUDENT_VISIBLE", rendered)


class StudentInterfaceViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {
            "harness_id": "student-v1",
            "tools": [{"instance_id": "search"}],
            "prompt": {"instance_id": "prompt"},
            "output": {"instance_id": "tagged_output"},
            "extensions": [
                {
                    "instance_id": "rewrite",
                    "config": {
                        "phase": "post_tool",
                        "purpose": "rewrite retrieved evidence",
                    },
                }
            ],
        }
        self.record = {
            "run": {
                "trace": [
                    {
                        "event_type": "model_input",
                        "payload": {
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "Available tools:\n"
                                        "- `search`: Retrieve evidence.\n"
                                        "<tool_call>{}</tool_call>\n"
                                        "<final_answer>x</final_answer>"
                                    ),
                                },
                                {"role": "user", "content": "Question?"},
                            ]
                        },
                    }
                ]
            }
        }

    def test_capability_view_excludes_manifest_assembly_details(self) -> None:
        rendered = render_student_capability_view(
            manifest=self.manifest,
            records=[self.record],
        )

        self.assertIn("Retrieve evidence.", rendered)
        self.assertIn("post_tool", rendered)
        self.assertNotIn("entrypoint", rendered)

    def test_behavior_interface_contains_exact_model_visible_prompt(self) -> None:
        rendered = render_student_behavior_interface(
            manifest=self.manifest,
            record=self.record,
        )

        self.assertIn("Exact Model-visible Prompt", rendered)
        self.assertIn("<tool_call>{}</tool_call>", rendered)
        self.assertIn("rewrite retrieved evidence", rendered)
        self.assertNotIn("tool_call, value", rendered)


class InterventionQueryViewTest(unittest.TestCase):
    def test_shadow_views_remove_duplicate_observation_and_json_escaping(self) -> None:
        activation = _ActivationState(
            {
                "editable_context": [
                    {
                        "block_id": 1,
                        "kind": "message",
                        "role": "user",
                        "characters": 11,
                        "summary": "line 1 line 2",
                    }
                ],
                "_editable_context_blocks": [
                    {
                        "block_id": 1,
                        "kind": "message",
                        "role": "user",
                        "content": "line 1\nline 2",
                    }
                ],
                "source_boundary": True,
                "current_phase": "post_prompt",
                "active_stage": {},
            }
        )

        tool_set = _shadow_activation_tools(activation)
        names = {item.name for item in tool_set.tools}
        self.assertNotIn("inspect_active_observation", names)
        table = next(
            item for item in tool_set.tools if item.name == "inspect_editable_context"
        ).run({})
        block = next(
            item for item in tool_set.tools if item.name == "inspect_context_block"
        ).run({"block_id": 1})

        self.assertIn("| id | kind | role | chars | preview |", table.content)
        self.assertIn("--- BEGIN EXACT CONTENT ---\nline 1\nline 2", block.content)
        self.assertNotIn('"content"', block.content)

class ShadowJudgeContractTest(unittest.TestCase):
    def test_score_and_assessment_contract(self) -> None:
        score, assessment = _parse_judgment(
            '{"score":1,"assessment":"The alias identifies the reference entity."}'
        )

        self.assertEqual(1, score)
        self.assertEqual(
            "The alias identifies the reference entity.",
            assessment,
        )

    def test_rejects_provider_extras_from_semantic_output(self) -> None:
        with self.assertRaises(ValueError):
            _parse_judgment(
                '{"score":1,"assessment":"Correct.","reasoning":"hidden"}'
            )


class ShadowTemplateAssemblyTest(unittest.TestCase):
    def test_shadow_roles_assemble_without_formal_registry_changes(self) -> None:
        root = Path(__file__).resolve().parents[2]
        store = EvaluationEvidenceStore(
            report_dir=root,
            rollout_file=root / "unused.jsonl",
            summary={},
            cases={},
            rollouts={},
            student_template_root=None,
            harness_manifest={},
        )
        resources = TeacherResources(evaluation=store)
        expected = {
            "failure_analyst": "get_student_capability_view",
            "hypothesis_researcher": "get_student_behavior_interface",
        }

        for role_id, shadow_tool in expected.items():
            with self.subTest(role_id=role_id):
                spec = load_teacher_agent_spec(
                    root
                    / "experiments"
                    / "teacher_query_views"
                    / "templates"
                    / role_id,
                    runtime_context=resources,
                    role_id=role_id,
                    role_version=1,
                )
                names = [tool.name for tool in spec.tools.tools]
                self.assertIn(shadow_tool, names)
                self.assertIn("get_trajectory_change", names)


if __name__ == "__main__":
    unittest.main()
