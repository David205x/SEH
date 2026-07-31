"""Start or resume the v2 evidence-driven Evolution Controller."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from search_harness.datasets import DatasetConfig, create_dataset_loader
from search_harness.evolution.experience import materialize_experience_set
from search_harness.versioning import HarnessVersionStore

from .controller import EvolutionController
from .domain import ControlOutcome, EvolutionControlConfig
from .effects import LocalControlEffects, LocalControlEffectsConfig


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Start a new controller run.")
    run.add_argument("--run-dir", type=Path, required=True)
    run.add_argument("--checkpoint-store", type=Path, required=True)
    run.add_argument("--dataset-path", type=Path)
    run.add_argument("--dataset-format")
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--max-generations", type=int, default=1)
    run.add_argument("--max-trials-per-hypothesis", type=int, default=4)
    run.add_argument("--max-trial-assignments", type=int, default=12)
    run.add_argument("--max-hypothesis-revisions", type=int, default=2)
    run.add_argument("--max-mechanism-revisions", type=int, default=2)
    run.add_argument("--max-compiler-revisions", type=int, default=2)
    run.add_argument("--max-candidate-revisions", type=int, default=2)
    run.add_argument("--max-work-retries", type=int, default=1)
    run.add_argument("--max-work-items", type=int, default=80)
    run.add_argument("--max-total-tokens", type=int)
    run.add_argument(
        "--min-accuracy-delta",
        type=float,
        default=-0.02,
        help=(
            "Deterministic safety floor for candidate accuracy delta; "
            "effect acceptance remains the Candidate Reviewer's decision."
        ),
    )
    run.add_argument("--max-total-token-ratio", type=float, default=3.0)
    _add_effect_arguments(run)

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
        if args.command == "run"
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
    store = HarnessVersionStore(args.checkpoint_store)
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
    control_config = EvolutionControlConfig(
        max_generations=args.max_generations,
        max_trials_per_hypothesis=args.max_trials_per_hypothesis,
        max_trial_assignments=args.max_trial_assignments,
        max_hypothesis_revisions=args.max_hypothesis_revisions,
        max_mechanism_revisions=args.max_mechanism_revisions,
        max_compiler_revisions=args.max_compiler_revisions,
        max_candidate_revisions=args.max_candidate_revisions,
        max_work_retries=args.max_work_retries,
        max_work_items=args.max_work_items,
        max_total_tokens=args.max_total_tokens,
        min_accuracy_delta=args.min_accuracy_delta,
        max_total_token_ratio=args.max_total_token_ratio,
    )
    effects_config = LocalControlEffectsConfig(
        experience_file=experience_file,
        env_file=args.env_file,
        actor_max_steps=args.actor_max_steps,
        teacher_max_turns=args.teacher_max_turns,
        rollout_workers=args.rollout_workers,
        rollouts_per_example=args.rollouts_per_example,
        judge_workers=args.judge_workers,
        teacher_judge=not args.no_teacher_judge,
        show_progress=not args.no_progress,
        candidate_error_streak_limit=args.candidate_error_streak_limit,
    )
    payload = {
        "schema_version": 1,
        "run_id": uuid4().hex,
        "checkpoint_store": str(store.root),
        "checkpoint_store_id": store.checkpoint_store_id,
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
    )
    controller.initialize(
        run_id=payload["run_id"],
        initial_version=payload["initial_version"],
    )
    return await controller.run()


async def _resume(args: argparse.Namespace) -> ControlOutcome:
    run_dir = args.run_dir.resolve()
    raw = _read_json(run_dir / "run.json")
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
    store = HarnessVersionStore(
        Path(_required_string(raw, "checkpoint_store"))
    )
    controller = EvolutionController(
        run_dir=run_dir,
        effects=LocalControlEffects(
            store=store,
            config=effects_config,
        ),
        config=control_config,
    )
    return await controller.run()


def _add_effect_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--actor-max-steps", type=int, default=20)
    parser.add_argument("--teacher-max-turns", type=int, default=20)
    parser.add_argument("--rollout-workers", type=int, default=2)
    parser.add_argument("--rollouts-per-example", type=int, default=1)
    parser.add_argument("--judge-workers", type=int, default=8)
    parser.add_argument(
        "--candidate-error-streak-limit",
        type=int,
        default=3,
        help=(
            "Stop candidate rollout after this many consecutive identical "
            "runner errors; default: 3."
        ),
    )
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


if __name__ == "__main__":
    main()
