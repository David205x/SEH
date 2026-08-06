"""Evolution Run Artifact schema and CLI naming tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from search_harness.evolution.control.cli import (
    _read_run_payload,
    parse_args,
)


class EvolutionControlCliTest(unittest.TestCase):
    def test_start_uses_version_store_option(self) -> None:
        args = parse_args(
            [
                "start",
                "--run-dir",
                "run",
                "--version-store",
                "versions",
            ]
        )

        self.assertEqual(args.version_store, Path("versions"))
        for runtime_field in (
            "max_generations",
            "max_trials_per_hypothesis",
            "max_trial_assignments",
            "max_hypothesis_revisions",
            "max_mechanism_revisions",
            "max_compiler_revisions",
            "max_candidate_revisions",
            "max_work_retries",
            "max_work_items",
            "max_total_tokens",
            "min_accuracy_delta",
            "max_total_token_ratio",
            "student_max_steps",
            "teacher_max_turns",
            "rollout_workers",
            "rollouts_per_example",
            "judge_workers",
            "candidate_error_streak_limit",
        ):
            self.assertFalse(hasattr(args, runtime_field))

    def test_reads_new_run_artifact_schema_v2(self) -> None:
        payload = {
            "schema_version": 2,
            "version_store": "versions",
            "version_store_id": "store_v2",
        }

        loaded = _read_payload(payload)

        self.assertEqual(loaded, payload)
        self.assertNotIn("checkpoint_store", loaded)

    def test_migrates_legacy_run_artifact_schema_v1_in_memory(self) -> None:
        loaded = _read_payload(
            {
                "schema_version": 1,
                "checkpoint_store": "legacy_versions",
                "checkpoint_store_id": "legacy_store",
            }
        )

        self.assertEqual(loaded["version_store"], "legacy_versions")
        self.assertEqual(loaded["version_store_id"], "legacy_store")


def _read_payload(payload: dict[str, object]) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "run.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return _read_run_payload(path)


if __name__ == "__main__":
    unittest.main()
