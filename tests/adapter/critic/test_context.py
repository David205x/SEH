from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.adapter.critic import CriticContext


class CriticContextTest(TestCase):
    def test_filters_and_paginates_compact_cases(self) -> None:
        """Verifies the filters and paginates compact cases contract."""
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))

            page = context.list_evaluation_cases(
                page=1,
                page_size=1,
                score=0,
                run_status="completed",
                has_retriever_error="false",
            )

        self.assertEqual(page["total_items"], 1)
        self.assertEqual(page["total_pages"], 1)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["items"][0]["example_id"], "case-1")
        self.assertNotIn("teacher", page["items"][0])

    def test_separates_evaluation_from_complete_trajectory(self) -> None:
        """Verifies the separates evaluation from complete trajectory contract."""
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))

            evaluation = context.get_case_evaluation("case-1")
            trajectory = context.get_case_trajectory("case-1", "r000")

        self.assertEqual(evaluation["score"], 0)
        self.assertNotIn("run", evaluation)
        self.assertEqual(trajectory["run"]["trace"][0]["event_type"], "model_output")

    def test_reads_manifest_and_all_component_text_files(self) -> None:
        """Verifies the reads manifest and all component text files contract."""
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))

            component = context.get_harness_component("extensions", "review")

        self.assertEqual(context.get_harness_manifest()["harness_id"], "actor-test")
        self.assertEqual(
            sorted(component["files"]),
            ["extensions/review/helper.py", "extensions/review/plugin.py"],
        )
        self.assertIn("def build", component["files"]["extensions/review/plugin.py"])

    def test_initial_context_contains_summary_but_not_case_records(self) -> None:
        """Verifies the initial context contains summary but not case records contract."""
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))

            initial = context.initial_context()

        self.assertEqual(initial["data_split"], "experience")
        self.assertEqual(initial["evaluation_summary"]["metrics"]["accuracy"], 0.5)
        self.assertNotIn("evaluation_cases", initial)

    def test_rejects_invalid_page_size_at_context_boundary(self) -> None:
        """Verifies the rejects invalid page size at context boundary contract."""
        with TemporaryDirectory() as tmpdir:
            context = _make_context(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "page_size"):
                context.list_evaluation_cases(
                    page=1,
                    page_size=101,
                    score=-1,
                    run_status="any",
                    has_retriever_error="any",
                )

    def test_aligns_comparison_cases_and_reports_score_transitions(self) -> None:
        """Verifies the aligns comparison cases and reports score transitions contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            context = _make_context(root)
            context = _bind_comparison(context, root)

            summary = context.get_comparison_summary()
            changed = context.list_comparison_cases(
                page=1,
                page_size=20,
                transition="comparison_only_correct",
            )
            trajectory = context.get_comparison_trajectory("case-1", "r000")
            harness_changes = context.get_harness_change_summary()

        self.assertEqual(summary["matched_count"], 2)
        self.assertEqual(summary["transitions"]["comparison_only_correct"], 1)
        self.assertEqual(summary["transitions"]["both_correct"], 1)
        self.assertEqual(summary["comparison_only_count"], 1)
        self.assertEqual(changed["items"][0]["example_id"], "case-1")
        self.assertEqual(trajectory["execution_delta"]["tool_calls"], -1)
        self.assertIn("extensions/review/helper.py", harness_changes["modified_paths"])


def _make_context(root: Path) -> CriticContext:
    report_dir = root / "report"
    report_dir.mkdir()
    rollout_file = root / "rollouts.jsonl"
    cases = [
        {
            "example_id": "case-1",
            "question": "Question one?",
            "golden_answer": "Gold",
            "predicted_answer": "Wrong",
            "run_status": "completed",
            "runner_error": None,
            "static": {"decision": "needs_teacher"},
            "teacher": {"score": 0},
            "score": 0,
            "score_source": "teacher",
            "execution": {"tool_calls": 2, "retriever_errors": 0},
        },
        {
            "example_id": "case-2",
            "question": "Question two?",
            "golden_answer": "Answer",
            "predicted_answer": "Answer",
            "run_status": "completed",
            "runner_error": None,
            "static": {"decision": "pass"},
            "teacher": None,
            "score": 1,
            "score_source": "static",
            "execution": {"tool_calls": 1, "retriever_errors": 0},
        },
    ]
    summary = {
        "schema_version": 1,
        "source_file": str(rollout_file),
        "metrics": {"accuracy": 0.5},
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    (report_dir / "per_example.jsonl").write_text(
        "\n".join(json.dumps(item) for item in cases) + "\n",
        encoding="utf-8",
    )
    rollouts = [
        {
            "example": {"example_id": item["example_id"], "question": item["question"]},
            "run": {
                "answer": item["predicted_answer"],
                "trace": [{"event_type": "model_output", "payload": {"raw_output": "x"}}],
            },
        }
        for item in cases
    ]
    rollout_file.write_text(
        "\n".join(json.dumps(item) for item in rollouts) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "harness_id": "actor-test",
        "tools": [],
        "prompt": {
            "instance_id": "prompt",
            "entrypoint": "prompts/prompt/plugin.py:build",
            "config": {},
            "evolution_policy": "fixed",
        },
        "extensions": [
            {
                "instance_id": "review",
                "entrypoint": "extensions/review/plugin.py:build",
                "config": {},
                "evolution_policy": "mutable",
                "enabled": True,
            }
        ],
    }
    files = {
        PurePosixPath("harness.json"): json.dumps(manifest).encode("utf-8"),
        PurePosixPath("extensions/review/plugin.py"): b"def build():\n    pass\n",
        PurePosixPath("extensions/review/helper.py"): b"VALUE = 1\n",
    }
    return CriticContext.load(
        report_dir=report_dir,
        rollout_file=rollout_file,
        harness_files=files,
        harness_version="harness_v0002",
    )


def _bind_comparison(context: CriticContext, root: Path) -> CriticContext:
    report_dir = root / "comparison-report"
    report_dir.mkdir()
    rollout_file = root / "comparison-rollouts.jsonl"
    cases = [
        {
            "example_id": "case-3",
            "question": "Question three?",
            "score": 0,
            "run_status": "completed",
            "execution": {"tool_calls": 1, "retriever_errors": 0},
        },
        {
            "example_id": "case-1",
            "question": "Question one?",
            "score": 1,
            "run_status": "completed",
            "execution": {"tool_calls": 3, "retriever_errors": 0},
        },
        {
            "example_id": "case-2",
            "question": "Question two?",
            "score": 1,
            "run_status": "completed",
            "execution": {"tool_calls": 1, "retriever_errors": 0},
        },
    ]
    (report_dir / "summary.json").write_text(
        json.dumps({"source_file": str(rollout_file), "metrics": {}}),
        encoding="utf-8",
    )
    (report_dir / "per_example.jsonl").write_text(
        "\n".join(json.dumps(item) for item in cases) + "\n",
        encoding="utf-8",
    )
    rollout_file.write_text(
        "\n".join(
            json.dumps(
                {
                    "example": {
                        "example_id": item["example_id"],
                        "question": item["question"],
                    },
                    "run": {"trace": []},
                }
            )
            for item in cases
        )
        + "\n",
        encoding="utf-8",
    )
    files = dict(context.harness_files)
    files[PurePosixPath("extensions/review/helper.py")] = b"VALUE = 0\n"
    return context.bind_comparison(
        report_dir=report_dir,
        rollout_file=rollout_file,
        harness_files=files,
        harness_version="harness_v0001",
    )
