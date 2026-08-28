"""Research-loop debug-fragment tests."""

from __future__ import annotations

import asyncio
import json
import shutil
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from experiments.run_research_until_distill_fragment import (
    parse_args,
    run_until_distill,
)
from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    TrajectoryLineage,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import LocalControlEffectsConfig
from search_harness.evolution.control.journal import (
    ControlJournal,
)
from search_harness.evolution.identifiers import (
    make_generation_id,
    make_logical_work_id,
    make_research_attempt_id,
    make_work_id,
)


SCRATCH_ROOT = Path("runs/c/rl")


class _FakeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.version_store_id = "research-loop-test-store"


class _ReadyToDistillEffects:
    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        del state, work_dir
        if work.kind is not WorkKind.REVIEW_EVIDENCE:
            raise AssertionError(f"Unexpected work kind: {work.kind}")
        return EffectResult(
            outcome={
                "output": {
                    "decision": "ready_to_distill",
                    "next_obligation": None,
                }
            },
            artifact_refs={"reviewer_artifact": "reviewer.json"},
            usage={"total_tokens": 20},
        )


class ResearchUntilDistillFragmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_dir = SCRATCH_ROOT / "run"
        if SCRATCH_ROOT.exists():
            shutil.rmtree(SCRATCH_ROOT)
        self.run_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        if SCRATCH_ROOT.exists():
            shutil.rmtree(SCRATCH_ROOT)

    def test_parse_args_accepts_stored_run(self) -> None:
        args = parse_args(["--run-dir", "runs/debug_fragments/example"])

        self.assertEqual(
            args.run_dir,
            Path("runs/debug_fragments/example"),
        )

    def test_stops_when_reviewer_routes_to_distiller(self) -> None:
        run_id = "run_research_loop_test"
        generation_id = make_generation_id(run_id, 1)
        research_id = make_research_attempt_id(generation_id, 1)
        logical_id = make_logical_work_id(
            research_id,
            1,
            WorkKind.REVIEW_EVIDENCE.value,
        )
        work = WorkItem(
            work_id=make_work_id(logical_id, 1),
            logical_work_id=logical_id,
            work_index=1,
            kind=WorkKind.REVIEW_EVIDENCE,
            subject_ref=generation_id,
            lineage=TrajectoryLineage(
                run_id=run_id,
                generation=1,
                generation_id=generation_id,
                research_attempt=1,
                research_attempt_id=research_id,
            ),
        )
        journal = ControlJournal(self.run_dir / "events.jsonl")
        journal.append_many(
            [
                (
                    "run_started",
                    {
                        "run_id": run_id,
                        "initial_version": "harness_v0001",
                        "generation": 1,
                        "generation_id": generation_id,
                    },
                ),
                ("work_scheduled", {"work": work.to_dict()}),
            ]
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
                    "version_store": str(
                        (SCRATCH_ROOT / "version_store").resolve()
                    ),
                    "version_store_id": "research-loop-test-store",
                    "control_config": asdict(EvolutionControlConfig()),
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
                "experiments.run_research_until_distill_fragment."
                "TemplateVersionStore",
                _FakeStore,
            ),
            patch(
                "experiments.run_research_until_distill_fragment."
                "LocalControlEffects",
                return_value=_ReadyToDistillEffects(),
            ),
        ):
            outcome = asyncio.run(run_until_distill(args))

        self.assertEqual(outcome.status, "running")
        state = project_events(journal.read())
        self.assertEqual(
            state.queued[0].item.kind,
            WorkKind.DISTILL_MECHANISM,
        )
        self.assertEqual(state.total_tokens, 20)


if __name__ == "__main__":
    unittest.main()
