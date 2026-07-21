from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.adapter.critic import (
    build_critic_loop,
    parse_critic_result,
    run_critic,
)
from search_harness.core import ModelInput
from search_harness.registry import build_harness

from tests.adapter.critic.test_context import _make_context


CRITIC_PLUGINS_ROOT = (
    Path(__file__).parents[3] / "harness_templates" / "adapter" / "critic" / "baseline" / "plugins"
)


class SequenceModel:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.inputs: list[ModelInput] = []

    def generate(self, model_input: ModelInput) -> str:
        self.inputs.append(model_input)
        return self.outputs.pop(0)


class CriticRuntimeTest(TestCase):
    def test_external_plugins_assemble_with_bound_context(self) -> None:
        """Verifies the external plugins assemble with bound context contract."""
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))

            components = build_harness(
                CRITIC_PLUGINS_ROOT,
                runtime_context=context,
            )
            prompt = components.prompt_builder.build(_state())

        self.assertEqual(
            [definition.name for definition in components.tools.definitions],
            [
                "list_evaluation_cases",
                "get_case_evaluation",
                "get_case_trajectory",
                "get_harness_manifest",
                "get_harness_component",
                "list_comparison_cases",
                "get_comparison_case",
                "get_comparison_trajectory",
                "get_harness_change_summary",
            ],
        )
        self.assertEqual(
            [hook.hook_id for hook in components.hooks.hooks],
            ["format_error_feedback", "turn_budget_notice"],
        )
        self.assertIn('"harness_version": "harness_v0002"', prompt.messages[1].content)
        self.assertNotIn("Question one?", prompt.messages[1].content)
        self.assertIn(
            "first write a concise plain-text analysis or statement of intent",
            prompt.messages[0].content,
        )
        self.assertIn("observed_pattern", prompt.messages[0].content)

    def test_loop_browses_case_index_then_returns_critic_result(self) -> None:
        """Verifies the loop browses case index then returns critic result contract."""
        model = SequenceModel(
            [
                '<tool_call>{"name":"list_evaluation_cases","arguments":{"score":0}}</tool_call>',
                '<final_answer>{"analysis":"A repeated process issue needs review.",'
                '"problem_directions":[{"problem":"Premature completion",'
                '"observed_pattern":"Repeated cases stop early.",'
                '"excluded_causes":[],"desired_behavior":"Continue when needed.",'
                '"success_criteria":["More completed evidence chains."],'
                '"constraints":[]}],"evidence_requests":[],"review":null}</final_answer>',
            ]
        )
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))
            loop = build_critic_loop(
                critic_context=context,
                plugins_root=CRITIC_PLUGINS_ROOT,
                model=model,
                max_steps=3,
            )

            run, result = run_critic(loop, "Find repeated failures.")

        self.assertEqual(run.status.value, "completed")
        self.assertEqual(
            result.problem_directions[0]["problem"], "Premature completion"
        )
        self.assertEqual(len(model.inputs), 2)
        self.assertIn('"total_pages": 1', model.inputs[1].messages[-2].content)
        self.assertEqual(model.inputs[1].messages[-1].content, "Turn budget: this is step 2 of 3.")
        self.assertEqual(model.inputs[0].messages[-1].content, "Turn budget: this is step 1 of 3.")

    def test_final_turn_budget_notice_requires_final_answer(self) -> None:
        """Verifies the final turn budget notice requires final answer contract."""
        model = SequenceModel(
            [
                '<final_answer>{"analysis":"Conclude now.",'
                '"problem_directions":[],"evidence_requests":[],"review":null}</final_answer>'
            ]
        )
        with TemporaryDirectory() as tmpdir:
            loop = build_critic_loop(
                critic_context=_make_context(Path(tmpdir)),
                plugins_root=CRITIC_PLUGINS_ROOT,
                model=model,
                max_steps=1,
            )

            run, _ = run_critic(loop, "Find repeated failures.")

        self.assertEqual(run.status.value, "completed")
        self.assertEqual(
            model.inputs[0].messages[-1].content,
            "Turn budget: this is step 1 of 1. This is the final allowed turn. "
            "Complete the current analysis and return <final_answer>; do not call another tool.",
        )

    def test_result_guard_requests_missing_direction_field(self) -> None:
        """验证 Critic 缺失必填证据时在同一对话内收到精确修复反馈。"""

        model = SequenceModel(
            [
                '<final_answer>{"analysis":"Incomplete.","problem_directions":['
                '{"problem":"Stops early","observed_pattern":"Repeated failures",'
                '"excluded_causes":[],"desired_behavior":"Continue",'
                '"success_criteria":[]}],"evidence_requests":[],"review":null}'
                '</final_answer>',
                '<final_answer>{"analysis":"Complete.","problem_directions":['
                '{"problem":"Stops early","observed_pattern":"Repeated failures",'
                '"excluded_causes":[],"desired_behavior":"Continue",'
                '"success_criteria":[],"constraints":[]}],'
                '"evidence_requests":[],"review":null}</final_answer>',
            ]
        )
        with TemporaryDirectory() as tmpdir:
            loop = build_critic_loop(
                critic_context=_make_context(Path(tmpdir)),
                plugins_root=CRITIC_PLUGINS_ROOT,
                model=model,
                max_steps=2,
            )

            run, result = run_critic(loop, "Find repeated failures.")

        self.assertEqual(run.status.value, "completed")
        self.assertEqual(result.problem_directions[0]["constraints"], [])
        self.assertIn("constraints", model.inputs[1].messages[-2].content)

    def test_critic_request_timeout_overrides_model_role_timeout(self) -> None:
        """Verifies the critic request timeout overrides model role timeout contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_file = root / "critic.env"
            env_file.write_text(
                "\n".join(
                    [
                        "TEACHER_BASE_URL=https://example.test/v1",
                        "TEACHER_MODEL_ID=test-critic",
                        "TEACHER_REQUEST_TIMEOUT=10",
                        "CRITIC_REQUEST_TIMEOUT=42",
                    ]
                ),
                encoding="utf-8",
            )
            loop = build_critic_loop(
                critic_context=_make_context(root),
                plugins_root=CRITIC_PLUGINS_ROOT,
                env_file=env_file,
            )

        self.assertEqual(loop.model.config.timeout, 42.0)

    def test_rejects_non_object_final_artifact(self) -> None:
        """Verifies the rejects non object final artifact contract."""
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_critic_result("[]")


def _state():
    from search_harness.core import AgentState

    return AgentState(question="Analyze.", max_steps=2)
