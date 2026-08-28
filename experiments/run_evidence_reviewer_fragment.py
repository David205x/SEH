"""Run the queued Evidence Reviewer from persisted Trial Reviews only."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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
    """Parse the Evidence Reviewer fragment arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def run_evidence_reviewer(
    args: argparse.Namespace,
) -> tuple[ControlOutcome, Path, tuple[WorkKind, ...]]:
    """Reuse Trial Reviews, run aggregate review, and stop before its route."""

    run_dir = args.run_dir.resolve()
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 3:
        raise ValueError("Evidence Reviewer fragments require Run schema v3")
    review_work = _require_ready_boundary(run_dir)
    stage_path = (
        ControlArtifactStore(run_dir / "artifacts")
        .work_dir(review_work.work_id)
        / "trial_review_stage.json"
    )
    stage = _validate_trial_review_stage(
        path=stage_path,
        work=review_work,
    )

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

    local_effects = LocalControlEffects(store=store, config=effects_config)
    recording_runner = _RecordingRoleRunner(local_effects.role_runner)
    local_effects.role_runner = recording_runner  # type: ignore[assignment]
    effects = _EvidenceAccountingEffects(
        inner=local_effects,
        stage_path=stage_path,
        stage=stage,
    )
    controller = EvolutionController(
        run_dir=run_dir,
        effects=effects,
        config=control_config,
    )
    downstream = frozenset(
        kind for kind in WorkKind if kind is not WorkKind.REVIEW_EVIDENCE
    )
    outcome = await controller.run(stop_before=downstream)
    artifact, next_kinds = _require_completed_boundary(run_dir)
    if recording_runner.role_ids != ["evidence_reviewer"]:
        raise RuntimeError(
            "Evidence stage invoked unexpected Teacher Roles: "
            f"{recording_runner.role_ids}"
        )
    _mark_trial_review_usage_charged(
        path=stage_path,
        stage=stage,
        review_work_id=review_work.work_id,
    )
    return outcome, artifact, next_kinds


class _RecordingRoleRunner:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.role_ids: list[str] = []

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        role_id = kwargs.get("role_id")
        if not isinstance(role_id, str):
            raise TypeError("Teacher Role invocation lacks role_id")
        self.role_ids.append(role_id)
        return await self.inner.run(**kwargs)


class _EvidenceAccountingEffects:
    """Charge the previously executed Trial Reviewer stage exactly once."""

    def __init__(
        self,
        *,
        inner: LocalControlEffects,
        stage_path: Path,
        stage: dict[str, Any],
    ) -> None:
        self.inner = inner
        self.stage_path = stage_path.resolve()
        self.stage = stage

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        result = await self.inner.execute(
            work=work,
            state=state,
            work_dir=work_dir,
        )
        if work.kind is not WorkKind.REVIEW_EVIDENCE:
            return result
        expected_reviews = self.stage.get("trial_reviews")
        if result.outcome.get("trial_reviews") != expected_reviews:
            raise RuntimeError(
                "Evidence Reviewer did not reuse the persisted Trial Reviews"
            )
        pending_tokens = _stage_total_tokens(self.stage)
        usage = dict(result.usage)
        usage["total_tokens"] = (
            int(usage.get("total_tokens", 0)) + pending_tokens
        )
        return EffectResult(
            outcome=dict(result.outcome),
            artifact_refs={
                **result.artifact_refs,
                "trial_review_stage_artifact": str(self.stage_path),
            },
            usage=usage,
        )


def _require_ready_boundary(run_dir: Path) -> WorkItem:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    queued = state.queued
    if (
        state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.REVIEW_EVIDENCE
    ):
        raise RuntimeError(
            "Run is not waiting for Evidence Reviewer: "
            f"status={state.status}, reason={state.status_reason}"
        )
    return queued[0].item


def _validate_trial_review_stage(
    *,
    path: Path,
    work: WorkItem,
) -> dict[str, Any]:
    stage = _read_object(path)
    if stage.get("schema_version") != 1 or stage.get("status") != "completed":
        raise ValueError("Trial Review stage is not a completed schema-v1 stage")
    if stage.get("review_work_id") != work.work_id:
        raise ValueError("Trial Review stage belongs to another WorkItem")
    if stage.get("charged_to_controller") is not False:
        raise ValueError("Trial Review usage was already charged to Controller")
    trial_files = stage.get("trial_files")
    if not isinstance(trial_files, list) or not trial_files:
        raise ValueError("Trial Review stage lacks trial_files")
    work_trials = [
        value
        for key, value in sorted(work.input_refs.items())
        if key.startswith("trial_") and key[6:].isdigit()
    ]
    if trial_files != work_trials:
        raise ValueError("Trial Review stage Trial set differs from WorkItem")
    reviews = stage.get("trial_reviews")
    if not isinstance(reviews, list) or len(reviews) != len(trial_files):
        raise ValueError("Trial Review stage has incomplete review outputs")
    _stage_total_tokens(stage)
    return stage


def _stage_total_tokens(stage: dict[str, Any]) -> int:
    usage = stage.get("usage")
    if not isinstance(usage, dict):
        raise TypeError("Trial Review stage usage must be an object")
    tokens = usage.get("total_tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        raise TypeError("Trial Review stage total_tokens must be non-negative")
    return tokens


def _require_completed_boundary(
    run_dir: Path,
) -> tuple[Path, tuple[WorkKind, ...]]:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    completed = [
        record
        for record in state.works.values()
        if record.item.kind is WorkKind.REVIEW_EVIDENCE
        and record.status == "completed"
    ]
    if len(completed) != 1:
        raise RuntimeError(
            "Evidence Reviewer did not complete exactly one WorkItem"
        )
    effect = ControlArtifactStore(run_dir / "artifacts").load_effect(
        completed[0].item.work_id
    )
    artifact = effect.artifact_refs.get("reviewer_artifact")
    if artifact is None or not Path(artifact).is_file():
        raise FileNotFoundError(
            f"Evidence Reviewer artifact is missing: {artifact}"
        )
    return Path(artifact).resolve(), tuple(
        record.item.kind for record in state.queued
    )


def _mark_trial_review_usage_charged(
    *,
    path: Path,
    stage: dict[str, Any],
    review_work_id: str,
) -> None:
    updated = dict(stage)
    updated["charged_to_controller"] = True
    updated["charged_in_work_id"] = review_work_id
    _write_object(path, updated)


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
    """Run Evidence Reviewer and print its formally routed next boundary."""

    args = parse_args(argv)
    outcome, artifact, next_kinds = asyncio.run(
        run_evidence_reviewer(args)
    )
    next_text = ",".join(kind.value for kind in next_kinds) or "none"
    print(
        "debug fragment ready: "
        "completed=evidence_reviewer, "
        f"stop_before={next_text}, "
        f"tokens={outcome.total_tokens}"
    )
    print(f"evidence_reviewer_artifact={artifact}")
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
