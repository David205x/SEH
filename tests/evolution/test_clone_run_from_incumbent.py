"""Tests for creating a fresh run from a reused incumbent evaluation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from typing import Any

from experiments.clone_run_from_incumbent import clone_run_from_incumbent
from search_harness._internal import (
    evolution_control_values,
    evolution_effect_values,
    read_runtime_config,
)
from search_harness.evolution.control.domain import (
    EffectResult,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.journal import (
    ControlArtifactStore,
    ControlJournal,
)
from search_harness.evolution.control.transitions import initial_work
from search_harness.evolution.experience import file_digest
from search_harness.evolution.versioning import (
    HarnessSnapshot,
    TemplateVersionStore,
)


SCRATCH_ROOT = Path("runs/components/clone_incumbent_tests")


class CloneRunFromIncumbentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = SCRATCH_ROOT / self._testMethodName
        if self.case_dir.exists():
            self._remove_tree(self.case_dir)
        self.source = self.case_dir / "source"
        self.destination = self.case_dir / "cloned"
        self.store = self.case_dir / "version_store"
        self._create_source_run()

    def tearDown(self) -> None:
        if self.case_dir.exists():
            self._remove_tree(self.case_dir)

    def test_creates_fresh_agenda_with_reused_evaluation(self) -> None:
        result = clone_run_from_incumbent(self.source, self.destination)

        self.assertEqual(result, self.destination.resolve())
        journal = ControlJournal(self.destination / "events.jsonl")
        state = project_events(journal.read())
        self.assertEqual(state.total_tokens, 0)
        self.assertEqual(state.completed_work_count, 1)
        self.assertEqual(len(state.queued), 1)
        self.assertIs(state.queued[0].item.kind, WorkKind.ANALYZE_FAILURE)
        self.assertEqual(state.queued[0].item.lineage.research_attempt, 1)

        evaluation = next(
            record.item
            for record in state.works.values()
            if record.item.kind is WorkKind.EVALUATE_INCUMBENT
        )
        effect = ControlArtifactStore(
            self.destination / "artifacts"
        ).load_effect(evaluation.work_id)
        for artifact_path in effect.artifact_refs.values():
            self.assertTrue(
                Path(artifact_path).is_relative_to(self.destination.resolve())
            )
            self.assertTrue(Path(artifact_path).exists())

        run_payload = self._read_object(self.destination / "run.json")
        reuse = run_payload["incumbent_evaluation_reuse"]
        self.assertEqual(reuse["charged_tokens"], 0)
        self.assertEqual(reuse["source_usage"]["total_tokens"], 123)
        self.assertEqual(
            run_payload["effects_config"]["experience_file"],
            str((self.destination / "experience_set.jsonl").resolve()),
        )
        cloned_store_path = self.destination / "version_store"
        self.assertEqual(
            run_payload["version_store"],
            str(cloned_store_path.resolve()),
        )
        source_attempts = (
            self.store / ".harness-store" / "candidate_attempts.jsonl"
        ).read_text(encoding="utf-8")
        cloned_store = TemplateVersionStore(cloned_store_path)
        self.assertNotEqual(cloned_store.version_store_id, "test-store")
        self.assertEqual(
            [item.version_id for item in cloned_store.list_versions()],
            ["harness_v0001"],
        )
        self.assertEqual(cloned_store.list_candidate_attempts(), ())
        self.assertTrue(
            (self.store / ".harness-store" / "candidate_attempts.jsonl").exists()
        )
        attempt = cloned_store.start_candidate_attempt(
            metadata={"test": "independent"}
        )
        attempt.reject("Test independent Candidate lifecycle")
        self.assertEqual(
            (
                self.store / ".harness-store" / "candidate_attempts.jsonl"
            ).read_text(encoding="utf-8"),
            source_attempts,
        )

    def test_refuses_to_overwrite_existing_destination(self) -> None:
        self.destination.mkdir(parents=True)
        marker = self.destination / "keep.txt"
        marker.write_text("keep", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            clone_run_from_incumbent(self.source, self.destination)

        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_can_apply_current_runtime_configuration(self) -> None:
        runtime = read_runtime_config(
            config_file=Path("config/runtime.yaml")
        )
        env_file = self.case_dir / "runtime.env"

        clone_run_from_incumbent(
            self.source,
            self.destination,
            runtime_config=runtime,
            env_file=env_file,
        )

        run_payload = self._read_object(self.destination / "run.json")
        self.assertEqual(
            run_payload["control_config"],
            evolution_control_values(runtime),
        )
        effects = run_payload["effects_config"]
        for name, value in evolution_effect_values(runtime).items():
            self.assertEqual(effects[name], value)
        self.assertEqual(effects["env_file"], str(env_file.resolve()))
        self.assertEqual(
            effects["experience_file"],
            str((self.destination / "experience_set.jsonl").resolve()),
        )

    def _create_source_run(self) -> None:
        self.source.mkdir(parents=True)
        self._create_version_store()
        experience = self.source / "experience_set.jsonl"
        experience.write_text(
            json.dumps(
                {
                    "example_id": "example-1",
                    "question": "Question?",
                    "answer": "Answer",
                    "metadata": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        work = initial_work(run_id="source-run", version_id="harness_v0001")
        work_dir = self.source / "artifacts" / work.work_id
        report_dir = work_dir / "report"
        report_dir.mkdir(parents=True)
        (report_dir / "summary.json").write_text(
            json.dumps({"schema_version": 1, "metrics": {}}) + "\n",
            encoding="utf-8",
        )
        rollout_file = work_dir / "report_rollouts.jsonl"
        rollout_file.write_text("{}\n", encoding="utf-8")
        effect = EffectResult(
            outcome={"metrics": {"answers": {"accuracy": 0.5}}},
            artifact_refs={
                "rollout_file": str(rollout_file.resolve()),
                "report_dir": str(report_dir.resolve()),
            },
            usage={"total_tokens": 123},
        )
        effect_path = ControlArtifactStore(
            self.source / "artifacts"
        ).write_effect(work.work_id, effect)
        ControlJournal(self.source / "events.jsonl").append_many(
            [
                (
                    "run_started",
                    {
                        "run_id": "source-run",
                        "initial_version": "harness_v0001",
                        "generation": work.lineage.generation,
                        "generation_id": work.lineage.generation_id,
                    },
                ),
                ("work_scheduled", {"work": work.to_dict()}),
                ("work_started", {"work_id": work.work_id}),
                (
                    "work_completed",
                    {
                        "work_id": work.work_id,
                        "result_ref": str(effect_path),
                        "total_tokens": 123,
                    },
                ),
            ]
        )
        self._write_object(
            self.source / "run.json",
            {
                "schema_version": 3,
                "run_id": "source-run",
                "version_store": str(self.store.resolve()),
                "version_store_id": "test-store",
                "initial_version": "harness_v0001",
                "control_config": {},
                "effects_config": {
                    "experience_file": str(experience.resolve()),
                    "env_file": str(Path(".env").resolve()),
                },
                "experience_set": {
                    "path": str(experience.resolve()),
                    "count": 1,
                    "digest": file_digest(experience),
                },
                "dataset": {
                    "path": str(experience.resolve()),
                    "format": "jsonl",
                    "filter_status": None,
                },
            },
        )

    def _create_version_store(self) -> None:
        metadata = self.store / ".harness-store"
        metadata.mkdir(parents=True)
        template = self.store / "template"
        template.mkdir()
        (template / "baseline.txt").write_text(
            "baseline\n",
            encoding="utf-8",
        )
        self._git("init")
        self._git("config", "user.name", "Test")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "core.autocrlf", "false")
        self._git("add", "template")
        self._git("commit", "-m", "Initialize baseline")
        commit = self._git("rev-parse", "HEAD").stdout.strip()
        template_digest = HarnessSnapshot.from_directory(
            template,
            version_id="harness_v0001",
        ).digest
        self._write_object(
            self.store / "version_store.json",
            {"schema_version": 3, "version_store_id": "test-store"},
        )
        record = {
            "schema_version": 3,
            "version_id": "harness_v0001",
            "parent_version": None,
            "git_commit": commit,
            "digest": template_digest,
            "summary": "Test baseline",
            "evaluation": {},
            "candidate_attempt_id": None,
        }
        (metadata / "versions.jsonl").write_text(
            json.dumps(record) + "\n",
            encoding="utf-8",
        )
        rejected_event = {
            "schema_version": 3,
            "candidate_attempt_id": "candidate_attempt_rejected",
            "sequence": 0,
            "event_type": "started",
            "timestamp": "2026-08-07T00:00:00+00:00",
            "payload": {
                "parent_version": "harness_v0001",
                "parent_digest": "test-digest",
                "metadata": {},
            },
        }
        (metadata / "candidate_attempts.jsonl").write_text(
            json.dumps(rejected_event) + "\n",
            encoding="utf-8",
        )

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.store), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    @staticmethod
    def _remove_tree(path: Path) -> None:
        def make_writable_and_retry(
            operation: Any,
            value: str,
            error: tuple[type[BaseException], BaseException, object],
        ) -> None:
            del error
            os.chmod(value, 0o700)
            operation(value)

        for attempt in range(5):
            try:
                shutil.rmtree(path, onerror=make_writable_and_retry)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1)

    @staticmethod
    def _read_object(path: Path) -> dict[str, object]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(path)
        return value

    @staticmethod
    def _write_object(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
