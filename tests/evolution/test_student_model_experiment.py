"""Descriptive Student model experiment tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from search_harness.evolution.research.resources.base import TeacherResources
from search_harness.evolution.research.student_model_experiment import (
    StudentModelExperimentCase,
    run_student_model_experiment,
)
from search_harness.framework import HookModelRequest, HookModelResponse


class _ScriptedBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)
        self.requests: list[HookModelRequest] = []

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(
            raw_output=next(self.outputs),
            metadata={"usage": {"total_tokens": 12}},
        )


class StudentModelExperimentTest(unittest.TestCase):
    def test_returns_raw_outputs_without_expected_labels_or_verdict(self) -> None:
        backend = _ScriptedBackend(
            ["enabled-a", "enabled-b", "disabled-a", "disabled-b"]
        )

        result = run_student_model_experiment(
            backend=backend,
            experiment_id="student_model_experiment_001",
            purpose="Observe a proposed response format.",
            system_prompt="Return one short label.",
            cases=(
                StudentModelExperimentCase(
                    case_id="boundary",
                    user_prompt="Classify this boundary.",
                ),
            ),
            thinking_modes=("enabled", "disabled"),
            repetitions=2,
        )

        self.assertEqual(len(result["observations"]), 4)
        self.assertEqual(
            [request.thinking_mode for request in backend.requests],
            ["enabled", "enabled", "disabled", "disabled"],
        )
        self.assertNotIn("expected_label", str(result))
        self.assertNotIn("passed", result)
        self.assertEqual(
            result["observations"][0]["raw_output"],
            "enabled-a",
        )

    def test_rejects_duplicate_cases_and_unbounded_repetitions(self) -> None:
        backend = _ScriptedBackend([])
        duplicate = (
            StudentModelExperimentCase("same", "first"),
            StudentModelExperimentCase("same", "second"),
        )

        with self.assertRaisesRegex(ValueError, "unique"):
            run_student_model_experiment(
                backend=backend,
                experiment_id="student_model_experiment_001",
                purpose="Observe behavior.",
                system_prompt="Respond.",
                cases=duplicate,
                thinking_modes=("disabled",),
                repetitions=1,
            )
        with self.assertRaisesRegex(ValueError, "one to three"):
            run_student_model_experiment(
                backend=backend,
                experiment_id="student_model_experiment_001",
                purpose="Observe behavior.",
                system_prompt="Respond.",
                cases=(StudentModelExperimentCase("one", "input"),),
                thinking_modes=("disabled",),
                repetitions=4,
            )

    def test_teacher_resources_reuses_identical_experiment(self) -> None:
        """验证 Compiler 修订可复用同请求实验而不再次调用 Student。"""

        backend = _ScriptedBackend(["negative"])
        resources = TeacherResources(hook_probe_env_file=Path(".env"))
        kwargs = {
            "purpose": "Check one boundary.",
            "system_prompt": "Return one label.",
            "cases": [{"case_id": "negative", "user_prompt": "Case."}],
            "thinking_modes": ["disabled"],
            "repetitions": 1,
        }
        with patch(
            "search_harness.evolution.research.resources.base."
            "ProfiledHookModelBackend",
            return_value=backend,
        ):
            first = resources.run_student_model_experiment(**kwargs)
            second = resources.run_student_model_experiment(**kwargs)

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(backend.requests), 1)
        self.assertEqual(len(resources.student_model_experiments), 1)


if __name__ == "__main__":
    unittest.main()
