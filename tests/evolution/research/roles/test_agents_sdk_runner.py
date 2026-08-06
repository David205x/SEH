"""OpenAI Agents SDK Teacher runtime 的离线回放测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, AsyncIterator

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.cli import _read_request
from search_harness.evolution.research.roles.agents_sdk_runner import (
    AgentsSdkRoleRunner,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DISTILLER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "mechanism_distiller"
)


class MechanismReplayModel(Model):
    """按顺序回放三次原生工具调用和一个结构化最终结果。"""

    def __init__(self, trial_ref: str) -> None:
        self._turn = 0
        self._trial_ref = trial_ref

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self._turn += 1
        if self._turn == 1:
            output = [
                _tool_call(
                    "create_mechanism_draft",
                    "call_1",
                    {
                        "goal": "Continue evidence gathering.",
                    },
                )
            ]
        elif self._turn == 2:
            output = [
                _tool_call(
                    "add_mechanism_phase",
                    "call_2",
                    {
                        "draft_id": "mechanism_draft_001",
                        "phase": "post_tool",
                        "trigger_condition": "The target relation is absent.",
                        "decision_inputs": ["question", "latest tool result"],
                        "runtime_inputs": ["task", "tool", "persistent_state"],
                        "decision_evaluator": "deterministic",
                        "action": "Append a generic evidence-gap instruction.",
                        "activation_budget": 1,
                    },
                )
            ]
        elif self._turn == 3:
            output = [
                _tool_call(
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
                )
            ]
        elif self._turn == 4:
            output = [
                _tool_call(
                    "validate_mechanism_draft",
                    "call_4",
                    {
                        "draft_id": "mechanism_draft_001",
                        "evidence_refs": [self._trial_ref],
                    },
                )
            ]
        else:
            output = [
                _tool_call(
                    "submit_mechanism_distillation",
                    "call_5",
                    {
                        "decision": "distilled",
                        "mechanism_ref": "mechanism_001",
                        "rationale": "The mechanism uses only Student-visible inputs.",
                        "next_obligation": None,
                    },
                )
            ]
        return ModelResponse(
            output=output,
            usage=Usage(),
            response_id=None,
        )

    async def stream_response(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        if False:
            yield None


class InvalidThenCorrectedOutputModel(MechanismReplayModel):
    """先提交语义冲突终态，再根据工具错误重试。"""

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self._turn += 1
        if self._turn <= 4:
            self._turn -= 1
            return await super().get_response(*args, **kwargs)
        if self._turn == 5:
            output = [
                _tool_call(
                    "submit_mechanism_distillation",
                    "call_5_invalid",
                    {
                        "decision": "distilled",
                        "mechanism_ref": "mechanism_001",
                        "rationale": "The mechanism is portable.",
                        "next_obligation": "No further work is required.",
                    },
                )
            ]
        else:
            output = [
                _tool_call(
                    "submit_mechanism_distillation",
                    "call_6",
                    {
                        "decision": "distilled",
                        "mechanism_ref": "mechanism_001",
                        "rationale": "The mechanism is portable.",
                        "next_obligation": None,
                    },
                )
            ]
        return ModelResponse(
            output=output,
            usage=Usage(),
            response_id=None,
        )


class AgentsSdkRoleRunnerTest(unittest.IsolatedAsyncioTestCase):
    def test_cli_reads_windows_utf8_bom_request(self) -> None:
        """验证 Windows PowerShell 产生的 UTF-8 BOM request 可以被显式解码。"""

        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            request.write_text(
                json.dumps({"input": {}, "resources": {}}),
                encoding="utf-8-sig",
            )

            payload = _read_request(request)

        self.assertEqual(payload["resources"], {})

    async def test_distiller_builds_and_returns_validated_mechanism(self) -> None:
        """验证 SDK 工具循环与结构化输出共同生成可解析 MechanismSpec。"""

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
            role_input = {
                "hypothesis": {
                    "trigger": "After a valid tool result lacks the target relation.",
                    "trigger_phase": "post_tool",
                    "intervention": "Ask the Student to identify the gap and continue.",
                    "predicted_student_response": "A follow-up tool call occurs.",
                    "evaluation": {
                        "primary_signal": "tool_call_after_intervention",
                        "success_condition": "One additional tool call occurs.",
                        "falsifier": (
                            "The Student finalizes without another tool call."
                        ),
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
                "budget": _review_budget(trials_used=1),
                "capability_constraints": ["Student runtime cannot call Teacher."],
            }
            artifact = await AgentsSdkRoleRunner(max_turns=8).run(
                template_root=DISTILLER_TEMPLATE,
                role_id="mechanism_distiller",
                role_version=1,
                role_input=role_input,
                resource_config=TeacherResourceConfig(
                    trial_files=[trial_file],
                ),
                model=MechanismReplayModel("trial_001"),
            )

        self.assertEqual(artifact["output"]["decision"], "distilled")
        self.assertIn("mechanism_001", artifact["validated_mechanisms"])
        self.assertIn(
            "ACTOR_OBLIGATION_AFTER_DEFER",
            artifact["validated_mechanisms"]["mechanism_001"][
                "behavioral_pseudocode"
            ],
        )
        self.assertEqual(
            [call["name"] for call in artifact["tool_calls"]],
            [
                "create_mechanism_draft",
                "add_mechanism_phase",
                "complete_mechanism_draft",
                "validate_mechanism_draft",
                "submit_mechanism_distillation",
            ],
        )

    async def test_invalid_terminal_output_is_returned_for_correction(self) -> None:
        """验证跨字段协议错误会反馈给模型，而不是直接终止角色运行。"""

        with tempfile.TemporaryDirectory() as directory:
            trial_file = Path(directory) / "trial_001" / "intervention.json"
            trial_file.parent.mkdir()
            trial_file.write_text(
                json.dumps(
                    {
                        "intent": "Test a generic evidence-gap instruction.",
                        "comparison": {"process_success": True},
                        "worker_summary": "The Student continued retrieval.",
                    }
                ),
                encoding="utf-8",
            )
            artifact = await AgentsSdkRoleRunner(max_turns=8).run(
                template_root=DISTILLER_TEMPLATE,
                role_id="mechanism_distiller",
                role_version=1,
                role_input=_distiller_input(),
                resource_config=TeacherResourceConfig(
                    trial_files=[trial_file],
                ),
                model=InvalidThenCorrectedOutputModel("trial_001"),
            )

        submissions = [
            call
            for call in artifact["tool_calls"]
            if call["name"] == "submit_mechanism_distillation"
        ]
        self.assertEqual(len(submissions), 2)
        self.assertTrue(submissions[0]["metadata"]["validation_error"])
        self.assertTrue(submissions[1]["metadata"]["terminal"])
        self.assertIsNone(artifact["output"]["next_obligation"])


def _tool_call(
    name: str,
    call_id: str,
    arguments: dict[str, Any],
) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        arguments=json.dumps(arguments),
        call_id=call_id,
        name=name,
        type="function_call",
        status="completed",
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
        "evidence_refs": ["trial_001"],
        "budget": _review_budget(trials_used=1),
        "capability_constraints": ["Student runtime cannot call Teacher."],
    }


def _review_budget(*, trials_used: int) -> dict[str, Any]:
    max_trials = 4
    max_assignments = 12
    return {
        "max_trials_per_hypothesis": max_trials,
        "trials_used": trials_used,
        "trials_remaining": max_trials - trials_used,
        "max_trial_assignments": max_assignments,
        "assignments_used": trials_used,
        "assignments_remaining": max_assignments - trials_used,
        "conclusion_required": trials_used == max_trials,
    }


if __name__ == "__main__":
    unittest.main()
