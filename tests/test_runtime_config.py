"""Structured runtime configuration tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from search_harness._internal.runtime_config import (
    evolution_control_values,
    evolution_effect_values,
    legacy_runtime_values,
    read_runtime_config,
    teacher_role_budget,
)


class RuntimeConfigTest(unittest.TestCase):
    def test_reads_yaml_comments_without_corrupting_urls(self) -> None:
        """YAML comments remain readable while URL slashes stay in strings."""

        with TemporaryDirectory() as temporary_dir:
            config_file = Path(temporary_dir) / "runtime.yaml"
            config_file.write_text(
                "schema_version: 1 # schema\n"
                "models:\n"
                "  student:\n"
                "    base_url: http://localhost/v1 # endpoint\n",
                encoding="utf-8",
            )

            config = read_runtime_config(config_file=config_file)

        self.assertEqual(
            config["models"]["student"]["base_url"],
            "http://localhost/v1",
        )

    def test_reads_complete_evolution_hyperparameters(self) -> None:
        config = _evolution_config()

        control = evolution_control_values(config)
        effects = evolution_effect_values(config)

        self.assertEqual(control["max_trials_per_hypothesis"], 5)
        self.assertEqual(control["max_trial_assignments"], 14)
        self.assertEqual(effects["rollouts_per_example"], 3)
        self.assertEqual(effects["candidate_error_streak_limit"], 3)

    def test_rejects_trial_assignment_budget_below_trial_budget(self) -> None:
        config = _evolution_config()
        config["evolution"]["control"]["max_trial_assignments"] = 4
        with self.assertRaisesRegex(ValueError, "must be at least"):
            evolution_control_values(config)

    def test_rejects_incomplete_evolution_effect_settings(self) -> None:
        config = _evolution_config()
        del config["evolution"]["effects"]["judge_workers"]

        with self.assertRaisesRegex(ValueError, "missing fields"):
            evolution_effect_values(config)

    def test_rejects_unknown_evolution_control_setting(self) -> None:
        config = _evolution_config()
        config["evolution"]["control"]["max_attempts"] = 3

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            evolution_control_values(config)

    def test_projects_model_and_runtime_settings(self) -> None:
        config = {
            "models": {
                "teacher": {
                    "base_url": "https://teacher.invalid",
                    "model_id": "teacher-test",
                    "max_tokens": 2048,
                    "thinking_mode": "enabled",
                }
            },
            "retriever": {"url": "http://retriever.invalid", "top_k": 7},
            "agent": {"max_steps": 12},
        }

        values = legacy_runtime_values(config)

        self.assertEqual(values["TEACHER_MODEL_ID"], "teacher-test")
        self.assertEqual(values["TEACHER_MAX_TOKENS"], "2048")
        self.assertEqual(values["TEACHER_THINKING_MODE"], "enabled")
        self.assertEqual(values["RETRIEVER_TOPK"], "7")
        self.assertEqual(values["MAX_AGENT_ITERS"], "12")

    def test_resolves_each_teacher_role_budget_independently(self) -> None:
        config = {
            "teacher_roles": {
                "trial_reviewer": {"max_tokens": 4096, "max_turns": 8},
                "evidence_reviewer": {
                    "max_tokens": 12288,
                    "max_turns": 20,
                },
            }
        }

        trial = teacher_role_budget(
            config,
            "trial_reviewer",
            default_max_tokens=1024,
            default_max_turns=3,
        )
        evidence = teacher_role_budget(
            config,
            "evidence_reviewer",
            default_max_tokens=1024,
            default_max_turns=3,
        )

        self.assertEqual((trial.max_tokens, trial.max_turns), (4096, 8))
        self.assertEqual(
            (evidence.max_tokens, evidence.max_turns),
            (12288, 20),
        )


def _evolution_config() -> dict[str, Any]:
    return {
        "evolution": {
            "control": {
                "max_generations": 5,
                "max_trials_per_hypothesis": 5,
                "max_trial_assignments": 14,
                "max_hypothesis_revisions": 2,
                "max_mechanism_revisions": 2,
                "max_compiler_revisions": 2,
                "max_candidate_revisions": 2,
                "max_work_retries": 1,
                "max_work_items": 80,
                "max_total_tokens": None,
                "min_accuracy_delta": -0.02,
                "max_total_token_ratio": 3.0,
            },
            "effects": {
                "student_max_steps": 20,
                "teacher_max_turns": 20,
                "rollout_workers": 2,
                "rollouts_per_example": 3,
                "judge_workers": 8,
                "candidate_error_streak_limit": 3,
            },
        }
    }


if __name__ == "__main__":
    unittest.main()
