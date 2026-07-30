"""Compiler capability packet 的选择与资源注入测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from search_harness.teacher.compiler_capabilities import (
    build_compiler_capability_packet,
)
from search_harness.teacher.contracts import CompilerInput, MechanismSpec
from search_harness.teacher.resources import (
    CompilerResourceConfig,
    TeacherResourceConfig,
    TeacherResources,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PLUGINS = (
    PROJECT_ROOT / "harness_templates" / "actor" / "baseline" / "plugins"
)


class CompilerCapabilityPacketTest(unittest.TestCase):
    def test_packet_selects_phase_and_exact_required_contracts(self) -> None:
        """验证能力包只装入当前 phase 和显式请求的公开契约。"""

        packet = build_compiler_capability_packet(
            _mechanism(
                trigger_phase="post_prompt",
                decision_inputs=["stage.model_input", "semantic flag"],
                required_capabilities=[
                    "ModelInput.from_messages",
                    "ChatMessage",
                ],
            )
        )
        symbols = {item["symbol"] for item in packet["contracts"]}

        self.assertIn("HookPhase.POST_PROMPT", symbols)
        self.assertIn("stage.model_input", symbols)
        self.assertIn("ModelInput.from_messages", symbols)
        self.assertNotIn("ToolResult", symbols)
        self.assertNotIn("HookContext.call_model", symbols)
        phase_rule = packet["selection"]["phase_rules"][0]
        self.assertEqual(
            phase_rule["decision_evaluator"],
            "deterministic",
        )
        self.assertEqual(
            phase_rule["semantic_decision_inputs"],
            ["semantic flag"],
        )

    def test_packet_adds_model_rules_only_for_model_capabilities(self) -> None:
        """验证 hook_model evaluator 无需关键词即可装入模型调用契约。"""

        packet = build_compiler_capability_packet(
            _mechanism(
                trigger_phase="post_tool",
                decision_inputs=["stage.tool_result"],
                required_capabilities=[],
                decision_evaluator="hook_model",
            )
        )

        self.assertIn("model_inference_rules", packet["authoring"])
        self.assertEqual(
            packet["authoring"]["allowed_model_profiles"],
            ["student"],
        )
        phase_rule = packet["selection"]["phase_rules"][0]
        self.assertEqual(
            phase_rule["decision_evaluator"],
            "hook_model",
        )
        symbols = {item["symbol"] for item in packet["contracts"]}
        self.assertIn("HookContext.call_model", symbols)
        self.assertIn("HookModelResponse.json_object", symbols)

    def test_packet_preserves_semantic_actor_capabilities(self) -> None:
        """验证自然语言 Actor 能力不会被误判为缺失的框架 API。"""

        packet = build_compiler_capability_packet(
            _mechanism(
                trigger_phase="pre_final",
                decision_inputs=["question text", "visible passages"],
                required_capabilities=[
                    "Actor can follow feedback and call search",
                    "FinalDecision.defer",
                ],
            )
        )

        selection = packet["selection"]
        self.assertEqual(
            selection["semantic_required_capabilities"],
            ["Actor can follow feedback and call search"],
        )
        self.assertEqual(selection["unresolved_api_capabilities"], [])
        symbols = {item["symbol"] for item in packet["contracts"]}
        self.assertIn("FinalDecision.defer", symbols)

    def test_compiler_input_binds_packet_into_model_context(self) -> None:
        """验证程序从 CompilerInput 构造并注入只读能力包。"""

        resources = TeacherResources.from_config(
            TeacherResourceConfig(
                compiler=CompilerResourceConfig(
                    parent_plugins_root=BASELINE_PLUGINS,
                    env_file=PROJECT_ROOT / ".env",
                )
            )
        )
        role_input = CompilerInput(
            mechanism=_mechanism(
                trigger_phase="pre_final",
                decision_inputs=["stage.final_decision"],
                required_capabilities=["FinalDecision.defer"],
            )
        )

        resources.bind_role_input(role_input)
        context = resources.model_context("compiler")

        packet = context["compiler"]["capability_packet"]
        self.assertEqual(
            packet["selection"]["phase_rules"][0]["phase"],
            "pre_final",
        )
        self.assertEqual(packet["selection"]["unresolved_symbols"], [])

    def test_packet_unions_contracts_for_mixed_phase_evaluators(self) -> None:
        """验证多 phase 机制同时保留确定性与小模型判断所需的最小契约。"""

        mechanism = MechanismSpec(
            goal="Carry one evidence-gap state into finalization.",
            phase_rules=[
                {
                    "phase": "post_tool",
                    "trigger_condition": "A visible relation is unsupported.",
                    "decision_inputs": ["stage.tool_result", "question text"],
                    "decision_evaluator": "hook_model",
                    "action": "Record the visible evidence gap.",
                    "activation_budget": 1,
                },
                {
                    "phase": "pre_final",
                    "trigger_condition": "The recorded gap remains open.",
                    "decision_inputs": [
                        "stage.final_decision",
                        "extension.gap_open",
                    ],
                    "decision_evaluator": "deterministic",
                    "action": "Defer finalization once.",
                    "activation_budget": 1,
                },
            ],
            behavioral_pseudocode=(
                "ON post_tool classify the visible gap; "
                "ON pre_final defer once while gap_open."
            ),
            state_scope="One rollout-local gap flag.",
            fallback="Leave the active stage unchanged.",
            expected_behavior="The Actor retrieves before finalizing.",
            evidence_refs=["trial_001"],
        )

        packet = build_compiler_capability_packet(mechanism)

        self.assertEqual(
            [
                item["decision_evaluator"]
                for item in packet["selection"]["phase_rules"]
            ],
            ["hook_model", "deterministic"],
        )
        symbols = {item["symbol"] for item in packet["contracts"]}
        self.assertIn("HookPhase.POST_TOOL", symbols)
        self.assertIn("HookPhase.PRE_FINAL", symbols)
        self.assertIn("HookContext.call_model", symbols)


def _mechanism(
    *,
    trigger_phase: str,
    decision_inputs: list[str],
    required_capabilities: list[str],
    decision_evaluator: str = "deterministic",
) -> MechanismSpec:
    return MechanismSpec(
        goal="Test one bounded mechanism.",
        trigger_phase=trigger_phase,
        trigger_condition="The selected phase is reached.",
        decision_inputs=decision_inputs,
        decision_evaluator=decision_evaluator,
        action="Apply one bounded context intervention.",
        behavioral_pseudocode=(
            "ON selected_phase:\n"
            "  IF activation remains:\n"
            "    apply the intervention"
        ),
        state_scope="One rollout-local activation flag.",
        fallback="Leave the current stage value unchanged.",
        expected_behavior="The Actor receives the bounded intervention.",
        evidence_refs=["trial:test"],
        activation_budget=1,
        required_capabilities=required_capabilities,
        prohibited_behaviors=["Do not inject an answer."],
        observability=["Hook activation is traced."],
        known_limits=["Only the selected phase was tested."],
    )
