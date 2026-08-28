"""Run one queued Hypothesis Researcher and stop before Trial Selection."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    ControlOutcome,
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
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
    """Parse the Hypothesis Researcher fragment arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def run_hypothesis_researcher(
    args: argparse.Namespace,
) -> tuple[ControlOutcome, Path]:
    """Execute the queued Researcher with relocated Run paths if needed."""

    run_dir = args.run_dir.resolve()
    run_file = run_dir / "run.json"
    payload = _read_object(run_file)
    if payload.get("schema_version") != 3:
        raise ValueError("Hypothesis Researcher fragments require Run schema v3")
    _require_ready_boundary(run_dir)

    stored_effects = _required_object(payload, "effects_config")
    source_root = _normalize_run_location(
        payload=payload,
        run_dir=run_dir,
    )
    if source_root != run_dir:
        _write_object(run_file, payload)
        stored_effects = _required_object(payload, "effects_config")
    if args.env_file is not None:
        stored_effects["env_file"] = str(args.env_file.resolve())
    if args.no_progress:
        stored_effects["show_progress"] = False

    control_config = EvolutionControlConfig(
        **_required_object(payload, "control_config")
    )
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

    effects = _RelocatedInputEffects(
        inner=LocalControlEffects(store=store, config=effects_config),
        source_root=source_root,
        run_dir=run_dir,
    )
    controller = EvolutionController(
        run_dir=run_dir,
        effects=effects,
        config=control_config,
    )
    outcome = await controller.run(
        stop_before=frozenset({WorkKind.SELECT_TRIAL})
    )
    artifact = _require_completed_boundary(run_dir)
    return outcome, artifact


class _RelocatedInputEffects:
    """Rebase missing WorkItem paths without rewriting the existing Journal."""

    def __init__(
        self,
        *,
        inner: LocalControlEffects,
        source_root: Path,
        run_dir: Path,
    ) -> None:
        self.inner = inner
        self.source_root = source_root.resolve()
        self.run_dir = run_dir.resolve()

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        rebased_refs = {
            name: _rebase_existing_path(
                value,
                source_root=self.source_root,
                run_dir=self.run_dir,
            )
            for name, value in work.input_refs.items()
        }
        rebound = replace(work, input_refs=rebased_refs)
        result = await self.inner.execute(
            work=rebound,
            state=state,
            work_dir=work_dir,
        )
        corrected_refs = {
            name: value
            for name, value in rebased_refs.items()
            if work.input_refs.get(name) != value
        }
        return EffectResult(
            outcome=dict(result.outcome),
            artifact_refs={
                **corrected_refs,
                **result.artifact_refs,
            },
            usage=dict(result.usage),
        )


def _normalize_run_location(
    *,
    payload: dict[str, Any],
    run_dir: Path,
) -> Path:
    effects = _required_object(payload, "effects_config")
    experience = _required_object(payload, "experience_set")
    stored = Path(_required_string(effects, "experience_file")).resolve()
    recorded = Path(_required_string(experience, "path")).resolve()
    if stored != recorded:
        raise ValueError(
            "Run experience paths disagree before relocation: "
            f"{stored} != {recorded}"
        )
    current = (run_dir / "experience_set.jsonl").resolve()
    if stored == current:
        return run_dir
    if stored.exists():
        raise ValueError(
            "Run references an existing external Experience Set; "
            "automatic relocation is ambiguous"
        )
    if not current.is_file():
        raise FileNotFoundError(
            f"Relocated Experience Set is missing: {current}"
        )
    effects["experience_file"] = str(current)
    experience["path"] = str(current)
    payload["effects_config"] = effects
    payload["experience_set"] = experience
    return stored.parent


def _rebase_existing_path(
    value: str,
    *,
    source_root: Path,
    run_dir: Path,
) -> str:
    path = Path(value).resolve()
    if path.exists() or source_root == run_dir:
        return str(path)
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        return str(path)
    candidate = (run_dir / relative).resolve()
    return str(candidate) if candidate.exists() else str(path)


def _require_ready_boundary(run_dir: Path) -> None:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    queued = state.queued
    if (
        state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.RESEARCH_HYPOTHESIS
    ):
        raise RuntimeError(
            "Run is not waiting for Hypothesis Researcher: "
            f"status={state.status}, reason={state.status_reason}"
        )


def _require_completed_boundary(run_dir: Path) -> Path:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    completed = [
        record
        for record in state.works.values()
        if record.item.kind is WorkKind.RESEARCH_HYPOTHESIS
        and record.status == "completed"
    ]
    queued = state.queued
    if (
        len(completed) != 1
        or state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.SELECT_TRIAL
    ):
        raise RuntimeError(
            "Hypothesis Researcher did not reach the manual review boundary: "
            f"status={state.status}, reason={state.status_reason}"
        )
    effect = ControlArtifactStore(run_dir / "artifacts").load_effect(
        completed[0].item.work_id
    )
    artifact = effect.artifact_refs.get("hypothesis_artifact")
    if artifact is None:
        raise RuntimeError("Researcher effect lacks hypothesis_artifact")
    path = Path(artifact)
    if not path.is_file():
        raise FileNotFoundError(f"Researcher artifact is missing: {path}")
    return path.resolve()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


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
    """Run Hypothesis Researcher and print the next manual boundary."""

    args = parse_args(argv)
    outcome, artifact = asyncio.run(run_hypothesis_researcher(args))
    print(
        "debug fragment ready: "
        "completed=research_hypothesis, "
        "stop_before=select_trial, "
        f"tokens={outcome.total_tokens}"
    )
    print(f"hypothesis_artifact={artifact}")
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
