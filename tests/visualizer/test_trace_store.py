from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.versioning import FileEdit, HarnessVersionStore
from search_harness.visualizer import (
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
            baseline = store.initialize(_template_root(base))
            session = store.start_iteration(metadata={"source": "viewer-test"})
            session.apply_patch(
                (
                    FileEdit(
                        "write",
                        "components/extensions/note.txt",
                        "candidate note\n",
                    ),
                )
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


def _run(question: str) -> dict[str, object]:
    return {
        "question": question,
        "answer": "answer",
        "status": "completed",
        "error": None,
        "state": {"step": 1},
        "trace": [],
    }


def _template_root(base: Path) -> Path:
    root = base / "template-source"
    prompt_dir = root / "components" / "prompts" / "base"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "component.py").write_text(
        "from search_harness.core import ChatMessage, ModelInput\n\n"
        "class Prompt:\n"
        "    def build(self, state):\n"
        "        return ModelInput.from_messages([ChatMessage(role='user', content=state.question)])\n\n"
        "def build(config, context, tools):\n"
        "    return Prompt()\n",
        encoding="utf-8",
    )
    output_dir = root / "components" / "outputs" / "tagged_output"
    output_dir.mkdir(parents=True)
    (output_dir / "component.py").write_text(
        "from search_harness.framework.harness import TaggedOutputParser\n\n"
        "def build(config, context):\n"
        "    return TaggedOutputParser()\n",
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
                    "entrypoint": "components/prompts/base/component.py:build",
                    "config": {},
                },
                "output": {
                    "instance_id": "tagged_output",
                    "entrypoint": "components/outputs/tagged_output/component.py:build",
                    "config": {},
                },
                "extensions": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "evolution.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "harness_id": "viewer_test",
                "components": {
                    "base_prompt": "fixed",
                    "tagged_output": "fixed",
                },
            }
        ),
        encoding="utf-8",
    )
    return root
