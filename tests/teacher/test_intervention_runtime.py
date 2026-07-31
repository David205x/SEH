"""Dedicated persistent Intervention Worker runtime tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from search_harness.teacher.intervention_runtime import (
    InterventionRoleRuntime,
)
from search_harness.teacher.resources import TeacherResourceConfig
from search_harness.teacher.role_resources import (
    InterventionResourceConfig,
)

from tests.teacher.test_intervention_prefix import _write_rollout


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "intervention_worker"
    / "plugins"
)


class _FakeRunner:
    """Return one complete multi-phase branch and retain runtime arguments."""

    last_kwargs: dict[str, Any] | None = None

    def __init__(self, _config: object) -> None:
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
                "teacher_model": {"role": "teacher", "model_id": "test"},
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
                    "metadata": {"usage": {"total_tokens": 10}},
                }
            ],
        }


class InterventionRoleRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_wraps_one_persistent_branch_as_worker_contract(self) -> None:
        """验证正式角色运行时只按分支事实生成 v3 输出。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            with patch(
                "search_harness.teacher.intervention_runtime.InterventionRunner",
                _FakeRunner,
            ):
                artifact = await InterventionRoleRuntime(
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
                            actor_plugins_root=root / "plugins",
                            env_file=root / ".env",
                            actor_max_steps=4,
                        )
                    ),
                )

        self.assertEqual(
            artifact["output_contract"],
            {
                "id": "intervention_worker_result",
                "version": 3,
                "schema_digest": artifact["output_contract"][
                    "schema_digest"
                ],
            },
        )
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
            "same Worker transcript",
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
                "expected_effect": "The Actor identifies an evidence gap.",
                "max_activations": 1,
            },
            {
                "phase": "pre_final",
                "activation_condition": "The evidence gap remains unresolved.",
                "instruction": "Defer finalization once.",
                "expected_effect": "The Actor retrieves before finalizing.",
                "max_activations": 1,
            },
        ],
        "evaluation": {
            "primary_signal": "tool_call_after_intervention",
            "success_condition": "A retrieval occurs before finalization.",
            "falsifier": "The Actor finalizes with an unresolved gap.",
            "secondary_metrics": ["total_tokens"],
        },
        "applicability": "Multi-hop retrieval with partial visible evidence.",
    }


if __name__ == "__main__":
    unittest.main()
