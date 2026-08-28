"""Dedicated persistent Intervention Worker runtime tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
    _worker_result,
)
from search_harness.evolution.research.roles.contracts import (
    InterventionHypothesis,
)
from search_harness.evolution.research.roles.provenance import (
    input_view_digest,
    teacher_role_scope_from_artifact,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.resources.stores import (
    InterventionResourceConfig,
)
from search_harness.integrations.openai_compatible import OpenAICompatibleConfig

from tests.evolution.research.intervention.test_prefix import _write_rollout


PROJECT_ROOT = Path(__file__).resolve().parents[4]
WORKER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "intervention_worker"
)


class _FakeRunner:
    """Return one complete multi-phase branch and retain runtime arguments."""

    last_kwargs: dict[str, Any] | None = None

    def __init__(
        self,
        _config: object,
        *,
        teacher_config: object | None = None,
    ) -> None:
        pass

    def run(self, **kwargs: Any) -> dict[str, Any]:
        type(self).last_kwargs = kwargs
        return {
            "source": {
                "rollout_file": str(kwargs["rollout_file"]),
                "example_id": kwargs["example_id"],
                "replicate_id": kwargs["replicate_id"],
                "fork_step": kwargs["fork_step"],
                "fork_phase": kwargs["fork_phase"],
            },
            "runtime": {
                "teacher_model": {
                    "provider": "test",
                    "model_id": "teacher-test",
                },
            },
            "activation_budgets": {
                "post_tool": 1,
                "pre_final": 1,
            },
            "activation_counts": {
                "post_tool": 1,
                "pre_final": 1,
            },
            "intervention_changes": [
                {
                    "phase": "post_tool",
                    "action": {"kind": "append_context_message"},
                },
                {
                    "phase": "pre_final",
                    "action": {"kind": "replace_stage_value"},
                },
            ],
            "branch_run": {
                "status": "completed",
                "answer": "J. R. R. Tolkien",
                "trace": [],
            },
            "comparison": {
                "source": {
                    "status": "completed",
                    "answer": "Shakespeare",
                    "execution": {"model_calls": 2, "tool_calls": 1},
                },
                "branch": {
                    "status": "completed",
                    "answer": "J. R. R. Tolkien",
                    "score": 1,
                    "execution": {
                        "model_calls": 2,
                        "tool_calls": 0,
                        "tokens": {"total_tokens": 20},
                    },
                },
            },
            "worker_trace": [
                {
                    "event_type": "worker_model_output",
                    "model_input": {
                        "messages": [
                            {"role": "system", "content": "worker"},
                            {"role": "user", "content": "compact view"},
                        ],
                        "tools": [],
                    },
                    "metadata": {"usage": {"total_tokens": 10}},
                }
            ],
        }


class InterventionRoleRunnerTest(unittest.IsolatedAsyncioTestCase):
    def test_reached_no_change_is_a_completed_trial(self) -> None:
        """正确保持上下文不变仍保留为可审查的负对照。"""

        result = _worker_result(
            InterventionHypothesis.model_validate(_hypothesis()),
            {
                "activation_counts": {"post_tool": 1, "pre_final": 0},
                "intervention_changes": [
                    {
                        "phase": "post_tool",
                        "action": {"kind": "continue_without_change"},
                    }
                ],
            },
        )

        self.assertEqual(result.result_kind, "executed")
        self.assertEqual(result.activated_phases, ["post_tool"])
        self.assertEqual(result.modified_phases, [])
        self.assertEqual(result.unmet_phases, ["pre_final"])

    async def test_wraps_one_persistent_branch_as_worker_contract(self) -> None:
        """验证正式角色运行时只按分支事实生成 v4 输出。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            with (
                patch(
                    "search_harness.evolution.research.intervention.role_runner.InterventionRunner",
                    _FakeRunner,
                ),
                patch(
                    "search_harness.evolution.research.intervention.role_runner.OpenAICompatibleConfig.from_env",
                    return_value=OpenAICompatibleConfig(
                        base_url="https://teacher.invalid",
                        model_id="teacher-test",
                    ),
                ),
            ):
                artifact = await InterventionRoleRunner(
                    env_file=root / ".env",
                    max_steps_per_activation=4,
                    teacher_judge=False,
                ).run(
                    template_root=WORKER_TEMPLATE,
                    role_input={
                        "hypothesis": _hypothesis(),
                        "trial_objective": (
                            "Test a two-phase evidence-gap intervention."
                        ),
                        "example_id": "example-1",
                        "replicate_id": "r000",
                        "prefix_id": 5,
                        "prohibited_content": ["golden answer"],
                    },
                    resource_config=TeacherResourceConfig(
                        intervention=InterventionResourceConfig(
                            rollout_file=rollout_file,
                            student_template_root=root / "template",
                            env_file=root / ".env",
                            student_max_steps=4,
                        )
                    ),
                )

        self.assertEqual(
            artifact["output_contract"],
            {
                "id": "intervention_worker_result",
                "version": 4,
                "schema_digest": artifact["output_contract"][
                    "schema_digest"
                ],
            },
        )
        self.assertEqual(artifact["schema_version"], 2)
        self.assertEqual(
            teacher_role_scope_from_artifact(artifact).role_id,
            "intervention_worker",
        )
        self.assertEqual(
            artifact["input_view_digest"],
            input_view_digest(
                [
                    {
                        "messages": [
                            {"role": "system", "content": "worker"},
                            {"role": "user", "content": "compact view"},
                        ],
                        "tools": [],
                    }
                ]
            ),
        )
        self.assertEqual(len(artifact["base_prompt_digest"]), 64)
        self.assertEqual(artifact["output"]["result_kind"], "executed")
        self.assertEqual(
            artifact["output"]["activated_phases"],
            ["post_tool", "pre_final"],
        )
        self.assertEqual(
            artifact["output"]["modified_phases"],
            ["post_tool", "pre_final"],
        )
        self.assertEqual(artifact["output"]["unmet_phases"], [])
        self.assertNotIn("summary", artifact["output"])
        self.assertNotIn(
            "worker_summary",
            artifact["resource_artifacts"]["intervention_trial"],
        )
        self.assertEqual(artifact["usage"]["total_tokens"], 30)
        self.assertIsNotNone(_FakeRunner.last_kwargs)
        assert _FakeRunner.last_kwargs is not None
        self.assertEqual(
            _FakeRunner.last_kwargs["activation_budgets"],
            {"post_tool": 1, "pre_final": 1},
        )
        self.assertFalse(_FakeRunner.last_kwargs["persist"])
        self.assertIn(
            "same Worker session",
            _FakeRunner.last_kwargs["system_prompt_template"],
        )


def _hypothesis() -> dict[str, Any]:
    return {
        "fork_phase": "post_tool",
        "phase_plan": [
            {
                "phase": "post_tool",
                "activation_condition": "A visible relation is unsupported.",
                "instruction": "Mark the unsupported relation.",
                "expected_effect": "The Student identifies an evidence gap.",
                "max_activations": 1,
            },
            {
                "phase": "pre_final",
                "activation_condition": "The evidence gap remains unresolved.",
                "instruction": "Defer finalization once.",
                "expected_effect": "The Student retrieves before finalizing.",
                "max_activations": 1,
            },
        ],
        "evaluation": {
            "primary_signal": "tool_call_after_intervention",
            "success_condition": "A retrieval occurs before finalization.",
            "falsifier": "The Student finalizes with an unresolved gap.",
            "secondary_metrics": ["total_tokens"],
        },
        "applicability": "Multi-hop retrieval with partial visible evidence.",
    }


if __name__ == "__main__":
    unittest.main()
