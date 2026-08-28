"""Start or resume the evidence-driven Evolution Controller."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from search_harness.datasets import DatasetConfig, create_dataset_loader
from search_harness._internal import (
    evolution_control_values,
    evolution_effect_values,
    read_runtime_config,
)
from search_harness.evolution.experience import materialize_experience_set
from search_harness.evolution.identifiers import new_run_id
from search_harness.evolution.versioning import TemplateVersionStore

from .controller import ControlProjection, EvolutionController
from .domain import ControlOutcome, EvolutionControlConfig
from .effects import LocalControlEffects, LocalControlEffectsConfig


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m search_harness evolve",
        description=__doc__,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", help="Start a new controller run.")
    start.add_argument("--run-dir", type=Path, required=True)
    start.add_argument("--version-store", type=Path, required=True)
    start.add_argument("--dataset-path", type=Path)
    start.add_argument("--dataset-format")
    start.add_argument("--limit", type=int, default=20)
    _add_effect_arguments(start)

    resume = commands.add_parser(
        "resume",
        help="Resume a durable controller run.",
    )
    resume.add_argument("run_dir", type=Path)
    resume.add_argument("--env-file", type=Path)
    resume.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    outcome = (
        asyncio.run(_start(args))
        if args.command == "start"
        else asyncio.run(_resume(args))
    )
    print(
        f"evolution controller {outcome.status}: "
        f"generation={outcome.generation}, "
        f"work_items={outcome.completed_work_count}, "
        f"tokens={outcome.total_tokens}, "
        f"latest={outcome.current_version}"
    )
    print(outcome.reason)


async def _start(args: argparse.Namespace) -> ControlOutcome:
    run_dir = args.run_dir.resolve()
    run_file = run_dir / "run.json"
    if run_file.exists():
        raise FileExistsError(
            f"Evolution Controller run already exists: {run_dir}"
        )
    runtime = read_runtime_config(env_file=args.env_file)
    control_config = EvolutionControlConfig(
        **evolution_control_values(runtime)
    )
    effect_values = evolution_effect_values(runtime)
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
        **effect_values,
        teacher_judge=not args.no_teacher_judge,
        show_progress=not args.no_progress,
    )
    payload = {
        "schema_version": 3,
        "run_id": new_run_id(),
        "version_store": str(store.root),
        "version_store_id": store.version_store_id,
        "initial_version": versions[-1].version_id,
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
    }
    _write_json(run_file, payload)
    controller = EvolutionController(
        run_dir=run_dir,
        effects=LocalControlEffects(
            store=store,
            config=effects_config,
        ),
        config=control_config,
        projections=_automatic_projections(
            run_dir=run_dir,
            env_file=effects_config.env_file,
        ),
    )
    controller.initialize(
        run_id=payload["run_id"],
        initial_version=payload["initial_version"],
    )
    return await controller.run()


async def _resume(args: argparse.Namespace) -> ControlOutcome:
    run_dir = args.run_dir.resolve()
    raw = _read_run_payload(run_dir / "run.json")
    control_config = EvolutionControlConfig(
        **_required_object(raw, "control_config")
    )
    stored_effects = _required_object(raw, "effects_config")
    if args.env_file is not None:
        stored_effects["env_file"] = str(args.env_file.resolve())
    if args.no_progress:
        stored_effects["show_progress"] = False
    effects_config = LocalControlEffectsConfig(
        **{
            **stored_effects,
            "experience_file": Path(
                _required_string(stored_effects, "experience_file")
            ),
            "env_file": Path(
                _required_string(stored_effects, "env_file")
            ),
        }
    )
    store = TemplateVersionStore(
        Path(_required_string(raw, "version_store"))
    )
    expected_store_id = _required_string(raw, "version_store_id")
    if store.version_store_id != expected_store_id:
        raise ValueError(
            "Evolution Run version_store_id does not match Version Store: "
            f"{expected_store_id} != {store.version_store_id}"
        )
    controller = EvolutionController(
        run_dir=run_dir,
        effects=LocalControlEffects(
            store=store,
            config=effects_config,
        ),
        config=control_config,
        projections=_automatic_projections(
            run_dir=run_dir,
            env_file=effects_config.env_file,
        ),
    )
    return await controller.run()


def _automatic_projections(
    *,
    run_dir: Path,
    env_file: Path,
) -> tuple[ControlProjection, ...]:
    """Compose non-decision Run projections enabled by runtime config."""

    from evolution_observer.timeline import timeline_projection_from_runtime

    timeline = timeline_projection_from_runtime(
        run_dir=run_dir,
        env_file=env_file,
    )
    return (timeline,) if timeline is not None else ()


def _add_effect_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--no-teacher-judge", action="store_true")
    parser.add_argument("--no-progress", action="store_true")


def _effects_dict(config: LocalControlEffectsConfig) -> dict[str, Any]:
    return {
        **asdict(config),
        "experience_file": str(config.experience_file.resolve()),
        "env_file": str(config.env_file.resolve()),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return value


def _read_run_payload(path: Path) -> dict[str, Any]:
    """Read the current Run Artifact schema."""

    raw = _read_json(path)
    schema_version = raw.get("schema_version")
    if schema_version != 3:
        raise ValueError(
            f"unsupported Evolution Run schema_version: {schema_version}"
        )
    _required_string(raw, "version_store")
    _required_string(raw, "version_store_id")
    return raw


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _required_object(
    value: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item
