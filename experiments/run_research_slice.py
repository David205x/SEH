"""Run a real Controller route until a selected downstream work boundary."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from evolution_observer.timeline import timeline_projection_from_runtime
from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    EvolutionControlConfig,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.journal import ControlJournal
from search_harness.evolution.versioning import TemplateVersionStore


SUPPORTED_BOUNDARIES = (
    WorkKind.DISTILL_MECHANISM,
    WorkKind.COMPILE_CANDIDATE,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the research-slice command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--stop-before",
        choices=[item.value for item in SUPPORTED_BOUNDARIES],
        default=WorkKind.DISTILL_MECHANISM.value,
        help=(
            "Stop with this formally routed WorkItem still queued. "
            "The default excludes Mechanism Distiller."
        ),
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def run_research_slice(args: argparse.Namespace) -> None:
    """Resume one Run through the Controller until the requested boundary."""

    run_dir = args.run_dir.resolve()
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 2:
        raise ValueError("Research slices only support Evolution Run schema v2")

    control_config = EvolutionControlConfig(
        **_required_object(payload, "control_config")
    )
    stored_effects = _required_object(payload, "effects_config")
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
        Path(_required_string(payload, "version_store"))
    )
    expected_store_id = _required_string(payload, "version_store_id")
    if store.version_store_id != expected_store_id:
        raise ValueError(
            "Evolution Run version_store_id does not match Version Store: "
            f"{expected_store_id} != {store.version_store_id}"
        )

    timeline = timeline_projection_from_runtime(
        run_dir=run_dir,
        env_file=effects_config.env_file,
    )
    controller = EvolutionController(
        run_dir=run_dir,
        effects=LocalControlEffects(store=store, config=effects_config),
        config=control_config,
        projections=(timeline,) if timeline is not None else (),
    )
    boundary = WorkKind(args.stop_before)
    outcome = await controller.run(stop_before=frozenset({boundary}))
    state = project_events(ControlJournal(run_dir / "events.jsonl").read())

    if (
        state.status != "running"
        or not state.queued
        or state.queued[0].item.kind is not boundary
    ):
        raise RuntimeError(
            "Controller stopped before reaching the requested boundary: "
            f"status={outcome.status}, reason={outcome.reason}"
        )

    completed_counts: dict[str, int] = {}
    for record in state.works.values():
        if record.status != "completed":
            continue
        kind = record.item.kind.value
        completed_counts[kind] = completed_counts.get(kind, 0) + 1
    counts = ", ".join(
        f"{kind}={count}" for kind, count in sorted(completed_counts.items())
    )
    print(
        "research slice ready: "
        f"stop_before={boundary.value}, "
        f"generation={state.generation}, "
        f"work_items={state.completed_work_count}, "
        f"tokens={state.total_tokens}"
    )
    print(f"completed work: {counts}")
    print(
        "The boundary WorkItem remains queued; use "
        "'python -m search_harness evolve resume' to continue the Run."
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the research slice command."""

    asyncio.run(run_research_slice(parse_args(argv)))


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
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
