"""Hypothesis Researcher debug-fragment and relocation tests."""

from __future__ import annotations

import asyncio
import json
import shutil
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from experiments.run_hypothesis_researcher_fragment import (
    parse_args,
    run_hypothesis_researcher,
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


SCRATCH_ROOT = Path("runs/c/hr")


class _FakeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.version_store_id = "hypothesis-researcher-test-store"


class _StageEffects:
    def __init__(self, expected: WorkKind) -> None:
        self.expected = expected

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        del state
        if work.kind is not self.expected:
            raise AssertionError(f"Unexpected work kind: {work.kind}")
        work_dir.mkdir(parents=True, exist_ok=True)
        if work.kind is WorkKind.EVALUATE_INCUMBENT:
            report_dir = work_dir / "report"
            report_dir.mkdir()
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
        if work.kind is WorkKind.ANALYZE_FAILURE:
            artifact = work_dir / "failure.json"
            artifact.write_text(
                '{"output":{"pattern":"premature finalization"}}\n',
                encoding="utf-8",
            )
            return EffectResult(
                outcome={"output": {"pattern": "premature finalization"}},
                artifact_refs={"failure_artifact": str(artifact.resolve())},
                usage={"total_tokens": 40},
            )
        for value in work.input_refs.values():
            if not Path(value).exists():
                raise AssertionError(f"Researcher input was not rebased: {value}")
        artifact = work_dir / "hypothesis.json"
        artifact.write_text(
            json.dumps(
                {
                    "output": {
                        "scheme_action": "start_new",
                        "hypothesis": {"trigger_phase": "pre_final"},
                    }
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return EffectResult(
            outcome={
                "output": {
                    "scheme_action": "start_new",
                    "hypothesis": {"trigger_phase": "pre_final"},
                }
            },
            artifact_refs={"hypothesis_artifact": str(artifact.resolve())},
            usage={"total_tokens": 60},
        )


class HypothesisResearcherFragmentTest(unittest.TestCase):
    def setUp(self) -> None:
        if SCRATCH_ROOT.exists():
            shutil.rmtree(SCRATCH_ROOT)
        self.old_dir = SCRATCH_ROOT / "a"
        self.run_dir = SCRATCH_ROOT / "b"

    def tearDown(self) -> None:
        if SCRATCH_ROOT.exists():
            shutil.rmtree(SCRATCH_ROOT)

    def test_parse_args_accepts_stored_run(self) -> None:
        args = parse_args(["--run-dir", "runs/debug_fragments/example"])

        self.assertEqual(
            args.run_dir,
            Path("runs/debug_fragments/example"),
        )
        self.assertIsNone(args.env_file)

    def test_rebases_moved_run_and_stops_before_trial_selection(self) -> None:
        control_config = EvolutionControlConfig()
        controller = EvolutionController(
            run_dir=self.old_dir,
            effects=_StageEffects(WorkKind.EVALUATE_INCUMBENT),
            config=control_config,
        )
        controller.initialize(
            run_id="run_hypothesis_researcher_test",
            initial_version="harness_v0001",
        )
        asyncio.run(
            controller.run(
                stop_before=frozenset({WorkKind.ANALYZE_FAILURE})
            )
        )
        analyst = EvolutionController(
            run_dir=self.old_dir,
            effects=_StageEffects(WorkKind.ANALYZE_FAILURE),
            config=control_config,
        )
        asyncio.run(
            analyst.run(
                stop_before=frozenset({WorkKind.RESEARCH_HYPOTHESIS})
            )
        )

        experience_file = self.old_dir / "experience_set.jsonl"
        experience_file.write_text("{}\n", encoding="utf-8")
        effects_config = LocalControlEffectsConfig(
            experience_file=experience_file,
            env_file=Path(".env"),
            show_progress=False,
        )
        stored_effects = asdict(effects_config)
        stored_effects["experience_file"] = str(experience_file.resolve())
        stored_effects["env_file"] = str(Path(".env").resolve())
        (self.old_dir / "run.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "run_id": "run_hypothesis_researcher_test",
                    "version_store": str(
                        (SCRATCH_ROOT / "version_store").resolve()
                    ),
                    "version_store_id": "hypothesis-researcher-test-store",
                    "initial_version": "harness_v0001",
                    "control_config": asdict(control_config),
                    "effects_config": stored_effects,
                    "experience_set": {
                        "path": str(experience_file.resolve()),
                        "count": 1,
                        "digest": "digest",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.old_dir.rename(self.run_dir)
        args = parse_args(["--run-dir", str(self.run_dir)])

        with (
            patch(
                "experiments.run_hypothesis_researcher_fragment."
                "TemplateVersionStore",
                _FakeStore,
            ),
            patch(
                "experiments.run_hypothesis_researcher_fragment."
                "LocalControlEffects",
                return_value=_StageEffects(WorkKind.RESEARCH_HYPOTHESIS),
            ),
        ):
            outcome, artifact = asyncio.run(
                run_hypothesis_researcher(args)
            )

        self.assertEqual(outcome.status, "running")
        self.assertEqual(outcome.completed_work_count, 3)
        self.assertEqual(outcome.total_tokens, 125)
        self.assertTrue(artifact.is_file())
        payload = json.loads(
            (self.run_dir / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            Path(payload["experience_set"]["path"]),
            (self.run_dir / "experience_set.jsonl").resolve(),
        )
        state = project_events(
            ControlJournal(self.run_dir / "events.jsonl").read()
        )
        self.assertEqual(state.queued[0].item.kind, WorkKind.SELECT_TRIAL)
        for value in state.queued[0].item.input_refs.values():
            self.assertTrue(Path(value).exists(), value)


if __name__ == "__main__":
    unittest.main()
