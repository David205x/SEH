"""Start a manually inspectable Evolution fragment at Incumbent Evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from search_harness._internal import (
    evolution_control_values,
    evolution_effect_values,
    read_runtime_config,
)
from search_harness.datasets import DatasetConfig, create_dataset_loader
from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    ControlOutcome,
    EvolutionControlConfig,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.journal import ControlJournal
from search_harness.evolution.experience import materialize_experience_set
from search_harness.evolution.identifiers import new_run_id
from search_harness.evolution.versioning import TemplateVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the first debug-fragment stage arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--version-store", type=Path, required=True)
    parser.add_argument("--dataset-path", type=Path)
    parser.add_argument("--dataset-format")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--no-teacher-judge", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def start_incumbent_fragment(
    args: argparse.Namespace,
) -> ControlOutcome:
    """Run the formal Incumbent Evaluation and stop before Failure Analyst."""

    run_dir = args.run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(
            f"Debug fragment directory already exists: {run_dir}"
        )

    runtime = read_runtime_config(env_file=args.env_file)
    control_config = EvolutionControlConfig(
        **evolution_control_values(runtime)
    )
    store = TemplateVersionStore(args.version_store)
    versions = store.list_versions()
    if not versions:
        raise RuntimeError(
            f"Harness Version Store is not initialized: {store.root}"
        )

    dataset = (
        DatasetConfig.from_env(env_file=args.env_file)
        if args.dataset_path is None
        else DatasetConfig(
            path=args.dataset_path,
            **(
                {"format_name": args.dataset_format}
                if args.dataset_format
                else {}
            ),
        )
    )
    experience_file = run_dir / "experience_set.jsonl"
    selected, digest = materialize_experience_set(
        create_dataset_loader(dataset).iter_examples(),
        experience_file,
        limit=args.limit,
    )
    effects_config = LocalControlEffectsConfig(
        experience_file=experience_file,
        env_file=args.env_file,
        **evolution_effect_values(runtime),
        teacher_judge=not args.no_teacher_judge,
        show_progress=not args.no_progress,
    )
    run_id = new_run_id()
    initial_version = versions[-1].version_id
    _write_json(
        run_dir / "run.json",
        {
            "schema_version": 3,
            "run_id": run_id,
            "version_store": str(store.root),
            "version_store_id": store.version_store_id,
            "initial_version": initial_version,
            "control_config": asdict(control_config),
            "effects_config": _effects_dict(effects_config),
            "experience_set": {
                "path": str(experience_file.resolve()),
                "count": len(selected),
                "digest": digest,
            },
            "dataset": {
                "path": str(dataset.path.resolve()),
                "format": dataset.format_name,
                "filter_status": dataset.filter_status,
            },
        },
    )

    controller = EvolutionController(
        run_dir=run_dir,
        effects=LocalControlEffects(store=store, config=effects_config),
        config=control_config,
    )
    controller.initialize(
        run_id=run_id,
        initial_version=initial_version,
    )
    outcome = await controller.run(
        stop_before=frozenset({WorkKind.ANALYZE_FAILURE})
    )
    _require_incumbent_boundary(run_dir)
    return outcome


def _require_incumbent_boundary(run_dir: Path) -> None:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    completed = [
        record
        for record in state.works.values()
        if record.item.kind is WorkKind.EVALUATE_INCUMBENT
        and record.status == "completed"
    ]
    queued = state.queued
    if (
        len(completed) != 1
        or state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.ANALYZE_FAILURE
    ):
        raise RuntimeError(
            "Incumbent Evaluation did not reach the manual review boundary: "
            f"status={state.status}, reason={state.status_reason}"
        )


def _effects_dict(config: LocalControlEffectsConfig) -> dict[str, Any]:
    return {
        **asdict(config),
        "experience_file": str(config.experience_file.resolve()),
        "env_file": str(config.env_file.resolve()),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Start one fragment and report its first manual review boundary."""

    args = parse_args(argv)
    outcome = asyncio.run(start_incumbent_fragment(args))
    print(
        "debug fragment ready: "
        "completed=evaluate_incumbent, "
        "stop_before=analyze_failure, "
        f"tokens={outcome.total_tokens}"
    )
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
