"""NativeChatRoleRunner 的离线原生工具协议测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openai.types import CompletionUsage
from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)
from pydantic import ValidationError

from search_harness.integrations.openai_compatible import OpenAICompatibleConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
    _structured_validation_feedback,
)
from search_harness.evolution.research.roles.contracts import EvidenceReview
from search_harness.evolution.research.roles.provenance import (
    input_view_digest,
    teacher_role_scope_from_artifact,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DISTILLER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "mechanism_distiller"
)
SHADOW_DISTILLER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "shadow_mechanism_distiller"
)
RESEARCHER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "hypothesis_researcher"
)
REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "evidence_reviewer"
)
TRIAL_REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "trial_reviewer"
)


class ReplayCompletions:
    """按顺序返回原生 ChatCompletionMessage。"""

    def __init__(self, messages: list[ChatCompletionMessage]) -> None:
        self.messages = messages
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.messages:
            raise AssertionError("Native runtime made an unexpected request")
        message = self.messages.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=CompletionUsage(
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
            ),
        )


class ReplayClient:
    """提供 Native runtime 所需的最小 client 表面。"""

    def __init__(self, messages: list[ChatCompletionMessage]) -> None:
        self.completions = ReplayCompletions(messages)
        self.chat = SimpleNamespace(completions=self.completions)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class NativeChatRoleRunnerTest(unittest.IsolatedAsyncioTestCase):
    def test_length_feedback_reports_field_and_actual_limit(self) -> None:
        arguments = {
            "decision": "continue",
            "phase_findings": [
                {
                    "phase": "post_tool",
                    "status": "inconclusive",
                    "assessment": "x" * 601,
                }
            ],
            "assessment": "More evidence is required.",
            "key_risk": None,
            "next_obligation": "Run one independent trial.",
        }
        try:
            EvidenceReview.model_validate(arguments)
        except ValidationError as exc:
            feedback, fields = _structured_validation_feedback(exc, arguments)
        else:
            self.fail("overlong Evidence Review unexpectedly validated")

        self.assertEqual(
            fields,
            ["phase_findings.0.assessment:string_too_long"],
        )
        self.assertIn("actual_length=601", feedback)
        self.assertIn("maximum_length=600", feedback)

    async def test_exhausted_role_exposes_complete_failure_artifact(self) -> None:
        client = ReplayClient(
            [ChatCompletionMessage(role="assistant", content="not submitted")]
        )
        config = OpenAICompatibleConfig(
            base_url="https://teacher.invalid",
            model_id="teacher-test",
            max_tokens=512,
        )

        with self.assertRaises(TeacherRoleRunFailed) as raised:
            await NativeChatRoleRunner(
                max_turns=1,
                client=client,
                config=config,
            ).run(
                template_root=REVIEWER_TEMPLATE,
                role_id="evidence_reviewer",
                role_version=1,
                role_input={
                    "hypothesis": _hypothesis(
                        intervention="Append one bounded instruction."
                    ),
                    "aggregate_observations": {"trial_count": 0},
                    "trial_reviews": [
                        {
                            "trial_ref": "trial_001",
                            "assessment": "The trial remains inconclusive.",
                        }
                    ],
                    "budget": _review_budget(trials_used=1),
                    "prior_obligation": None,
                },
                resource_config=TeacherResourceConfig(),
            )

        artifact = raised.exception.failure_artifact
        request = client.completions.requests[0]
        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["schema_version"], 2)
        self.assertEqual(artifact["role"]["id"], "evidence_reviewer")
        self.assertEqual(
            teacher_role_scope_from_artifact(artifact).model_id,
            "teacher-test",
        )
        self.assertEqual(
            artifact["input_view_digest"],
            input_view_digest(
                [
                    {
                        "messages": request["messages"],
                        "tools": request["tools"],
                    }
                ]
            ),
        )
        self.assertEqual(len(artifact["base_prompt_digest"]), 64)
        self.assertEqual(artifact["error"]["turn_count"], 1)
        self.assertEqual(
            artifact["role_budget"],
            {"max_tokens": 512, "max_turns": 1},
        )
        self.assertEqual(artifact["usage"]["requests"], 1)
        self.assertEqual(artifact["transcript"][-1]["role"], "user")

    async def test_shadow_distiller_materializes_shallow_submission(
        self,
    ) -> None:
        """The model submits a ref while the artifact stores the full product."""

        responses = [
            _tool_message(
                "create_shadow_mechanism_draft",
                "shadow_create",
                {
                    "effect_kind": "behavioral_intermediate",
                    "effect_success": (
                        "The next Student generation performs one search."
                    ),
                },
            ),
            _tool_message(
                "add_shadow_decision_phase",
                "shadow_phase",
                {
                    "draft_id": "shadow_draft_001",
                    "phase": "pre_final",
                    "guards": [
                        "stage.final_decision is present."
                    ],
                    "evaluator": "hook_model",
                    "inputs": [
                        {
                            "name": "question",
                            "sources": ["core.question"],
                        },
                        {
                            "name": "candidate",
                            "sources": ["stage.final_decision"],
                        },
                    ],
                    "positive": "A required fact is missing.",
                    "negative": "All required facts are present.",
                    "uncertain": "The inputs cannot establish either case.",
                    "on_success": "Defer the final answer once.",
                    "fallback_default": "continue_without_change",
                    "activation_limit": 1,
                    "fallback_uncertain": "",
                    "fallback_exhausted": "",
                },
            ),
            _tool_message(
                "validate_shadow_mechanism_draft",
                "shadow_validate",
                {
                    "draft_id": "shadow_draft_001",
                    "state": [],
                    "constraints": [],
                },
            ),
            _tool_message(
                "submit_shadow_distillation_result",
                "shadow_submit",
                {
                    "outcome": "distilled",
                    "mechanism_ref": "shadow_mechanism_001",
                    "obligation": None,
                },
            ),
        ]
        client = ReplayClient(responses)
        config = OpenAICompatibleConfig(
            base_url="https://teacher.invalid",
            model_id="teacher-test",
            max_tokens=512,
        )

        with tempfile.TemporaryDirectory() as directory:
            trial_file = Path(directory) / "trial_001" / "intervention.json"
            trial_file.parent.mkdir()
            trial_file.write_text(
                json.dumps(
                    {
                        "intent": "Test one bounded intervention.",
                        "comparison": {"process_success": True},
                        "worker_summary": "The Student searched again.",
                    }
                ),
                encoding="utf-8",
            )
            artifact = await NativeChatRoleRunner(
                max_turns=6,
                client=client,
                config=config,
            ).run(
                template_root=SHADOW_DISTILLER_TEMPLATE,
                role_id="shadow_mechanism_distiller",
                role_version=1,
                role_input=_distiller_input(),
                resource_config=TeacherResourceConfig(
                    trial_files=[trial_file]
                ),
            )

        self.assertEqual(artifact["output"]["outcome"], "distilled")
        self.assertEqual(
            artifact["output"]["mechanism"]["phases"][0]["phase"],
            "pre_final",
        )
        self.assertIn(
            "shadow_mechanism_001",
            artifact["validated_mechanisms"],
        )
        terminal = client.completions.requests[0]["tools"][-1]["function"]
        self.assertIn("mechanism_ref", terminal["parameters"]["properties"])
        self.assertNotIn("mechanism", terminal["parameters"]["properties"])

    async def test_trial_reviewer_must_read_its_single_full_trial(
        self,
    ) -> None:
        """验证单条审阅必须先读取其绑定的完整 Worker 轨迹。"""

        review = {
            "trial_ref": "trial_001",
            "predicate_observations": [
                {
                    "phase": "post_tool",
                    "predicate_label": "positive",
                    "decisive_observation": "The evidence gap was visible.",
                    "phase_execution": "intervention_applied",
                    "observed_effect": "The Student searched again.",
                    "outcome_evidence": None,
                }
            ],
            "assessment": "The intervention effect is visible.",
        }
        client = ReplayClient(
            [
                _tool_message(
                    "submit_trial_review",
                    "submit_too_early",
                    review,
                ),
                _tool_message(
                    "get_trial_evidence",
                    "read_trial",
                    {"trial_ref": "trial_001"},
                ),
                _tool_message(
                    "submit_trial_review",
                    "submit_review",
                    review,
                ),
            ]
        )
        config = OpenAICompatibleConfig(
            base_url="https://teacher.invalid",
            model_id="teacher-test",
            max_tokens=512,
            temperature=0.4,
            seed=7,
        )
        with tempfile.TemporaryDirectory() as directory:
            trial_file = _trial_file(Path(directory), "trial_001")
            artifact = await NativeChatRoleRunner(
                max_turns=5,
                client=client,
                config=config,
            ).run(
                template_root=TRIAL_REVIEWER_TEMPLATE,
                role_id="trial_reviewer",
                role_version=1,
                role_input={
                    "hypothesis": _hypothesis(
                        intervention="Append one bounded instruction."
                    ),
                    "trial_ref": "trial_001",
                },
                resource_config=TeacherResourceConfig(
                    trial_files=[trial_file]
                ),
            )

        self.assertEqual(artifact["output"], review)
        self.assertTrue(
            artifact["tool_calls"][0]["metadata"]["validation_error"]
        )
        self.assertEqual(
            artifact["role_session"]["resource_state"]["trials"][
                "trial_reads"
            ],
            ["trial_001"],
        )

    async def test_continues_reviewer_with_new_trial_and_read_ledger(
        self,
    ) -> None:
        """验证 Reviewer 保留 transcript 并追加独立 trial 审阅。"""

        responses = [
            _tool_message(
                "submit_evidence_review",
                "call_review_1",
                {
                    "decision": "continue",
                    "phase_findings": [
                        {
                            "phase": "post_tool",
                            "status": "inconclusive",
                            "assessment": (
                                "One trial does not establish consistency."
                            ),
                        }
                    ],
                    "assessment": "One trial does not resolve consistency.",
                    "key_risk": "The response may be case-specific.",
                    "next_obligation": "Test one independent case.",
                },
            ),
            _tool_message(
                "submit_evidence_review",
                "call_review_2",
                {
                    "decision": "revise",
                    "phase_findings": [
                        {
                            "phase": "post_tool",
                            "status": "unsupported",
                            "assessment": (
                                "The second trial contradicted the effect."
                            ),
                        }
                    ],
                    "assessment": "The second trial contradicts the response.",
                    "key_risk": "The mechanism is not consistent.",
                    "next_obligation": "null",
                },
            ),
        ]
        client = ReplayClient(responses)
        config = OpenAICompatibleConfig(
            base_url="https://teacher.invalid",
            model_id="teacher-test",
            max_tokens=512,
            temperature=0.4,
            seed=7,
        )

        runtime = NativeChatRoleRunner(
            max_turns=5,
            client=client,
            config=config,
        )
        first = await runtime.run(
            template_root=REVIEWER_TEMPLATE,
            role_id="evidence_reviewer",
            role_version=1,
            role_input={
                "hypothesis": _hypothesis(
                    intervention="Append one bounded instruction."
                ),
                "aggregate_observations": {"trial_count": 1},
                "trial_reviews": [
                    {
                        "trial_ref": "trial_001",
                        "assessment": "The effect needs another case.",
                    }
                ],
                "budget": _review_budget(trials_used=1),
                "prior_obligation": None,
            },
            resource_config=TeacherResourceConfig(),
        )
        second = await runtime.continue_reviewer(
            previous_artifact=first,
            trial_reviews=[
                {
                    "trial_ref": "trial_002",
                    "assessment": "The second trial contradicted the effect.",
                }
            ],
            aggregate_observations={"trial_count": 2},
            budget=_review_budget(trials_used=2),
        )

        self.assertEqual(first["role_session"]["revision"], 1)
        self.assertEqual(second["role_session"]["revision"], 2)
        self.assertEqual(
            first["role_session"]["session_id"],
            second["role_session"]["session_id"],
        )
        self.assertEqual(
            [
                review["trial_ref"]
                for review in second["input"]["trial_reviews"]
            ],
            ["trial_001", "trial_002"],
        )
        self.assertEqual(second["input"]["budget"]["trials_used"], 2)
        continuation_request = client.completions.requests[1]
        continuation_messages = continuation_request["messages"]
        self.assertEqual(
            continuation_messages[: len(first["transcript"])],
            first["transcript"],
        )
        self.assertIn(
            "trial_002",
            continuation_messages[-1]["content"],
        )
        self.assertIsNone(second["output"]["next_obligation"])

    async def test_continues_researcher_transcript_with_review_feedback(
        self,
    ) -> None:
        """验证 Reviewer 反馈追加到原会话且沿用已检查证据账本。"""

        first_hypothesis = _hypothesis(
            intervention="Use append_user_message at post_tool."
        )
        revised_hypothesis = _hypothesis(
            intervention="Use defer_final_answer once at pre_final."
        )
        responses = [
            _tool_calls_message(
                [
                    (
                        "get_intervention_capabilities",
                        "call_capabilities",
                        {},
                    ),
                    (
                        "get_student_trajectory",
                        "call_trajectory_1",
                        {
                            "example_id": "example_1",
                            "replicate_id": "r000",
                        },
                    ),
                    (
                        "get_student_trajectory",
                        "call_trajectory_2",
                        {
                            "example_id": "example_2",
                            "replicate_id": "r000",
                        },
                    ),
                ]
            ),
            _tool_message(
                "submit_hypothesis_researcher_result",
                "call_submit_1",
                {
                    "scheme_action": "start_new",
                    "hypothesis": first_hypothesis,
                },
            ),
            _tool_message(
                "submit_hypothesis_researcher_result",
                "call_submit_2",
                {
                    "scheme_action": "revise_current",
                    "hypothesis": revised_hypothesis,
                },
            ),
        ]
        client = ReplayClient(responses)
        config = OpenAICompatibleConfig(
            base_url="https://teacher.invalid",
            model_id="teacher-test",
            max_tokens=512,
            temperature=0.4,
            seed=7,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report, rollout, template_root = _researcher_resources(root)
            runtime = NativeChatRoleRunner(
                max_turns=5,
                client=client,
                config=config,
            )
            artifact = await runtime.run(
                template_root=RESEARCHER_TEMPLATE,
                role_id="hypothesis_researcher",
                role_version=2,
                role_input=_researcher_input(),
                resource_config=TeacherResourceConfig(
                    report_dir=report,
                    rollout_file=rollout,
                    student_template_root=template_root,
                ),
            )
            frozen_instruction = "Frozen Researcher session instruction."
            frozen_digest = "f" * 64
            artifact["transcript"][0]["content"] = frozen_instruction
            artifact["base_prompt_digest"] = frozen_digest
            revision = await runtime.continue_researcher(
                previous_artifact=artifact,
                feedback_source="evidence_reviewer",
                feedback={
                    "decision": "revise",
                    "assessment": "The action did not change the next step.",
                    "key_risk": "The trigger is too early.",
                    "next_obligation": "Test one pre_final deferral.",
                },
            )

        self.assertEqual(artifact["role_session"]["revision"], 1)
        self.assertEqual(revision["role_session"]["revision"], 2)
        self.assertEqual(
            revision["role_session"]["session_id"],
            artifact["role_session"]["session_id"],
        )
        self.assertEqual(len(revision["role_session"]["output_history"]), 2)
        self.assertEqual(revision["base_prompt_digest"], frozen_digest)
        self.assertEqual(
            revision["role_session"]["feedback_history"][0]["payload"][
                "decision"
            ],
            "revise",
        )
        continuation_request = client.completions.requests[2]
        continuation_message = continuation_request["messages"][-1]
        self.assertEqual(
            continuation_request["messages"][0]["content"],
            frozen_instruction,
        )
        self.assertEqual(continuation_message["role"], "user")
        self.assertIn("evidence_reviewer", continuation_message["content"])
        self.assertIn(
            "Test one pre_final deferral.",
            continuation_message["content"],
        )
        self.assertEqual(
            revision["output"]["hypothesis"]["phase_plan"][0][
                "instruction"
            ],
            "Use defer_final_answer once at pre_final.",
        )

    async def test_runs_native_tool_loop_and_repairs_terminal_output(self) -> None:
        """验证原生 tool_call_id 循环、reasoning 保留和终态自我修正。"""

        responses = [
            _tool_calls_message(
                [
                    (
                        "get_trial_evidence",
                        "call_trial_1",
                        {"trial_ref": "trial_001"},
                    ),
                    (
                        "get_trial_evidence",
                        "call_trial_2",
                        {"trial_ref": "trial_001"},
                    ),
                ],
                reasoning="I will inspect the supplied evidence first.",
            ),
            _tool_message(
                "create_mechanism_draft",
                "call_1",
                {
                    "goal": "Continue evidence gathering.",
                },
            ),
            _tool_message(
                "add_mechanism_phase",
                "call_2",
                {
                    "draft_id": "mechanism_draft_001",
                    "phase": "post_tool",
                    "guards": [],
                    "predicate": "Is a required relation unsupported?",
                    "positive_rule": "The required relation is absent.",
                    "negative_rule": "The required relation is present.",
                    "uncertain_rule": "The inputs cannot establish either boundary.",
                    "positive_evidence": ["A required relation was absent."],
                    "negative_evidence": ["A required relation was present."],
                    "uncertain_evidence": [],
                    "decision_inputs": ["question", "latest tool result"],
                    "runtime_inputs": ["task", "tool", "persistent_state"],
                    "decision_evaluator": "deterministic",
                    "action": "Append a generic evidence-gap instruction.",
                    "fallback_negative": "Leave the decision unchanged.",
                    "fallback_uncertain": "Leave the decision unchanged.",
                    "fallback_budget_exhausted": "Leave the decision unchanged.",
                    "activation_budget": 1,
                },
            ),
            _tool_message(
                "complete_mechanism_draft",
                "call_3",
                {
                    "draft_id": "mechanism_draft_001",
                    "behavioral_pseudocode": (
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
                    "state_scope": "Until the next model generation.",
                    "expected_behavior": "Perform a relevant follow-up retrieval.",
                },
            ),
            _tool_message(
                "validate_mechanism_draft",
                "call_4",
                {
                    "draft_id": "mechanism_draft_001",
                    "evidence_refs": ["trial_001"],
                },
            ),
            _tool_message(
                "submit_mechanism_distillation",
                "call_5_invalid",
                {
                    "decision": "distilled",
                    "mechanism_ref": "mechanism_001",
                    "rationale": "The mechanism uses Student-visible inputs.",
                    "next_obligation": "No further work is required.",
                },
            ),
            _tool_message(
                "submit_mechanism_distillation",
                "call_6",
                {
                    "decision": "distilled",
                    "mechanism_ref": "mechanism_001",
                    "rationale": "The mechanism uses Student-visible inputs.",
                    "next_obligation": None,
                },
            ),
        ]
        client = ReplayClient(responses)
        config = OpenAICompatibleConfig(
            base_url="https://teacher.invalid",
            model_id="teacher-test",
            max_tokens=512,
            temperature=0.4,
            seed=7,
        )

        with tempfile.TemporaryDirectory() as directory:
            trial_file = Path(directory) / "trial_001" / "intervention.json"
            trial_file.parent.mkdir()
            trial_file.write_text(
                json.dumps(
                    {
                        "intent": "Prompt the Student to identify its evidence gap.",
                        "comparison": {"process_success": True},
                        "worker_summary": "The Student performed another retrieval.",
                    }
                ),
                encoding="utf-8",
            )
            artifact = await NativeChatRoleRunner(
                max_turns=8,
                client=client,
                config=config,
            ).run(
                template_root=DISTILLER_TEMPLATE,
                role_id="mechanism_distiller",
                role_version=1,
                role_input=_distiller_input(),
                resource_config=TeacherResourceConfig(
                    trial_files=[trial_file],
                ),
            )

        self.assertEqual(artifact["runtime"], "native_chat")
        self.assertEqual(artifact["output"]["decision"], "distilled")
        self.assertIn("mechanism_001", artifact["validated_mechanisms"])
        submissions = [
            call
            for call in artifact["tool_calls"]
            if call["name"] == "submit_mechanism_distillation"
        ]
        self.assertTrue(submissions[0]["metadata"]["validation_error"])
        self.assertTrue(submissions[1]["metadata"]["terminal"])
        self.assertEqual(artifact["usage"]["requests"], 7)
        self.assertEqual(artifact["usage"]["total_tokens"], 84)
        self.assertEqual(
            artifact["transcript"][2]["reasoning_content"],
            "I will inspect the supplied evidence first.",
        )
        self.assertFalse(client.closed)

        requests = client.completions.requests
        self.assertEqual(
            [
                item["tool_call_id"]
                for item in requests[1]["messages"][-2:]
            ],
            ["call_trial_1", "call_trial_2"],
        )
        terminal_schema = requests[0]["tools"][-1]["function"]
        self.assertEqual(
            terminal_schema["name"],
            "submit_mechanism_distillation",
        )
        self.assertNotIn("strict", terminal_schema)


def _tool_message(
    name: str,
    call_id: str,
    arguments: dict[str, Any],
    *,
    reasoning: str | None = None,
) -> ChatCompletionMessage:
    return _tool_calls_message(
        [(name, call_id, arguments)],
        reasoning=reasoning,
    )


def _tool_calls_message(
    calls: list[tuple[str, str, dict[str, Any]]],
    *,
    reasoning: str | None = None,
) -> ChatCompletionMessage:
    return ChatCompletionMessage(
        role="assistant",
        content=None,
        reasoning_content=reasoning,
        tool_calls=[
            ChatCompletionMessageFunctionToolCall(
                id=call_id,
                type="function",
                function=Function(
                    name=name,
                    arguments=json.dumps(arguments),
                ),
            )
            for name, call_id, arguments in calls
        ],
    )


def _distiller_input() -> dict[str, Any]:
    return {
        "hypothesis": {
            "trigger": "After a valid tool result lacks the target relation.",
            "trigger_phase": "post_tool",
            "intervention": "Ask the Student to identify the gap and continue.",
            "predicted_student_response": "A follow-up tool call occurs.",
            "evaluation": {
                "primary_signal": "tool_call_after_intervention",
                "success_condition": "One additional tool call occurs.",
                "falsifier": "The Student finalizes without another tool call.",
                "secondary_metrics": ["answer_score"],
            },
            "applicability": "Multi-hop cases with valid partial evidence.",
        },
        "review": {
            "decision": "ready_to_distill",
            "assessment": "The same mechanism produced the target behavior.",
            "key_risk": None,
            "next_obligation": None,
        },
        "trial_reviews": [
            {
                "trial_ref": "trial_001",
                "predicate_observations": [
                    {
                        "phase": "post_tool",
                        "predicate_label": "positive",
                        "decisive_observation": "The target relation was absent.",
                        "phase_execution": "intervention_applied",
                        "observed_effect": "The Student searched again.",
                        "outcome_evidence": "A follow-up tool call was recorded.",
                    }
                ],
                "assessment": "The intervention produced a follow-up search.",
            }
        ],
        "coverage_summary": {
            "required_distinct_examples": 3,
            "required_positive_per_phase": 2,
            "required_negative_per_phase": 2,
            "observed_distinct_examples": 3,
            "phase_coverage": [],
            "unmet_requirements": [],
            "special_obligations": [],
            "default_requirements_met": True,
        },
        "evidence_refs": ["trial_001"],
        "budget": _review_budget(trials_used=1),
        "capability_constraints": ["Student runtime cannot call Teacher."],
    }


def _hypothesis(*, intervention: str) -> dict[str, Any]:
    phase = (
        "pre_final"
        if "pre_final" in intervention
        else "post_tool"
    )
    return {
        "fork_phase": phase,
        "phase_plan": [
            {
                "phase": phase,
                "activation_condition": (
                    "Partial evidence is visible at the recoverable phase."
                ),
                "instruction": intervention,
                "expected_effect": (
                    "The Student performs another search."
                ),
                "max_activations": 1,
            }
        ],
        "evaluation": {
            "primary_signal": "next_parsed_output_kind",
            "success_condition": "The next output is a tool call.",
            "falsifier": "The next output is a final answer.",
            "secondary_metrics": ["total_tokens"],
        },
        "applicability": "Multi-hop cases with partial evidence.",
    }


def _researcher_input() -> dict[str, Any]:
    return {
        "problem_direction": {
            "pattern": "The Student stops after partial evidence.",
            "applicability": "Multi-hop cases with partial evidence.",
            "caveats": ["Corpus coverage may vary."],
            "evidence_refs": ["example_1/r000", "example_2/r000"],
        }
    }


def _review_budget(*, trials_used: int) -> dict[str, Any]:
    max_trials = 4
    max_assignments = 12
    assignments_used = trials_used
    return {
        "max_trials_per_hypothesis": max_trials,
        "trials_used": trials_used,
        "trials_remaining": max_trials - trials_used,
        "max_trial_assignments": max_assignments,
        "assignments_used": assignments_used,
        "assignments_remaining": max_assignments - assignments_used,
        "conclusion_required": trials_used == max_trials,
    }


def _researcher_resources(
    root: Path,
) -> tuple[Path, Path, Path]:
    report = root / "report"
    report.mkdir()
    rollout = root / "rollouts.jsonl"
    template_root = root / "template"
    template_root.mkdir()
    (report / "summary.json").write_text(
        json.dumps(
            {
                "source_file": str(rollout),
                "metrics": {},
                "provenance": {
                    "execution": {"rollouts_per_example": 1}
                },
            }
        ),
        encoding="utf-8",
    )
    cases = []
    records = []
    for example_id in ("example_1", "example_2"):
        cases.append(
            {
                "example_id": example_id,
                "question": "Question?",
                "replicates": [{"replicate_id": "r000", "score": 0}],
            }
        )
        records.append(
            {
                "example": {
                    "example_id": example_id,
                    "question": "Question?",
                },
                "replicate": {"replicate_id": "r000"},
                "run": {"status": "completed", "trace": []},
            }
        )
    (report / "per_example.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in cases),
        encoding="utf-8",
    )
    rollout.write_text(
        "".join(json.dumps(item) + "\n" for item in records),
        encoding="utf-8",
    )
    (template_root / "harness.json").write_text(
        json.dumps(
            {
                "harness_id": "student",
                "tools": [],
                "extensions": [],
            }
        ),
        encoding="utf-8",
    )
    return report, rollout, template_root


def _trial_file(root: Path, trial_ref: str) -> Path:
    path = root / trial_ref / "worker.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "input": {"trial_objective": "Test the frozen hypothesis."},
                "output": {
                    "result_kind": "executed",
                    "action": "append_user_message",
                    "content": "Continue.",
                    "rationale": "Applied the assigned action.",
                },
                "resource_artifacts": {
                    "intervention_trial": {
                        "source": {},
                        "action": {
                            "action": "append_user_message",
                            "content": "Continue.",
                            "rationale": "Applied the assigned action.",
                        },
                        "context_changes": [],
                        "branch_run": {
                            "status": "completed",
                            "trace": [],
                        },
                        "comparison": {
                            "source": {"status": "completed"},
                            "branch": {"status": "completed"},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
