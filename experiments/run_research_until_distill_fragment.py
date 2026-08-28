"""Run the formal research loop until Mechanism Distiller is queued."""

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
from search_harness.evolution.control.journal import ControlJournal
from search_harness.evolution.versioning import TemplateVersionStore


_RESEARCH_LOOP_WORK = frozenset(
    {
        WorkKind.RESEARCH_HYPOTHESIS,
        WorkKind.SELECT_TRIAL,
        WorkKind.EXECUTE_TRIAL,
        WorkKind.REVIEW_EVIDENCE,
        WorkKind.SUMMARIZE_CAPABILITY,
        WorkKind.SUMMARIZE_DIRECTION,
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the bounded research-loop arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def run_until_distill(
    args: argparse.Namespace,
) -> ControlOutcome:
    """Resume formal research work and stop before Mechanism Distiller."""

    run_dir = args.run_dir.resolve()
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 3:
        raise ValueError("Research-loop fragments require Run schema v3")
    _require_research_boundary(run_dir)

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
        stop_before=frozenset({WorkKind.DISTILL_MECHANISM})
    )
    _require_distill_boundary(run_dir, outcome)
    return outcome


def _require_research_boundary(run_dir: Path) -> None:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    if state.status != "running" or not state.queued:
        raise RuntimeError(
            "Run has no active research-loop work: "
            f"status={state.status}, reason={state.status_reason}"
        )
    unexpected = [
        record.item.kind
        for record in state.queued
        if record.item.kind not in _RESEARCH_LOOP_WORK
    ]
    if unexpected:
        raise RuntimeError(
            "Run is outside the pre-Distiller research loop: "
            f"{[item.value for item in unexpected]}"
        )


def _require_distill_boundary(
    run_dir: Path,
    outcome: ControlOutcome,
) -> None:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    if (
        state.status == "running"
        and state.queued
        and state.queued[0].item.kind is WorkKind.DISTILL_MECHANISM
    ):
        return
    raise RuntimeError(
        "Research loop ended before Evidence Reviewer accepted distillation: "
        f"status={outcome.status}, reason={outcome.reason}"
    )


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
    """Run the research loop and report the Distiller boundary."""

    args = parse_args(argv)
    outcome = asyncio.run(run_until_distill(args))
    print(
        "debug fragment ready: "
        "completed=research_loop, "
        "stop_before=distill_mechanism, "
        f"work_items={outcome.completed_work_count}, "
        f"tokens={outcome.total_tokens}"
    )
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
