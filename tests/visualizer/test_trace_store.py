from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.versioning import FileEdit, HarnessVersionStore
from search_harness.visualizer import (
    CompilerLogStore,
    CriticLogStore,
    ExperimentRunStore,
    HarnessEvolutionStore,
    ReportStore,
    TraceStore,
)


class TraceStoreTest(TestCase):
    def test_loads_evaluation_report_directory(self) -> None:
        """Verifies the loads evaluation report directory contract."""
        with TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)
            report_dir = reports_dir / "student-b0"
            report_dir.mkdir()
            (report_dir / "summary.json").write_text(
                json.dumps({"metrics": {"answers": {"accuracy": 1.0}}}),
                encoding="utf-8",
            )
            (report_dir / "per_example.jsonl").write_text(
                json.dumps({"example_id": "item-1", "score": 1}) + "\n",
                encoding="utf-8",
            )

            store = ReportStore(reports_dir)
            report = store.load_report("student-b0")
            report_paths = [item.path for item in store.list_reports()]

        self.assertEqual(report_paths, ["student-b0"])
        self.assertEqual(report["items"][0]["score"], 1)

    def test_lists_json_and_jsonl_and_normalizes_batch_entries(self) -> None:
        """Verifies the lists json and jsonl and normalizes batch entries contract."""
        with TemporaryDirectory() as tmpdir:
            traces_dir = Path(tmpdir)
            (traces_dir / "single.json").write_text(
                json.dumps(_run("single question")), encoding="utf-8"
            )
            (traces_dir / "batch.jsonl").write_text(
                json.dumps(
                    {
                        "example": {"example_id": "item-1", "answer": "golden answer"},
                        "run": _run("batch question"),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            store = TraceStore(traces_dir)

            files = store.list_files()
            batch = store.load_file("batch.jsonl")

        self.assertEqual([file.path for file in files], ["batch.jsonl", "single.json"])
        self.assertEqual(batch["format"], "jsonl")
        self.assertEqual(batch["entries"][0]["label"], "item-1")
        self.assertEqual(batch["entries"][0]["run"]["question"], "batch question")
        self.assertEqual(batch["entries"][0]["example"]["answer"], "golden answer")

    def test_rejects_paths_outside_the_trace_directory(self) -> None:
        """Verifies the rejects paths outside the trace directory contract."""
        with TemporaryDirectory() as tmpdir:
            store = TraceStore(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "inside traces directory"):
                store.load_file("../outside.json")

    def test_preserves_batch_runner_error_without_inventing_a_run(self) -> None:
        """Verifies the preserves batch runner error without inventing a run contract."""
        with TemporaryDirectory() as tmpdir:
            traces_dir = Path(tmpdir)
            (traces_dir / "errors.jsonl").write_text(
                json.dumps(
                    {
                        "example": {"example_id": "item-1"},
                        "runner_error": {
                            "type": "RuntimeError",
                            "message": "model unavailable",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            entry = TraceStore(traces_dir).load_file("errors.jsonl")["entries"][0]

        self.assertIsNone(entry["run"])
        self.assertEqual(entry["runner_error"]["type"], "RuntimeError")


class HarnessEvolutionStoreTest(TestCase):
    def test_projects_versions_iteration_events_and_version_changes(self) -> None:
        """Verifies the projects versions iteration events and version changes contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store_root = base / "version-store"
            store = HarnessVersionStore(store_root)
            baseline = store.initialize(_plugins_root(base))
            session = store.start_iteration(metadata={"source": "viewer-test"})
            session.apply_patch(
                (FileEdit("write", "extensions/note.txt", "candidate note\n"),)
            )
            session.reject("No improvement", evaluation={"accuracy": 0.0})

            view = HarnessEvolutionStore(store_root)
            overview = view.overview()
            iteration = view.load_iteration(session.iteration_id)
            version = view.load_version(baseline.version_id)
            topology = view.load_topology(baseline.version_id)

        self.assertTrue(overview["configured"])
        self.assertTrue(overview["initialized"])
        self.assertEqual(overview["versions"][0]["version_id"], "harness_v0001")
        self.assertEqual(overview["iterations"][0]["status"], "rejected")
        self.assertEqual(
            [event["event_type"] for event in iteration["events"]],
            ["started", "patch_applied", "rejected"],
        )
        self.assertEqual(
            iteration["events"][1]["payload"]["edits"][0]["content"],
            "candidate note\n",
        )
        self.assertIn("harness.json", [item["path"] for item in version["files"]])
        self.assertEqual(version["manifest"]["harness_id"], "viewer_test")
        self.assertEqual(topology["topology"]["harness_id"], "viewer_test")
        self.assertEqual(
            topology["topology"]["prompt"]["instance_id"], "base_prompt"
        )
        self.assertEqual(topology["topology"]["phase_order"][0], "pre_prompt")

    def test_reports_when_no_version_store_is_configured(self) -> None:
        """Verifies the reports when no version store is configured contract."""
        overview = HarnessEvolutionStore(None).overview()

        self.assertFalse(overview["configured"])
        self.assertEqual(overview["versions"], [])
        self.assertEqual(overview["iterations"], [])


class CriticLogStoreTest(TestCase):
    def test_lists_and_loads_completed_and_failed_critic_logs(self) -> None:
        """Verifies the lists and loads completed and failed critic logs contract."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            (logs_dir / "critic_success.json").write_text(
                json.dumps(
                    _critic_log(
                        created_at="2026-07-14T10:00:00+00:00",
                        critic_result={
                            "analysis": "Repeated format issue.",
                            "proposals": [{"hypothesis": "format"}],
                            "evidence_requests": [],
                        },
                        run=_run("Analyze failures"),
                    )
                ),
                encoding="utf-8",
            )
            (logs_dir / "critic_timeout.json").write_text(
                json.dumps(
                    _critic_log(
                        created_at="2026-07-14T11:00:00+00:00",
                        result_error="TimeoutError: The read operation timed out",
                        run=None,
                    )
                ),
                encoding="utf-8",
            )
            (logs_dir / "ordinary.json").write_text(
                json.dumps(_run("not a Critic log")),
                encoding="utf-8",
            )

            store = CriticLogStore(logs_dir)
            logs = store.list_logs()
            timeout_log = store.load_log("critic_timeout.json")

        self.assertEqual([item["path"] for item in logs], ["critic_timeout.json", "critic_success.json"])
        self.assertEqual(logs[0]["status"], "failed")
        self.assertEqual(logs[1]["proposal_count"], 1)
        self.assertIsNone(timeout_log["log"]["run"])
        self.assertEqual(
            timeout_log["summary"]["result_error"],
            "TimeoutError: The read operation timed out",
        )

    def test_rejects_paths_outside_the_critic_log_directory(self) -> None:
        """Verifies the rejects paths outside the critic log directory contract."""
        with TemporaryDirectory() as tmpdir:
            store = CriticLogStore(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "inside logs directory"):
                store.load_log("../outside.json")


class CompilerLogStoreTest(TestCase):
    def test_lists_and_loads_compiler_logs(self) -> None:
        """Verifies the lists and loads compiler logs contract."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            (logs_dir / "compiler_success.json").write_text(
                json.dumps(
                    _compiler_log(
                        created_at="2026-07-15T10:00:00+00:00",
                        compiler_result={
                            "summary": "Add an extension.",
                            "edits": [{"operation": "write", "path": "harness.json"}],
                            "clarification": None,
                        },
                        validation={"passed": True, "issues": []},
                        run=_run("Compile proposal"),
                    )
                ),
                encoding="utf-8",
            )
            (logs_dir / "compiler_failure.json").write_text(
                json.dumps(
                    _compiler_log(
                        created_at="2026-07-15T11:00:00+00:00",
                        result_error="TimeoutError: request timed out",
                        run=None,
                    )
                ),
                encoding="utf-8",
            )
            (logs_dir / "critic.json").write_text(
                json.dumps(
                    _critic_log(
                        created_at="2026-07-15T12:00:00+00:00",
                        run=_run("Critic"),
                    )
                ),
                encoding="utf-8",
            )

            store = CompilerLogStore(logs_dir)
            logs = store.list_logs()
            success = store.load_log("compiler_success.json")

        self.assertEqual(
            [item["path"] for item in logs],
            ["compiler_failure.json", "compiler_success.json"],
        )
        self.assertEqual(logs[0]["status"], "failed")
        self.assertEqual(logs[1]["edit_count"], 1)
        self.assertTrue(logs[1]["validation_passed"])
        self.assertEqual(success["summary"]["iteration_id"], "iteration_0001")

    def test_rejects_paths_outside_the_compiler_log_directory(self) -> None:
        """Verifies the rejects paths outside the compiler log directory contract."""
        with TemporaryDirectory() as tmpdir:
            store = CompilerLogStore(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "inside logs directory"):
                store.load_log("../outside.json")


class ExperimentRunStoreTest(TestCase):
    def test_aggregates_iterations_and_loads_component_artifacts(self) -> None:
        """Verifies one experiment projects its ordered stages and full artifacts."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "evolution" / "run_001"
            iteration_dir = run_dir / "iterations" / "0001"
            report_dir = iteration_dir / "incumbent_report"
            report_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "initial_version": "harness_v0001",
                        "experience_set": {"count": 2},
                    }
                ),
                encoding="utf-8",
            )
            events = [
                {
                    "sequence": 0,
                    "event_type": "iteration_started",
                    "iteration": 1,
                    "timestamp": "2026-07-19T00:00:00+00:00",
                    "payload": {"parent_version": "harness_v0001"},
                },
                {
                    "sequence": 1,
                    "event_type": "candidate_rejected",
                    "iteration": 1,
                    "timestamp": "2026-07-19T00:01:00+00:00",
                    "payload": {"reason": "Regression"},
                },
                {
                    "sequence": 2,
                    "event_type": "run_completed",
                    "iteration": None,
                    "timestamp": "2026-07-19T00:01:01+00:00",
                    "payload": {
                        "status": "max_iterations",
                        "latest_version": "harness_v0001",
                        "accepted_iterations": 0,
                    },
                },
            ]
            (run_dir / "events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            rollout = {"example": {"example_id": "one"}, "run": _run("Question")}
            (iteration_dir / "incumbent_rollouts.jsonl").write_text(
                json.dumps(rollout) + "\n",
                encoding="utf-8",
            )
            (report_dir / "summary.json").write_text(
                json.dumps({"metrics": {"answers": {"accuracy": 1.0}}}),
                encoding="utf-8",
            )
            (report_dir / "per_example.jsonl").write_text(
                json.dumps({"example_id": "one", "score": 1}) + "\n",
                encoding="utf-8",
            )
            compiler_payload = _compiler_log(
                created_at="2026-07-19T00:00:30+00:00",
                compiler_result={"summary": "Patch", "edits": []},
                run=_run("Compile"),
            )
            compiler_payload["critic_result"] = {"analysis": "Input evidence"}
            (iteration_dir / "compiler.json").write_text(
                json.dumps(compiler_payload),
                encoding="utf-8",
            )

            store = ExperimentRunStore(root)
            runs = store.list_runs()
            document = store.load_run("evolution/run_001")
            actor = store.load_artifact(
                "evolution/run_001",
                "iterations/0001/incumbent_rollouts.jsonl",
            )
            evaluation = store.load_artifact(
                "evolution/run_001",
                "iterations/0001/incumbent_report",
            )
            compiler = store.load_artifact(
                "evolution/run_001",
                "iterations/0001/compiler.json",
            )

        self.assertEqual(runs[0]["status"], "max_iterations")
        self.assertEqual(document["iterations"][0]["decision"]["event_type"], "candidate_rejected")
        self.assertEqual(document["iterations"][0]["events"][-1]["event_type"], "run_completed")
        self.assertEqual(len(document["iterations"][0]["artifacts"]), 3)
        self.assertEqual(actor["kind"], "actor")
        self.assertEqual(actor["entries"][0]["label"], "one")
        self.assertEqual(evaluation["kind"], "evaluation")
        self.assertEqual(compiler["kind"], "compiler")

    def test_rejects_artifacts_outside_the_selected_experiment(self) -> None:
        """Verifies experiment artifact access cannot escape the selected run."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run_001"
            run_dir.mkdir()
            (run_dir / "run.json").write_text("{}", encoding="utf-8")
            (run_dir / "events.jsonl").write_text("", encoding="utf-8")
            store = ExperimentRunStore(root)

            with self.assertRaisesRegex(ValueError, "inside its run"):
                store.load_artifact("run_001", "../outside.json")


def _run(question: str) -> dict[str, object]:
    return {
        "question": question,
        "answer": "answer",
        "status": "completed",
        "error": None,
        "state": {"step": 1},
        "trace": [],
    }


def _critic_log(
    *,
    created_at: str,
    critic_result: dict[str, object] | None = None,
    result_error: str | None = None,
    run: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "created_at": created_at,
        "inputs": {
            "report_dir": "runs/components/actor/student_raw_100/evaluation",
            "rollout_file": "runs/components/actor/student_raw_100/rollout.jsonl",
            "actor_source": "harness_templates/actor/baseline/plugins",
            "harness_version": "working_directory",
            "critic_plugins_root": "harness_templates/adapter/critic/baseline/plugins",
            "model_role": "teacher",
            "data_split": "experience",
        },
        "critic_result": critic_result,
        "result_error": result_error,
        "run": run,
    }


def _compiler_log(
    *,
    created_at: str,
    compiler_result: dict[str, object] | None = None,
    validation: dict[str, object] | None = None,
    result_error: str | None = None,
    run: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "created_at": created_at,
        "inputs": {
            "critic_log": "runs/components/critic/example/critic.json",
            "proposal_index": 0,
            "checkpoint_store": "harness_checkpoints/search_actor",
            "checkpoint_store_id": "search_actor",
            "parent_version": "harness_v0001",
            "iteration_id": "iteration_0001",
            "compiler_plugins_root": "harness_templates/adapter/compiler/baseline/plugins",
            "model_role": "teacher",
        },
        "compiler_result": compiler_result,
        "result_error": result_error,
        "validation": validation,
        "run": run,
    }


def _plugins_root(base: Path) -> Path:
    root = base / "plugins-source"
    prompt_dir = root / "prompts" / "base"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "plugin.py").write_text(
        "from search_harness.core import ChatMessage, ModelInput\n\n"
        "class Prompt:\n"
        "    def build(self, state):\n"
        "        return ModelInput.from_messages([ChatMessage(role='user', content=state.question)])\n\n"
        "def build(config, context, tools):\n"
        "    return Prompt()\n",
        encoding="utf-8",
    )
    (root / "harness.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "harness_id": "viewer_test",
                "tools": [],
                "prompt": {
                    "instance_id": "base_prompt",
                    "entrypoint": "prompts/base/plugin.py:build",
                    "config": {},
                    "evolution_policy": "fixed",
                },
                "extensions": [],
            }
        ),
        encoding="utf-8",
    )
    return root
