"""Run the research chain from incumbent evidence to an evaluation-ready Candidate."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from search_harness._internal import (
    evolution_control_values,
    evolution_effect_values,
    read_runtime_config,
)
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
from search_harness.evolution.versioning import TemplateVersionStore


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reuse an incumbent evaluation, optionally reuse its Failure "
            "Analyst result, and stop after Mechanism Conformance Replay "
            "schedules candidate evaluation."
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--version-store", type=Path, required=True)
    parser.add_argument("--experience-file", type=Path, required=True)
    parser.add_argument("--incumbent-rollout-file", type=Path, required=True)
    parser.add_argument("--incumbent-report-dir", type=Path, required=True)
    parser.add_argument(
        "--failure-artifact",
        type=Path,
        help=(
            "Reuse an existing Failure Analyst artifact. Omit this option "
            "to run Failure Analyst through the normal Controller route."
        ),
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
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
    failure_artifact: Path | None,
) -> dict[str, Path]:
    inputs_dir = run_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=False)
    copied_report = inputs_dir / "incumbent_report"
    shutil.copytree(report_dir, copied_report)
    copied = {
        "experience_file": run_dir / "experience_set.jsonl",
        "rollout_file": inputs_dir / "incumbent_rollouts.jsonl",
        "report_dir": copied_report,
    }
    shutil.copy2(experience_file, copied["experience_file"])
    shutil.copy2(rollout_file, copied["rollout_file"])
    if failure_artifact is not None:
        copied["failure_artifact"] = inputs_dir / "failure_analyst.json"
        shutil.copy2(failure_artifact, copied["failure_artifact"])
    return copied


async def _run(args: argparse.Namespace) -> None:
    run_dir = args.run_dir.resolve()
    store = TemplateVersionStore(args.version_store.resolve())
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
            failure_artifact=(
                args.failure_artifact.resolve()
                if args.failure_artifact is not None
                else None
            ),
        )
        versions = store.list_versions()
        if not versions:
            raise RuntimeError("Checkpoint store has no accepted version")
        initial_version = versions[-1].version_id

        summary = _read_object(copied["report_dir"] / "summary.json")
        metrics = summary.get("metrics")
        if not isinstance(metrics, dict):
            raise TypeError("Incumbent report summary lacks metrics")

        runtime = read_runtime_config(env_file=args.env_file)
        control_config = EvolutionControlConfig(
            **evolution_control_values(runtime)
        )
        effects_config = LocalControlEffectsConfig(
            experience_file=copied["experience_file"],
            env_file=args.env_file.resolve(),
            **evolution_effect_values(runtime),
            teacher_judge=True,
            show_progress=True,
        )
        run_id = uuid4().hex
        start_from_failure = "failure_artifact" in copied
        _write_object(
            run_dir / "run.json",
            {
                "schema_version": 2,
                "run_id": run_id,
                "start_mode": (
                    "researcher_from_existing_failure"
                    if start_from_failure
                    else "failure_analyst_from_existing_incumbent"
                ),
                "version_store": str(args.version_store.resolve()),
                "version_store_id": store.version_store_id,
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
                    "failure_artifact": (
                        str(args.failure_artifact.resolve())
                        if args.failure_artifact is not None
                        else None
                    ),
                },
            },
        )

        first = WorkItem(
            work_id=(
                f"research_hypothesis-{uuid4().hex[:16]}"
                if start_from_failure
                else f"analyze_failure-{uuid4().hex[:16]}"
            ),
            kind=(
                WorkKind.RESEARCH_HYPOTHESIS
                if start_from_failure
                else WorkKind.ANALYZE_FAILURE
            ),
            subject_ref=f"generation:1:{initial_version}",
            input_refs={
                "rollout_file": str(copied["rollout_file"].resolve()),
                "report_dir": str(copied["report_dir"].resolve()),
                **(
                    {
                        "failure_artifact": str(
                            copied["failure_artifact"].resolve()
                        )
                    }
                    if start_from_failure
                    else {}
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
                        "candidate_attempt_id": next_work.payload.get(
                            "candidate_attempt_id"
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
                    "candidate_attempt_id="
                    f"{next_work.payload.get('candidate_attempt_id')}",
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
