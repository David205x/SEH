"""Failure Analyst debug-fragment tests."""

from __future__ import annotations

import asyncio
import json
import shutil
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from experiments.run_failure_analyst_fragment import (
    parse_args,
    run_failure_analyst,
)
from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import LocalControlEffectsConfig
from search_harness.evolution.control.journal import ControlJournal


SCRATCH_ROOT = Path("runs/c/fa")


class _FakeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.version_store_id = "failure-analyst-test-store"


class _IncumbentEffects:
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
        rollout_file = work_dir / "rollouts.jsonl"
        rollout_file.write_text("{}\n", encoding="utf-8")
        return EffectResult(
            outcome={"metrics": {"accuracy": 0.5}},
            artifact_refs={
                "report_dir": str(report_dir.resolve()),
                "rollout_file": str(rollout_file.resolve()),
            },
            usage={"total_tokens": 25},
        )


class _AnalystEffects:
    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        del state
        if work.kind is not WorkKind.ANALYZE_FAILURE:
            raise AssertionError(f"Unexpected work kind: {work.kind}")
        artifact = work_dir / "failure_analyst.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            json.dumps(
                {"output": {"pattern": "premature finalization"}},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return EffectResult(
            outcome={"output": {"pattern": "premature finalization"}},
            artifact_refs={"failure_artifact": str(artifact.resolve())},
            usage={"total_tokens": 40},
        )


class FailureAnalystFragmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_dir = SCRATCH_ROOT / "run"
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)

    def tearDown(self) -> None:
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)

    def test_parse_args_accepts_stored_run(self) -> None:
        args = parse_args(["--run-dir", "runs/debug_fragments/example"])

        self.assertEqual(
            args.run_dir,
            Path("runs/debug_fragments/example"),
        )
        self.assertIsNone(args.env_file)

    def test_runs_analyst_and_stops_before_researcher(self) -> None:
        control_config = EvolutionControlConfig()
        initial = EvolutionController(
            run_dir=self.run_dir,
            effects=_IncumbentEffects(),
            config=control_config,
        )
        initial.initialize(
            run_id="run_failure_analyst_test",
            initial_version="harness_v0001",
        )
        asyncio.run(
            initial.run(
                stop_before=frozenset({WorkKind.ANALYZE_FAILURE})
            )
        )

        experience_file = self.run_dir / "experience_set.jsonl"
        experience_file.write_text("{}\n", encoding="utf-8")
        effects_config = LocalControlEffectsConfig(
            experience_file=experience_file,
            env_file=Path(".env"),
            show_progress=False,
        )
        stored_effects = asdict(effects_config)
        stored_effects["experience_file"] = str(experience_file.resolve())
        stored_effects["env_file"] = str(Path(".env").resolve())
        (self.run_dir / "run.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "run_id": "run_failure_analyst_test",
                    "version_store": str(
                        (SCRATCH_ROOT / "version_store").resolve()
                    ),
                    "version_store_id": "failure-analyst-test-store",
                    "initial_version": "harness_v0001",
                    "control_config": asdict(control_config),
                    "effects_config": stored_effects,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        args = parse_args(["--run-dir", str(self.run_dir)])

        with (
            patch(
                "experiments.run_failure_analyst_fragment."
                "TemplateVersionStore",
                _FakeStore,
            ),
            patch(
                "experiments.run_failure_analyst_fragment."
                "LocalControlEffects",
                return_value=_AnalystEffects(),
            ),
        ):
            outcome, artifact = asyncio.run(run_failure_analyst(args))

        self.assertEqual(outcome.status, "running")
        self.assertEqual(outcome.completed_work_count, 2)
        self.assertEqual(outcome.total_tokens, 65)
        self.assertTrue(artifact.is_file())
        state = project_events(
            ControlJournal(self.run_dir / "events.jsonl").read()
        )
        self.assertEqual(
            state.queued[0].item.kind,
            WorkKind.RESEARCH_HYPOTHESIS,
        )
        analyst = next(
            record
            for record in state.works.values()
            if record.item.kind is WorkKind.ANALYZE_FAILURE
        )
        researcher = state.queued[0].item
        self.assertEqual(researcher.parent_work_id, analyst.item.work_id)
        self.assertIn("failure_artifact", researcher.input_refs)


if __name__ == "__main__":
    unittest.main()
