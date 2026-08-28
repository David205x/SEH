"""Run one queued Failure Analyst and stop before Hypothesis Researcher."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

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
from search_harness.evolution.control.journal import (
    ControlArtifactStore,
    ControlJournal,
)
from search_harness.evolution.versioning import TemplateVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the Failure Analyst fragment arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def run_failure_analyst(
    args: argparse.Namespace,
) -> tuple[ControlOutcome, Path]:
    """Execute the formally queued Analyst work and persist its artifact."""

    run_dir = args.run_dir.resolve()
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 3:
        raise ValueError("Failure Analyst fragments require Run schema v3")
    _require_ready_boundary(run_dir)

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

    controller = EvolutionController(
        run_dir=run_dir,
        effects=LocalControlEffects(store=store, config=effects_config),
        config=control_config,
    )
    outcome = await controller.run(
        stop_before=frozenset({WorkKind.RESEARCH_HYPOTHESIS})
    )
    artifact = _require_completed_boundary(run_dir)
    return outcome, artifact


def _require_ready_boundary(run_dir: Path) -> None:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    queued = state.queued
    if (
        state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.ANALYZE_FAILURE
    ):
        raise RuntimeError(
            "Run is not waiting for Failure Analyst: "
            f"status={state.status}, reason={state.status_reason}"
        )


def _require_completed_boundary(run_dir: Path) -> Path:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    completed = [
        record
        for record in state.works.values()
        if record.item.kind is WorkKind.ANALYZE_FAILURE
        and record.status == "completed"
    ]
    queued = state.queued
    if (
        len(completed) != 1
        or state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.RESEARCH_HYPOTHESIS
    ):
        raise RuntimeError(
            "Failure Analyst did not reach the manual review boundary: "
            f"status={state.status}, reason={state.status_reason}"
        )
    effect = ControlArtifactStore(run_dir / "artifacts").load_effect(
        completed[0].item.work_id
    )
    artifact = effect.artifact_refs.get("failure_artifact")
    if artifact is None:
        raise RuntimeError("Failure Analyst effect lacks failure_artifact")
    path = Path(artifact)
    if not path.is_file():
        raise FileNotFoundError(f"Failure Analyst artifact is missing: {path}")
    return path.resolve()


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


def main(argv: Sequence[str] | None = None) -> None:
    """Run Failure Analyst and print the next manual boundary."""

    args = parse_args(argv)
    outcome, artifact = asyncio.run(run_failure_analyst(args))
    print(
        "debug fragment ready: "
        "completed=analyze_failure, "
        "stop_before=research_hypothesis, "
        f"tokens={outcome.total_tokens}"
    )
    print(f"failure_artifact={artifact}")
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
