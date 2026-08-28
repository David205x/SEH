"""Incumbent-only Evolution debug-fragment tests."""

from __future__ import annotations

import asyncio
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiments.run_evolution_debug_fragment import (
    parse_args,
    start_incumbent_fragment,
)
from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.journal import ControlJournal


SCRATCH_ROOT = Path("runs/c/df")


class _FakeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.version_store_id = "debug-fragment-test-store"

    def list_versions(self) -> tuple[SimpleNamespace, ...]:
        return (SimpleNamespace(version_id="harness_v0001"),)


class _FakeDatasetLoader:
    def iter_examples(self) -> tuple[object, ...]:
        return (object(),)


class _FakeEvaluationEffects:
    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        del state
        if work.kind is not WorkKind.EVALUATE_INCUMBENT:
            raise AssertionError(f"Unexpected work kind: {work.kind}")
        report_dir = work_dir / "report"
        report_dir.mkdir(parents=True)
        rollout_file = work_dir / "report_rollouts.jsonl"
        rollout_file.write_text("{}\n", encoding="utf-8")
        return EffectResult(
            outcome={"metrics": {"accuracy": 0.5}},
            artifact_refs={
                "report_dir": str(report_dir.resolve()),
                "rollout_file": str(rollout_file.resolve()),
            },
            usage={"total_tokens": 25},
        )


class EvolutionDebugFragmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_dir = SCRATCH_ROOT / "run"
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)

    def tearDown(self) -> None:
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)

    def test_parse_args_requires_run_and_version_store(self) -> None:
        args = parse_args(
            [
                "--run-dir",
                "runs/debug_fragments/example",
                "--version-store",
                "runs/version_stores/example",
            ]
        )

        self.assertEqual(
            args.run_dir,
            Path("runs/debug_fragments/example"),
        )
        self.assertEqual(args.limit, 20)
        self.assertFalse(args.no_teacher_judge)

    def test_stops_with_formally_routed_failure_analyst_queued(self) -> None:
        args = parse_args(
            [
                "--run-dir",
                str(self.run_dir),
                "--version-store",
                str(SCRATCH_ROOT / "version_store"),
                "--dataset-path",
                str(SCRATCH_ROOT / "dataset.jsonl"),
                "--no-progress",
            ]
        )

        def materialize(
            examples: object,
            output_file: Path,
            *,
            limit: int,
        ) -> tuple[list[object], str]:
            del examples, limit
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text('{"example_id":"case-1"}\n', encoding="utf-8")
            return [object()], "experience-digest"

        with (
            patch(
                "experiments.run_evolution_debug_fragment."
                "TemplateVersionStore",
                _FakeStore,
            ),
            patch(
                "experiments.run_evolution_debug_fragment."
                "create_dataset_loader",
                return_value=_FakeDatasetLoader(),
            ),
            patch(
                "experiments.run_evolution_debug_fragment."
                "materialize_experience_set",
                side_effect=materialize,
            ),
            patch(
                "experiments.run_evolution_debug_fragment."
                "LocalControlEffects",
                return_value=_FakeEvaluationEffects(),
            ),
        ):
            outcome = asyncio.run(start_incumbent_fragment(args))

        self.assertEqual(outcome.status, "running")
        self.assertEqual(outcome.completed_work_count, 1)
        self.assertEqual(outcome.total_tokens, 25)
        state = project_events(
            ControlJournal(self.run_dir / "events.jsonl").read()
        )
        self.assertEqual(state.queued[0].item.kind, WorkKind.ANALYZE_FAILURE)
        self.assertEqual(state.completed_work_count, 1)
        payload = json.loads(
            (self.run_dir / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["initial_version"], "harness_v0001")
        self.assertEqual(payload["experience_set"]["count"], 1)
        completed = next(
            record
            for record in state.works.values()
            if record.item.kind is WorkKind.EVALUATE_INCUMBENT
        )
        self.assertTrue(
            (
                self.run_dir
                / "artifacts"
                / completed.item.work_id
                / "effect.json"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
