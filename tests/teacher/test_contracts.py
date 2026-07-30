"""Teacher v2 Pydantic 协议测试。"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from search_harness.teacher.contracts import (
    CandidateReview,
    CompilerResult,
    EvidenceReview,
    FailureAnalystInput,
    FailureDirection,
    HypothesisResearcherInput,
    InterventionHypothesis,
    InterventionWorkerResult,
    MechanismSpec,
    MechanismDistillation,
    get_teacher_role,
)


class TeacherContractTest(unittest.TestCase):
    def test_failure_analyst_input_has_no_solution_biased_history(self) -> None:
        """验证首轮失败诊断输入只保留可选分析焦点。"""

        role_input = FailureAnalystInput()

        self.assertEqual(
            role_input.model_dump(mode="json"),
            {"analysis_focus": None},
        )

    def test_failure_direction_requires_unique_trajectory_references(self) -> None:
        """验证失败方向只能引用至少两条唯一且格式正确的已检查轨迹。"""

        with self.assertRaises(ValidationError):
            FailureDirection(
                pattern="The Actor finalizes after partial evidence.",
                applicability="Multi-relation questions with partial evidence.",
                caveats=["Corpus coverage remains unknown."],
                evidence_refs=["example_1/r000", "example_1/r000"],
            )

    def test_researcher_input_rejects_removed_resource_controls(self) -> None:
        """验证 Researcher 输入只接受冻结问题方向，不再接收预算和先验方案。"""

        with self.assertRaises(ValidationError):
            HypothesisResearcherInput.model_validate(
                {
                    "problem_direction": {
                        "pattern": "The Actor stops after partial evidence.",
                        "applicability": "Multi-hop retrieval cases.",
                        "caveats": ["Corpus coverage may vary."],
                        "evidence_refs": [
                            "example_1/r000",
                            "example_2/r000",
                        ],
                    },
                    "trial_budget": 5,
                }
            )

    def test_hypothesis_requires_unique_bounded_secondary_metrics(self) -> None:
        """验证 Researcher 只能附带少量且不重复的次级观测指标。"""

        with self.assertRaises(ValidationError):
            InterventionHypothesis(
                trigger="At pre_final when evidence remains incomplete.",
                trigger_phase="pre_final",
                intervention="Defer once with a generic gap instruction.",
                predicted_actor_response="The Actor performs another action.",
                evaluation={
                    "primary_signal": "next_actor_action",
                    "success_condition": "The next action is a tool call.",
                    "falsifier": "The next action is a final answer.",
                    "secondary_metrics": ["total_tokens", "total_tokens"],
                },
                applicability="Partial-evidence multi-hop cases.",
            )

    def test_role_registry_binds_output_contract(self) -> None:
        """验证角色 ID 同时约束输入类型和稳定输出协议版本。"""

        role = get_teacher_role("failure_analyst", 1)

        self.assertEqual(role.output_contract_id, "failure_direction")
        self.assertEqual(role.output_contract_version, 1)

        self.assertEqual(
            get_teacher_role(
                "hypothesis_researcher",
                1,
            ).output_contract_version,
            3,
        )
        self.assertEqual(
            get_teacher_role(
                "candidate_reviewer",
                1,
            ).output_contract_version,
            2,
        )
        self.assertEqual(
            get_teacher_role(
                "intervention_worker",
                1,
            ).output_contract_version,
            3,
        )
        self.assertEqual(
            get_teacher_role(
                "trial_reviewer",
                1,
            ).output_contract_id,
            "trial_review",
        )

    def test_continue_review_requires_next_obligation(self) -> None:
        """验证继续取证时必须指出唯一的下一项证据义务。"""

        with self.assertRaises(ValidationError):
            EvidenceReview(
                decision="continue",
                assessment="Evidence remains incomplete.",
                key_risk=None,
                next_obligation=None,
            )

    def test_terminal_review_normalizes_string_null_obligation(self) -> None:
        """验证终态评审把字符串 null 宽松归一为空值。"""

        review = EvidenceReview(
            decision="reject",
            assessment="The trial falsified the hypothesis.",
            key_risk="none",
            next_obligation="null",
        )

        self.assertIsNone(review.key_risk)
        self.assertIsNone(review.next_obligation)

    def test_revision_review_accepts_common_empty_obligation_values(
        self,
    ) -> None:
        """验证 revise 可依靠 assessment 并宽松接收常见空值写法。"""

        for raw_value in (None, "", "0", 0, "null", "None", "n/a"):
            with self.subTest(raw_value=raw_value):
                review = EvidenceReview(
                    decision="revise",
                    assessment="Require an explicit tool execution instruction.",
                    key_risk=None,
                    next_obligation=raw_value,
                )
                self.assertIsNone(review.next_obligation)

    def test_ready_review_allows_mixed_phase_findings(self) -> None:
        """验证局部 phase 结论不机械决定总体蒸馏判断。"""

        review = EvidenceReview(
            decision="ready_to_distill",
            phase_findings=[
                {
                    "phase": "post_tool",
                    "status": "supported",
                    "assessment": "The next Actor decision was a tool call.",
                },
                {
                    "phase": "pre_final",
                    "status": "inconclusive",
                    "assessment": "The local effect varied across trials.",
                },
            ],
            assessment=(
                "The evidence is sufficient for a narrower mechanism."
            ),
            key_risk="The pre-final phase may be omitted during distillation.",
            next_obligation=None,
        )

        self.assertEqual(review.decision, "ready_to_distill")
        self.assertEqual(review.phase_findings[1].status, "inconclusive")

    def test_distilled_result_requires_mechanism_reference(self) -> None:
        """验证蒸馏成功不能只靠文字声明而缺少已验证机制引用。"""

        with self.assertRaises(ValidationError):
            MechanismDistillation(
                decision="distilled",
                mechanism_ref=None,
                rationale="The intervention is portable.",
                next_obligation=None,
            )

    def test_distilled_result_rejects_completed_obligation_text(self) -> None:
        """验证蒸馏终态不携带语义上已经完成的证据义务。"""

        with self.assertRaises(ValidationError):
            MechanismDistillation(
                decision="distilled",
                mechanism_ref="mechanism_001",
                rationale="The intervention is portable.",
                next_obligation="No further work is required.",
            )

    def test_mechanism_rejects_oversized_behavioral_pseudocode(self) -> None:
        """验证机制行为伪代码不能超过协议规定的 3000 字符。"""

        with self.assertRaises(ValidationError):
            MechanismSpec(
                goal="Continue evidence gathering.",
                trigger_phase="pre_final",
                trigger_condition="The first final answer is proposed.",
                decision_inputs=["candidate answer", "rollout-local state"],
                decision_evaluator="deterministic",
                action="Defer the first final answer once.",
                behavioral_pseudocode="x" * 3001,
                state_scope="One rollout.",
                fallback="Accept subsequent final answers.",
                expected_behavior="The Actor performs another retrieval.",
                evidence_refs=["trial_001"],
            )

    def test_mechanism_requires_behavioral_pseudocode(self) -> None:
        """验证旧版机制缺少行为伪代码时不会通过兼容路径加载。"""

        with self.assertRaises(ValidationError) as captured:
            MechanismSpec.model_validate(
                {
                    "goal": "Continue evidence gathering.",
                    "trigger_phase": "pre_final",
                    "trigger_condition": "The first final answer is proposed.",
                    "decision_inputs": [
                        "candidate answer",
                        "rollout-local state",
                    ],
                    "decision_evaluator": "deterministic",
                    "action": "Defer the first final answer once.",
                    "state_scope": "One rollout.",
                    "fallback": "Accept subsequent final answers.",
                    "expected_behavior": "The Actor performs another retrieval.",
                    "evidence_refs": ["trial_001"],
                }
            )

        self.assertEqual(
            captured.exception.errors()[0]["loc"],
            ("behavioral_pseudocode",),
        )

    def test_mechanism_requires_explicit_decision_evaluator(self) -> None:
        """验证机制不能依赖 Compiler 猜测触发判断的实现方式。"""

        with self.assertRaises(ValidationError) as captured:
            MechanismSpec.model_validate(
                {
                    "goal": "Continue evidence gathering.",
                    "trigger_phase": "pre_final",
                    "trigger_condition": "The first final answer is proposed.",
                    "decision_inputs": ["candidate answer"],
                    "action": "Defer the first final answer once.",
                    "behavioral_pseudocode": "Defer the first final answer.",
                    "state_scope": "One rollout.",
                    "fallback": "Accept subsequent final answers.",
                    "expected_behavior": "The Actor performs another retrieval.",
                    "evidence_refs": ["trial_001"],
                }
            )

        self.assertEqual(
            captured.exception.errors()[0]["loc"],
            ("phase_rules", 0, "decision_evaluator"),
        )

    def test_mechanism_rejects_unknown_decision_evaluator(self) -> None:
        """验证机制判断器只接受确定性规则或有界 Hook 模型。"""

        with self.assertRaises(ValidationError):
            MechanismSpec(
                goal="Continue evidence gathering.",
                trigger_phase="pre_final",
                trigger_condition="The first final answer is proposed.",
                decision_inputs=["candidate answer"],
                decision_evaluator="teacher",  # type: ignore[arg-type]
                action="Defer the first final answer once.",
                behavioral_pseudocode="Defer the first final answer.",
                state_scope="One rollout.",
                fallback="Accept subsequent final answers.",
                expected_behavior="The Actor performs another retrieval.",
                evidence_refs=["trial_001"],
            )

    def test_intervention_modified_phase_must_be_activated(self) -> None:
        """验证 Worker 不会把未实际到达的 phase 记成上下文修改。"""

        with self.assertRaises(ValidationError):
            InterventionWorkerResult(
                result_kind="unsuitable_assignment",
                activated_phases=[],
                modified_phases=["post_tool"],
                unmet_phases=["post_tool"],
            )

    def test_intervention_result_kind_requires_concrete_modification(
        self,
    ) -> None:
        """验证 executed 与非 executed 结果均由事实修改 phase 约束。"""

        with self.assertRaises(ValidationError):
            InterventionWorkerResult(
                result_kind="executed",
                activated_phases=["post_tool"],
                modified_phases=[],
            )
        with self.assertRaises(ValidationError):
            InterventionWorkerResult(
                result_kind="unsupported_hypothesis",
                activated_phases=["post_tool"],
                modified_phases=["post_tool"],
            )

    def test_compiler_submission_requires_candidate_reference(self) -> None:
        """验证 Compiler 不能仅以文本声称已提交候选。"""

        with self.assertRaises(ValidationError):
            CompilerResult(
                decision="submitted",
                candidate_ref=None,
                implementation_summary="Added a Hook.",
                unresolved_risk=None,
            )

    def test_candidate_revision_requires_next_obligation(self) -> None:
        """验证 Reviewer 建议修订时必须给出可执行的下一项义务。"""

        with self.assertRaises(ValidationError):
            CandidateReview(
                recommendation="revise",
                observed_effect="The mechanism fires inconsistently.",
                reason="The trigger is too broad.",
                next_obligation=None,
                revision_target="implementation",
            )

    def test_candidate_revision_requires_explicit_target(self) -> None:
        """验证候选修订必须明确返回证据、机制或实现层。"""

        with self.assertRaises(ValidationError):
            CandidateReview(
                recommendation="revise",
                observed_effect="The behavior is promising.",
                reason="One bounded revision remains.",
                next_obligation="Narrow the implementation trigger.",
                revision_target=None,
            )


if __name__ == "__main__":
    unittest.main()
