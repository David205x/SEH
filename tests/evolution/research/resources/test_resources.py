"""Teacher 证据资源与机制草稿测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from search_harness.evolution.research.roles.contracts import (
    EvidenceReview,
    EvidenceReviewerInput,
    InterventionHypothesis,
    MechanismDistillation,
    MechanismDistillerInput,
)
from search_harness.evolution.research.resources.base import (
    EvaluationEvidenceStore,
    MechanismDraftStore,
    TeacherResources,
    TrialEvidenceStore,
)


class TeacherResourceTest(unittest.TestCase):
    def test_hook_model_mechanism_requires_probe_before_submission(self) -> None:
        resources = TeacherResources()
        draft_id = resources.mechanisms.create(goal="Classify evidence support.")
        resources.mechanisms.add_phase(
            draft_id=draft_id,
            phase="pre_final",
            guards=[],
            predicate="Does evidence support the candidate?",
            positive_rule="Evidence directly supports the candidate.",
            negative_rule="Evidence directly contradicts the candidate.",
            uncertain_rule="Evidence establishes neither boundary.",
            positive_evidence=["Direct support is present."],
            negative_evidence=["Direct contradiction is present."],
            uncertain_evidence=["Only related evidence is present."],
            decision_inputs=["candidate", "retrieved evidence"],
            runtime_inputs=["tool", "final_decision"],
            decision_evaluator="hook_model",
            action="Defer the unsupported final answer.",
            fallback_negative="Leave the decision unchanged.",
            fallback_uncertain="Leave the decision unchanged.",
            fallback_budget_exhausted="Leave the decision unchanged.",
            activation_budget=1,
        )
        resources.mechanisms.complete(
            draft_id=draft_id,
            behavioral_pseudocode=(
                "ON pre_final: classify evidence; defer only on positive."
            ),
            state_scope="One rollout-local activation flag.",
            expected_behavior="Unsupported finalization is deferred once.",
        )
        mechanism_ref = resources.mechanisms.validate(
            draft_id=draft_id,
            evidence_refs=["trial_001"],
        )
        result = MechanismDistillation(
            decision="distilled",
            mechanism_ref=mechanism_ref,
            rationale="The bounded behavior is supported.",
        )

        with self.assertRaisesRegex(ValueError, "must run"):
            resources.validate_mechanism_distillation(result)

        resources.hook_evaluator_probes.append({"draft_id": draft_id})
        resources.validate_mechanism_distillation(result)

    def test_distiller_cannot_request_evidence_after_budget_exhaustion(
        self,
    ) -> None:
        hypothesis = InterventionHypothesis.model_validate(
            {
                "fork_phase": "post_tool",
                "phase_plan": [
                    {
                        "phase": "post_tool",
                        "activation_condition": "A visible gap exists.",
                        "instruction": "Ask for another search.",
                        "expected_effect": "The Student searches again.",
                        "max_activations": 1,
                    }
                ],
                "evaluation": {
                    "primary_signal": "next_action",
                    "success_condition": "Another search occurs.",
                    "falsifier": "No search occurs.",
                    "secondary_metrics": [],
                },
                "applicability": "Partial-evidence retrieval cases.",
            }
        )
        resources = TeacherResources()
        resources.bind_role_input(
            MechanismDistillerInput(
                hypothesis=hypothesis,
                review={
                    "decision": "ready_to_distill",
                    "assessment": "The bounded behavior is supported.",
                },
                trial_reviews=[
                    {
                        "trial_ref": "trial_001",
                        "assessment": "The intervention was observed.",
                    }
                ],
                coverage_summary={
                    "required_distinct_examples": 3,
                    "required_positive_per_phase": 2,
                    "required_negative_per_phase": 2,
                    "observed_distinct_examples": 3,
                    "phase_coverage": [],
                    "unmet_requirements": [],
                    "special_obligations": [],
                    "default_requirements_met": True,
                },
                evidence_refs=["trial_001"],
                budget={
                    "max_trials_per_hypothesis": 1,
                    "trials_used": 1,
                    "trials_remaining": 0,
                    "max_trial_assignments": 3,
                    "assignments_used": 1,
                    "assignments_remaining": 2,
                    "conclusion_required": True,
                },
            )
        )

        with self.assertRaisesRegex(ValueError, "cannot request"):
            resources.validate_mechanism_distillation(
                MechanismDistillation(
                    decision="needs_evidence",
                    rationale="One more trial would otherwise be useful.",
                    next_obligation="Run another trial.",
                )
            )

    def test_review_validation_does_not_derive_decision_from_phase_labels(
        self,
    ) -> None:
        """验证资源门禁只检查 phase 覆盖，不替 Reviewer 决定总体结论。"""

        hypothesis = InterventionHypothesis.model_validate(
            {
                "fork_phase": "post_tool",
                "phase_plan": [
                    {
                        "phase": "post_tool",
                        "activation_condition": "Partial evidence is visible.",
                        "instruction": "Ask the Student to inspect the gap.",
                        "expected_effect": "The Student searches again.",
                        "max_activations": 1,
                    },
                    {
                        "phase": "pre_final",
                        "activation_condition": "The gap remains.",
                        "instruction": "Defer once.",
                        "expected_effect": "The Student reconsiders.",
                        "max_activations": 1,
                    },
                ],
                "evaluation": {
                    "primary_signal": "next_decision",
                    "success_condition": "A useful follow-up occurs.",
                    "falsifier": "No behavior changes.",
                    "secondary_metrics": [],
                },
                "applicability": "Partial-evidence retrieval cases.",
            }
        )
        resources = TeacherResources()
        resources.bind_role_input(
            EvidenceReviewerInput(
                hypothesis=hypothesis,
                aggregate_observations={"trial_count": 1},
                trial_reviews=[
                    {
                        "trial_ref": "trial_001",
                        "assessment": "The complete trial was reviewed.",
                    }
                ],
                budget={
                    "max_trials_per_hypothesis": 4,
                    "trials_used": 1,
                    "trials_remaining": 3,
                    "max_trial_assignments": 12,
                    "assignments_used": 1,
                    "assignments_remaining": 11,
                    "conclusion_required": False,
                },
            )
        )
        review = EvidenceReview(
            decision="ready_to_distill",
            phase_findings=[
                {
                    "phase": "post_tool",
                    "status": "supported",
                    "assessment": "The local effect was observed.",
                },
                {
                    "phase": "pre_final",
                    "status": "inconclusive",
                    "assessment": "The local effect was variable.",
                },
            ],
            assessment="A narrower mechanism remains worth distilling.",
            key_risk="The second phase may not transfer.",
            next_obligation=None,
        )

        resources.validate_evidence_review(review)

    def test_review_cannot_continue_after_trial_budget_is_exhausted(
        self,
    ) -> None:
        hypothesis = InterventionHypothesis.model_validate(
            {
                "fork_phase": "post_tool",
                "phase_plan": [
                    {
                        "phase": "post_tool",
                        "activation_condition": "A gap is visible.",
                        "instruction": "Ask for another search.",
                        "expected_effect": "The Student searches again.",
                        "max_activations": 1,
                    }
                ],
                "evaluation": {
                    "primary_signal": "next_action",
                    "success_condition": "Another search occurs.",
                    "falsifier": "No search occurs.",
                    "secondary_metrics": [],
                },
                "applicability": "Partial-evidence retrieval cases.",
            }
        )
        resources = TeacherResources()
        resources.bind_role_input(
            EvidenceReviewerInput(
                hypothesis=hypothesis,
                aggregate_observations={"trial_count": 4},
                trial_reviews=[
                    {
                        "trial_ref": "trial_004",
                        "assessment": "The final trial remained mixed.",
                    }
                ],
                budget={
                    "max_trials_per_hypothesis": 4,
                    "trials_used": 4,
                    "trials_remaining": 0,
                    "max_trial_assignments": 12,
                    "assignments_used": 4,
                    "assignments_remaining": 8,
                    "conclusion_required": True,
                },
            )
        )
        review = EvidenceReview(
            decision="continue",
            phase_findings=[
                {
                    "phase": "post_tool",
                    "status": "inconclusive",
                    "assessment": "The available evidence remains mixed.",
                }
            ],
            assessment="Another trial would otherwise be useful.",
            next_obligation="Run another discriminating trial.",
        )

        with self.assertRaisesRegex(ValueError, "cannot continue"):
            resources.validate_evidence_review(review)

    def test_review_cannot_distill_with_unmet_default_coverage(self) -> None:
        """验证程序覆盖摘要不足时不能靠 Reviewer 主观放行蒸馏。"""

        hypothesis = InterventionHypothesis.model_validate(
            {
                "fork_phase": "post_tool",
                "phase_plan": [
                    {
                        "phase": "post_tool",
                        "activation_condition": "A gap is visible.",
                        "instruction": "Ask for another search.",
                        "expected_effect": "The Student searches again.",
                    }
                ],
                "evaluation": {
                    "primary_signal": "next_action",
                    "success_condition": "Another search occurs.",
                    "falsifier": "No search occurs.",
                },
                "applicability": "Partial-evidence retrieval cases.",
            }
        )
        resources = TeacherResources()
        resources.bind_role_input(
            EvidenceReviewerInput(
                hypothesis=hypothesis,
                aggregate_observations={"trial_count": 1},
                trial_reviews=[
                    {
                        "trial_ref": "trial_001",
                        "assessment": "One positive trial was observed.",
                    }
                ],
                coverage_summary={
                    "required_distinct_examples": 3,
                    "required_positive_per_phase": 2,
                    "required_negative_per_phase": 2,
                    "observed_distinct_examples": 1,
                    "phase_coverage": [
                        {
                            "phase": "post_tool",
                            "positive_count": 1,
                            "negative_count": 0,
                            "uncertain_count": 0,
                            "positive_distinct_examples": 1,
                            "negative_distinct_examples": 0,
                            "intervention_applied_count": 1,
                            "correct_non_intervention_count": 0,
                        }
                    ],
                    "unmet_requirements": [
                        "distinct examples: 1/3",
                        "post_tool positive distinct examples: 1/2",
                        "post_tool negative distinct examples: 0/2",
                    ],
                    "default_requirements_met": False,
                },
                budget={
                    "max_trials_per_hypothesis": 5,
                    "trials_used": 1,
                    "trials_remaining": 4,
                    "max_trial_assignments": 12,
                    "assignments_used": 1,
                    "assignments_remaining": 11,
                    "conclusion_required": False,
                },
            )
        )
        review = EvidenceReview(
            decision="ready_to_distill",
            phase_findings=[
                {
                    "phase": "post_tool",
                    "status": "supported",
                    "assessment": "The one observed trial was positive.",
                }
            ],
            assessment="The single case looks promising.",
        )

        with self.assertRaisesRegex(ValueError, "coverage requirements"):
            resources.validate_evidence_review(review)

    def test_trial_evidence_returns_trace_canonical_runs(
        self,
    ) -> None:
        """验证 Reviewer 保留 trace，并剥离 state 重复集合和 usage。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout = root / "rollouts.jsonl"
            source_run = {
                "status": "completed",
                "answer": "source",
                "state": {
                    "status": "completed",
                    "final_answer": "source",
                    "step": 1,
                    "model_inputs": [{"messages": []}],
                    "model_outputs": ["source"],
                    "parsed_outputs": [{"kind": "final_answer"}],
                    "tool_interactions": [],
                    "conversation_messages": [],
                    "hook_state": {"seen": True},
                },
                "trace": [
                    {
                        "event_type": "model_input",
                        "payload": {"messages": [{"role": "user", "content": "Q"}]},
                    },
                    {
                        "event_type": "model_output",
                        "payload": {
                            "raw_output": "<final_answer>source</final_answer>",
                            "usage": {"total_tokens": 10},
                            "metadata": {
                                "reasoning": "Source reasoning.",
                                "usage": {"total_tokens": 10},
                            },
                        },
                    },
                ],
            }
            rollout.write_text(
                json.dumps(
                    {
                        "example": {"example_id": "example_1"},
                        "replicate": {"replicate_id": "r000"},
                        "run": source_run,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            trial_file = root / "trial_001" / "worker.json"
            trial_file.parent.mkdir()
            trial_file.write_text(
                json.dumps(
                    {
                        "input": {"trial_objective": "Test one response."},
                        "output": {
                            "result_kind": "executed",
                            "action": "append_user_message",
                            "content": "Continue.",
                            "rationale": "Applied.",
                        },
                        "resource_artifacts": {
                            "intervention_trial": {
                                "source": {
                                    "rollout_file": str(rollout),
                                    "example_id": "example_1",
                                    "replicate_id": "r000",
                                    "prefix_id": 3,
                                    "source_run": {
                                        "answer": "duplicated source",
                                        "trace": [{"large": "duplicate"}],
                                    },
                                },
                                "action": {"action": "append_user_message"},
                                "context_changes": [{"op": "append"}],
                                "branch_run": {
                                    "status": "completed",
                                    "answer": "branch",
                                    "trace": [
                                        {
                                            "event_type": "model_output",
                                            "payload": {
                                                "raw_output": "branch",
                                                "metadata": {
                                                    "reasoning": "Branch reasoning.",
                                                    "usage": {"total_tokens": 12},
                                                },
                                            },
                                        }
                                    ],
                                },
                                "comparison": {
                                    "source": {"status": "completed"},
                                    "branch": {"status": "completed"},
                                },
                                "worker_summary": (
                                    "Legacy Worker self-assessment."
                                ),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            store = TrialEvidenceStore.load([trial_file])
            listing = store.list_trials()
            evidence = store.get_trial("trial_001")

        self.assertNotIn("source_run", listing["items"][0]["source"])
        self.assertEqual(
            [
                event["event_type"]
                for event in evidence["source"]["run"]["events"]
            ],
            ["model_input", "model_output"],
        )
        self.assertEqual(
            evidence["source"]["run"]["state"],
            {
                "status": "completed",
                "final_answer": "source",
                "step": 1,
                "hook_state": {"seen": True},
            },
        )
        self.assertNotIn("rollout_file", evidence["source"]["selector"])
        self.assertNotIn("source_run", evidence["source"]["selector"])
        self.assertEqual(
            evidence["run_scopes"]["branch"],
            "event catalog for continuation from the selected prefix",
        )
        source_event = store.get_trial_event(
            trial_ref="trial_001",
            stream="source",
            event_index=1,
        )
        self.assertEqual(
            source_event["event"]["payload"]["metadata"]["reasoning"],
            "Source reasoning.",
        )
        self.assertNotIn("usage", source_event["event"]["payload"])
        self.assertNotIn(
            "usage",
            store.get_trial_event(
                trial_ref="trial_001",
                stream="branch",
                event_index=0,
            )["event"]["payload"]["metadata"],
        )
        self.assertNotIn("worker_summary", evidence)
        store.validate_all_inspected()

    def test_cost_summary_reports_replicate_distribution_and_coverage(
        self,
    ) -> None:
        """验证成本摘要按 replicate 聚合，并显式报告 token 覆盖缺口。"""

        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={},
            cases={
                "example_1": {
                    "replicates": [
                        {
                            "execution": {
                                "tokens": {
                                    "total_tokens": 100,
                                    "input_tokens": 80,
                                }
                            }
                        },
                        {
                            "execution": {
                                "tokens": {
                                    "total_tokens": 300,
                                    "input_tokens": 200,
                                }
                            }
                        },
                    ]
                },
                "example_2": {"replicates": [{"execution": {}}]},
            },
            rollouts={},
            student_template_root=None,
            harness_manifest=None,
        )

        summary = store.get_cost_summary()
        total = summary["metrics"]["total_tokens"]

        self.assertEqual(summary["replicate_count"], 3)
        self.assertEqual(total["covered_replicates"], 2)
        self.assertAlmostEqual(total["coverage_rate"], 2 / 3)
        self.assertEqual(total["mean"], 200)
        self.assertEqual(total["p50"], 100)
        self.assertEqual(total["p95"], 300)

    def test_cases_can_be_sorted_by_mean_replicate_tokens(self) -> None:
        """验证 Analyst 可按指定 token 指标定位高成本逻辑样本。"""

        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={},
            cases={
                "cheap": {
                    "example_id": "cheap",
                    "question": "Cheap?",
                    "stability": "stable_failure",
                    "replicates": [
                        {
                            "execution": {
                                "tokens": {"total_tokens": 100}
                            }
                        }
                    ],
                },
                "expensive": {
                    "example_id": "expensive",
                    "question": "Expensive?",
                    "stability": "stable_failure",
                    "replicates": [
                        {
                            "execution": {
                                "tokens": {"total_tokens": 400}
                            }
                        },
                        {
                            "execution": {
                                "tokens": {"total_tokens": 200}
                            }
                        },
                    ],
                },
            },
            rollouts={},
            student_template_root=None,
            harness_manifest=None,
        )

        page = store.list_cases_by_cost(
            page=1,
            page_size=10,
            stability="stable_failure",
            token_metric="total_tokens",
            order="descending",
        )

        self.assertEqual(
            [item["example_id"] for item in page["items"]],
            ["expensive", "cheap"],
        )
        self.assertEqual(page["items"][0]["mean_tokens"], 300)

    def test_failure_analyst_context_omits_paths_and_token_details(self) -> None:
        """验证失败分析初始摘要仅暴露诊断所需的紧凑指标。"""

        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={
                "metrics": {
                    "answers": {
                        "accuracy": 0.5,
                        "stable_failure_count": 1,
                    },
                    "execution": {
                        "record_count": 2,
                        "completed_rate": 1.0,
                    },
                    "tokens": {"total_tokens": 999},
                },
                "provenance": {
                    "dataset": {"path": "secret.jsonl"},
                    "model": {
                        "model_id": "student",
                        "temperature": 0.6,
                        "seed": 42,
                    },
                    "execution": {"rollouts_per_example": 2},
                },
            },
            cases={},
            rollouts={},
            student_template_root=None,
            harness_manifest={"harness_id": "baseline"},
        )

        context = store.failure_analyst_context()

        self.assertEqual(context["outcomes"]["accuracy"], 0.5)
        self.assertEqual(context["outcomes"]["rollouts_per_example"], 2)
        self.assertNotIn("tokens", context)
        self.assertNotIn("report_dir", context)
        self.assertNotIn("dataset", context)
        self.assertNotIn("sampling", context)
        self.assertNotIn("harness", context)

    def test_behavior_trajectory_keeps_reasoning_and_omits_model_input(
        self,
    ) -> None:
        """验证紧凑轨迹保留模型思考与行为，同时移除重复输入和 usage。"""

        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={},
            cases={
                "example_1": {
                    "example_id": "example_1",
                    "golden_answer": "Gold",
                    "replicates": [
                        {
                            "replicate_id": "r000",
                            "score": 0,
                            "score_source": "teacher",
                        }
                    ],
                }
            },
            rollouts={
                "example_1": {
                    "r000": {
                        "example": {
                            "example_id": "example_1",
                            "question": "Question?",
                        },
                        "replicate": {"replicate_id": "r000"},
                        "run": {
                            "status": "completed",
                            "answer": "Prediction",
                            "trace": [
                                {
                                    "event_type": "model_input",
                                    "payload": {"messages": ["large input"]},
                                },
                                {
                                    "event_type": "model_output",
                                    "step": 1,
                                    "payload": {
                                        "raw_output": (
                                            "In-band thought."
                                            "<final_answer>Prediction</final_answer>"
                                        ),
                                        "metadata": {
                                            "reasoning": "Native thought.",
                                            "usage": {"total_tokens": 100},
                                        },
                                    },
                                },
                                {
                                    "event_type": "final_answer",
                                    "step": 1,
                                    "payload": {"answer": "Prediction"},
                                },
                            ],
                        },
                    }
                }
            },
            student_template_root=None,
            harness_manifest=None,
        )

        trajectory = store.get_trajectory(
            example_id="example_1",
            replicate_id="r000",
            view="behavior",
        )

        event_types = [event["event_type"] for event in trajectory["events"]]
        self.assertNotIn("model_input", event_types)
        model_output = trajectory["events"][0]["payload"]
        self.assertEqual(model_output["native_reasoning"], "Native thought.")
        self.assertIn("In-band thought.", model_output["raw_output"])
        self.assertNotIn("usage", model_output)

    def test_trajectory_read_budget_counts_unique_references(self) -> None:
        """验证失败分析证据预算允许重复查看已有轨迹但拒绝新的超额轨迹。"""

        records = {
            f"example_{index}": {
                "r000": {
                    "example": {"example_id": f"example_{index}"},
                    "replicate": {"replicate_id": "r000"},
                    "run": {"trace": []},
                }
            }
            for index in range(1, 3)
        }
        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={},
            cases={},
            rollouts=records,
            student_template_root=None,
            harness_manifest=None,
        )
        store.set_trajectory_read_budget(1)

        store.get_trajectory(
            example_id="example_1",
            replicate_id="r000",
            view="behavior",
        )
        store.get_trajectory(
            example_id="example_1",
            replicate_id="r000",
            view="full",
        )
        with self.assertRaisesRegex(ValueError, "budget is exhausted"):
            store.get_trajectory(
                example_id="example_2",
                replicate_id="r000",
                view="behavior",
            )

    def test_evidence_refs_must_match_inspected_trajectory_ids(self) -> None:
        """验证终态引用不能截断或伪造已读取轨迹的 ID。"""

        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={},
            cases={},
            rollouts={
                "example_1": {
                    "r000": {
                        "example": {"example_id": "example_1"},
                        "replicate": {"replicate_id": "r000"},
                        "run": {"trace": []},
                    }
                }
            },
            student_template_root=None,
            harness_manifest=None,
        )
        store.get_trajectory(
            example_id="example_1",
            replicate_id="r000",
            view="behavior",
        )

        store.validate_evidence_refs(["example_1/r000"])
        with self.assertRaisesRegex(ValueError, "were not inspected"):
            store.validate_evidence_refs(["example/r000"])

    def test_researcher_is_restricted_to_and_must_read_cited_trajectories(
        self,
    ) -> None:
        """验证 Researcher 只能访问 Analyst 引用且提交前必须逐条检查。"""

        store = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollouts.jsonl"),
            summary={},
            cases={
                "cited": {
                    "example_id": "cited",
                    "golden_answer": "Hidden answer",
                },
                "hidden": {"example_id": "hidden"},
            },
            rollouts={
                "cited": {
                    "r000": {
                        "example": {"example_id": "cited"},
                        "replicate": {"replicate_id": "r000"},
                        "run": {"trace": []},
                    },
                    "r001": {
                        "example": {"example_id": "cited"},
                        "replicate": {"replicate_id": "r001"},
                        "run": {"trace": []},
                    },
                },
                "hidden": {
                    "r000": {
                        "example": {"example_id": "hidden"},
                        "replicate": {"replicate_id": "r000"},
                        "run": {"trace": []},
                    }
                },
            },
            student_template_root=None,
            harness_manifest=None,
        )
        store.restrict_to_evidence_refs(["cited/r000", "cited/r001"])

        with self.assertRaisesRegex(ValueError, "only cited examples"):
            store.get_case("hidden")
        with self.assertRaisesRegex(ValueError, "only cited trajectories"):
            store.get_trajectory(
                example_id="hidden",
                replicate_id="r000",
                view="behavior",
            )
        store.get_trajectory(
            example_id="cited",
            replicate_id="r000",
            view="behavior",
        )
        trajectory = store.get_trajectory(
            example_id="cited",
            replicate_id="r000",
            view="behavior",
        )
        self.assertNotIn("golden_answer", trajectory["example"])
        with self.assertRaisesRegex(ValueError, "only the behavior view"):
            store.get_trajectory(
                example_id="cited",
                replicate_id="r000",
                view="full",
            )
        with self.assertRaisesRegex(ValueError, "inspect every cited"):
            store.validate_allowed_evidence_inspected()
        store.get_trajectory(
            example_id="cited",
            replicate_id="r001",
            view="behavior",
        )

        store.validate_allowed_evidence_inspected()

    def test_indexes_example_and_replicate_identity(self) -> None:
        """验证 evaluation 资源按 example_id 与 replicate_id 精确读取轨迹。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report"
            report.mkdir()
            rollout = root / "rollouts.jsonl"
            (report / "summary.json").write_text(
                json.dumps({"source_file": str(rollout), "metrics": {}}),
                encoding="utf-8",
            )
            (report / "per_example.jsonl").write_text(
                json.dumps(
                    {
                        "example_id": "example_1",
                        "question": "Question?",
                        "stability": "stable_failure",
                        "replicates": [{"replicate_id": "r000"}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            rollout.write_text(
                json.dumps(
                    {
                        "example": {
                            "example_id": "example_1",
                            "question": "Question?",
                        },
                        "replicate": {"replicate_id": "r000"},
                        "run": {"status": "completed", "trace": []},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            store = EvaluationEvidenceStore.load(
                report_dir=report,
                rollout_file=None,
                student_template_root=None,
            )

        trajectory = store.get_trajectory(
            example_id="example_1",
            replicate_id="r000",
        )
        self.assertEqual(trajectory["run"]["status"], "completed")
        self.assertEqual(
            store.list_cases(page=1, page_size=10, stability="stable_failure")[
                "total_items"
            ],
            1,
        )

    def test_mechanism_requires_complete_validated_draft(self) -> None:
        """验证 Distiller 只有补齐动作、状态和 fallback 后才能获得机制引用。"""

        store = MechanismDraftStore()
        draft_id = store.create(
            goal="Continue evidence gathering.",
        )
        store.add_phase(
            draft_id=draft_id,
            phase="post_tool",
            guards=[],
            predicate="Is the target relation absent?",
            positive_rule="The required target relation is absent.",
            negative_rule="The required target relation is present.",
            uncertain_rule="The result cannot establish presence or absence.",
            positive_evidence=["A result omitting the target relation."],
            negative_evidence=["A result stating the target relation."],
            uncertain_evidence=[],
            decision_inputs=["question", "latest tool result"],
            runtime_inputs=["task", "tool"],
            decision_evaluator="deterministic",
            action="Append a generic evidence-gap instruction.",
            fallback_negative="Leave the current decision unchanged.",
            fallback_uncertain="Leave the current decision unchanged.",
            fallback_budget_exhausted="Leave the current decision unchanged.",
            activation_budget=1,
        )

        with self.assertRaises(ValidationError):
            store.validate(draft_id=draft_id, evidence_refs=["trial_1"])

        store.complete(
            draft_id=draft_id,
            behavioral_pseudocode=(
                "STATE:\n"
                "  continued = false  // rollout-local\n"
                "ON post_tool(latest_tool_result):\n"
                "  SET continued = true\n"
                "  DEFER with a generic evidence-gap instruction\n"
                "ACTOR_OBLIGATION_AFTER_DEFER:\n"
                "  perform one relevant follow-up retrieval\n"
                "FALLBACK:\n"
                "  do nothing when uncertain"
            ),
            state_scope="Until the next model generation.",
            expected_behavior="Issue a relevant follow-up retrieval.",
        )
        mechanism_ref = store.validate(
            draft_id=draft_id,
            evidence_refs=["trial_1"],
        )

        self.assertEqual(mechanism_ref, "mechanism_001")
        self.assertEqual(
            store.resolve(mechanism_ref).trigger_phase,
            "post_tool",
        )
        self.assertIn(
            "ACTOR_OBLIGATION_AFTER_DEFER",
            store.resolve(mechanism_ref).behavioral_pseudocode,
        )


if __name__ == "__main__":
    unittest.main()
