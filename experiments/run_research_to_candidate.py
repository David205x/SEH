"""Run the v2 role chain from Researcher to an evaluation-ready Candidate."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.journal import ControlJournal
from search_harness.versioning import HarnessVersionStore


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start from an existing Failure Analyst result and stop after "
            "Mechanism Conformance Replay schedules candidate evaluation."
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-store", type=Path, required=True)
    parser.add_argument("--experience-file", type=Path, required=True)
    parser.add_argument("--incumbent-rollout-file", type=Path, required=True)
    parser.add_argument("--incumbent-report-dir", type=Path, required=True)
    parser.add_argument("--failure-artifact", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--actor-max-steps", type=int, default=30)
    parser.add_argument("--teacher-max-turns", type=int, default=50)
    parser.add_argument("--rollout-workers", type=int, default=6)
    parser.add_argument("--judge-workers", type=int, default=8)
    parser.add_argument("--max-work-items", type=int, default=120)
    parser.add_argument(
        "--resume-exhausted",
        action="store_true",
        help="Allow one explicit retry after an exhausted work retry budget.",
    )
    return parser.parse_args()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prepare_inputs(
    *,
    run_dir: Path,
    experience_file: Path,
    rollout_file: Path,
    report_dir: Path,
    failure_artifact: Path,
) -> dict[str, Path]:
    inputs_dir = run_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=False)
    copied_report = inputs_dir / "incumbent_report"
    shutil.copytree(report_dir, copied_report)
    copied = {
        "experience_file": run_dir / "experience_set.jsonl",
        "rollout_file": inputs_dir / "incumbent_rollouts.jsonl",
        "report_dir": copied_report,
        "failure_artifact": inputs_dir / "failure_analyst.json",
    }
    shutil.copy2(experience_file, copied["experience_file"])
    shutil.copy2(rollout_file, copied["rollout_file"])
    shutil.copy2(failure_artifact, copied["failure_artifact"])
    return copied


def _control_config(max_work_items: int) -> EvolutionControlConfig:
    return EvolutionControlConfig(
        max_generations=1,
        max_trials_per_hypothesis=10,
        max_trial_assignments=60,
        max_hypothesis_revisions=6,
        max_mechanism_revisions=5,
        max_compiler_revisions=5,
        max_candidate_revisions=4,
        max_work_retries=3,
        max_work_items=max_work_items,
        max_total_tokens=50_000_000,
        min_accuracy_delta=0.0,
        max_total_token_ratio=3.0,
    )


async def _run(args: argparse.Namespace) -> None:
    run_dir = args.run_dir.resolve()
    store = HarnessVersionStore(args.checkpoint_store.resolve())
    journal = ControlJournal(run_dir / "events.jsonl")
    if run_dir.exists():
        raw_run = _read_object(run_dir / "run.json")
        raw_control = raw_run.get("control_config")
        raw_effects = raw_run.get("effects_config")
        if not isinstance(raw_control, dict) or not isinstance(
            raw_effects,
            dict,
        ):
            raise TypeError("Existing run.json lacks controller configuration")
        control_config = EvolutionControlConfig(**raw_control)
        effects_config = LocalControlEffectsConfig(
            **{
                **raw_effects,
                "experience_file": Path(str(raw_effects["experience_file"])),
                "env_file": args.env_file.resolve(),
            }
        )
    else:
        run_dir.mkdir(parents=True)
        copied = _prepare_inputs(
            run_dir=run_dir,
            experience_file=args.experience_file.resolve(),
            rollout_file=args.incumbent_rollout_file.resolve(),
            report_dir=args.incumbent_report_dir.resolve(),
            failure_artifact=args.failure_artifact.resolve(),
        )
        versions = store.list_versions()
        if not versions:
            raise RuntimeError("Checkpoint store has no accepted version")
        initial_version = versions[-1].version_id

        summary = _read_object(copied["report_dir"] / "summary.json")
        metrics = summary.get("metrics")
        if not isinstance(metrics, dict):
            raise TypeError("Incumbent report summary lacks metrics")

        control_config = _control_config(args.max_work_items)
        effects_config = LocalControlEffectsConfig(
            experience_file=copied["experience_file"],
            env_file=args.env_file.resolve(),
            actor_max_steps=args.actor_max_steps,
            teacher_max_turns=args.teacher_max_turns,
            rollout_workers=args.rollout_workers,
            rollouts_per_example=3,
            judge_workers=args.judge_workers,
            teacher_judge=True,
            show_progress=True,
            candidate_error_streak_limit=3,
        )
        run_id = uuid4().hex
        _write_object(
            run_dir / "run.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "start_mode": "researcher_from_existing_failure",
                "checkpoint_store": str(args.checkpoint_store.resolve()),
                "initial_version": initial_version,
                "control_config": asdict(control_config),
                "effects_config": {
                    **asdict(effects_config),
                    "experience_file": str(
                        effects_config.experience_file.resolve()
                    ),
                    "env_file": str(effects_config.env_file.resolve()),
                },
                "source_inputs": {
                    "experience_file": str(args.experience_file.resolve()),
                    "incumbent_rollout_file": str(
                        args.incumbent_rollout_file.resolve()
                    ),
                    "incumbent_report_dir": str(
                        args.incumbent_report_dir.resolve()
                    ),
                    "failure_artifact": str(
                        args.failure_artifact.resolve()
                    ),
                },
            },
        )

        first = WorkItem(
            work_id=f"research_hypothesis-{uuid4().hex[:16]}",
            kind=WorkKind.RESEARCH_HYPOTHESIS,
            subject_ref=f"generation:1:{initial_version}",
            input_refs={
                "rollout_file": str(copied["rollout_file"].resolve()),
                "report_dir": str(copied["report_dir"].resolve()),
                "failure_artifact": str(
                    copied["failure_artifact"].resolve()
                ),
            },
            payload={
                "generation": 1,
                "version_id": initial_version,
                "incumbent_metrics": metrics,
            },
        )
        journal.append_many(
            [
                (
                    "run_started",
                    {"run_id": run_id, "initial_version": initial_version},
                ),
                ("work_scheduled", {"work": first.to_dict()}),
            ]
        )
    effects = LocalControlEffects(store=store, config=effects_config)
    exhausted_resume_used = False

    while True:
        state = project_events(journal.read())
        if state.status == "completed":
            raise RuntimeError(
                "Controller completed before producing an "
                "evaluation-ready Candidate: "
                f"{state.status_reason}"
            )
        if (
            state.status == "paused"
            and state.status_reason is not None
            and state.status_reason.startswith("work failed after ")
            and not state.queued
        ):
            if args.resume_exhausted and not exhausted_resume_used:
                exhausted_resume_used = True
            else:
                raise RuntimeError(
                    "Controller exhausted the configured retry budget: "
                    f"{state.status_reason}"
                )
        if state.queued:
            next_work = state.queued[0].item
            print(
                f"[driver] next={next_work.kind.value} "
                f"completed={state.completed_work_count}",
                flush=True,
            )
            if next_work.kind is WorkKind.EVALUATE_CANDIDATE:
                _write_object(
                    run_dir / "ready.json",
                    {
                        "status": "ready_for_evaluation",
                        "candidate_iteration_id": next_work.payload.get(
                            "iteration_id"
                        ),
                        "candidate_digest": next_work.payload.get(
                            "candidate_digest"
                        ),
                        "conformance_summary": next_work.payload.get(
                            "conformance_summary"
                        ),
                        "evaluate_work": next_work.to_dict(),
                    },
                )
                print(
                    "[driver] READY_FOR_EVALUATION "
                    f"iteration={next_work.payload.get('iteration_id')}",
                    flush=True,
                )
                return

        started_count = sum(
            record.status in {"running", "completed", "failed"}
            for record in state.works.values()
        )
        if started_count >= control_config.max_work_items:
            raise RuntimeError(
                "Research-to-candidate work budget was exhausted before "
                "candidate evaluation became ready"
            )
        step_config = replace(
            control_config,
            max_work_items=started_count + 1,
        )
        controller = EvolutionController(
            run_dir=run_dir,
            effects=effects,
            config=step_config,
        )
        await controller.run()


def main() -> None:
    """Run one reproducible Researcher-to-Candidate experiment."""

    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()
