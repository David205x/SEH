"""NativeChatTeacherRuntime 的离线原生工具协议测试。"""

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

from search_harness.models import OpenAICompatibleConfig
from search_harness.teacher.native_runtime import NativeChatTeacherRuntime
from search_harness.teacher.resources import TeacherResourceConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISTILLER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "mechanism_distiller"
    / "plugins"
)
RESEARCHER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "hypothesis_researcher"
    / "plugins"
)
REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "evidence_reviewer"
    / "plugins"
)
TRIAL_REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "trial_reviewer"
    / "plugins"
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


class NativeTeacherRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_trial_reviewer_must_read_its_single_full_trial(
        self,
    ) -> None:
        """验证单条审阅必须先读取其绑定的完整 Worker 轨迹。"""

        review = {
            "trial_ref": "trial_001",
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
            artifact = await NativeChatTeacherRuntime(
                max_turns=5,
                client=client,
                config=config,
            ).run(
                template_root=TRIAL_REVIEWER_TEMPLATE,
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

        runtime = NativeChatTeacherRuntime(
            max_turns=5,
            client=client,
            config=config,
        )
        first = await runtime.run(
            template_root=REVIEWER_TEMPLATE,
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
                        "get_actor_trajectory",
                        "call_trajectory_1",
                        {
                            "example_id": "example_1",
                            "replicate_id": "r000",
                            "view": "behavior",
                        },
                    ),
                    (
                        "get_actor_trajectory",
                        "call_trajectory_2",
                        {
                            "example_id": "example_2",
                            "replicate_id": "r000",
                            "view": "behavior",
                        },
                    ),
                ]
            ),
            _tool_message(
                "submit_intervention_hypothesis",
                "call_submit_1",
                first_hypothesis,
            ),
            _tool_message(
                "submit_intervention_hypothesis",
                "call_submit_2",
                revised_hypothesis,
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
            report, rollout, plugins = _researcher_resources(root)
            runtime = NativeChatTeacherRuntime(
                max_turns=5,
                client=client,
                config=config,
            )
            artifact = await runtime.run(
                template_root=RESEARCHER_TEMPLATE,
                role_input=_researcher_input(),
                resource_config=TeacherResourceConfig(
                    report_dir=report,
                    rollout_file=rollout,
                    actor_plugins_root=plugins,
                ),
            )
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
        self.assertEqual(
            revision["role_session"]["feedback_history"][0]["payload"][
                "decision"
            ],
            "revise",
        )
        continuation_request = client.completions.requests[2]
        continuation_message = continuation_request["messages"][-1]
        self.assertEqual(continuation_message["role"], "user")
        self.assertIn("evidence_reviewer", continuation_message["content"])
        self.assertIn(
            "Test one pre_final deferral.",
            continuation_message["content"],
        )
        self.assertEqual(
            revision["output"]["phase_plan"][0]["instruction"],
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
                    "trigger_condition": "A required relation is unsupported.",
                    "decision_inputs": ["question", "latest tool result"],
                    "decision_evaluator": "deterministic",
                    "action": "Append a generic evidence-gap instruction.",
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
                    "fallback": "Do nothing when uncertain.",
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
                    "rationale": "The mechanism uses Actor-visible inputs.",
                    "next_obligation": "No further work is required.",
                },
            ),
            _tool_message(
                "submit_mechanism_distillation",
                "call_6",
                {
                    "decision": "distilled",
                    "mechanism_ref": "mechanism_001",
                    "rationale": "The mechanism uses Actor-visible inputs.",
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
                        "intent": "Prompt the Actor to identify its evidence gap.",
                        "comparison": {"process_success": True},
                        "worker_summary": "The Actor performed another retrieval.",
                    }
                ),
                encoding="utf-8",
            )
            artifact = await NativeChatTeacherRuntime(
                max_turns=8,
                client=client,
                config=config,
            ).run(
                template_root=DISTILLER_TEMPLATE,
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
            "intervention": "Ask the Actor to identify the gap and continue.",
            "predicted_actor_response": "A follow-up tool call occurs.",
            "evaluation": {
                "primary_signal": "tool_call_after_intervention",
                "success_condition": "One additional tool call occurs.",
                "falsifier": "The Actor finalizes without another tool call.",
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
        "evidence_refs": ["trial_001"],
        "capability_constraints": ["Actor runtime cannot call Teacher."],
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
                    "The Actor performs another search."
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
            "pattern": "The Actor stops after partial evidence.",
            "applicability": "Multi-hop cases with partial evidence.",
            "caveats": ["Corpus coverage may vary."],
            "evidence_refs": ["example_1/r000", "example_2/r000"],
        }
    }


def _researcher_resources(
    root: Path,
) -> tuple[Path, Path, Path]:
    report = root / "report"
    report.mkdir()
    rollout = root / "rollouts.jsonl"
    plugins = root / "plugins"
    plugins.mkdir()
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
    (plugins / "harness.json").write_text(
        json.dumps(
            {
                "harness_id": "actor",
                "tools": [],
                "extensions": [],
            }
        ),
        encoding="utf-8",
    )
    return report, rollout, plugins


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
