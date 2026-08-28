"""Run Trial Selection, Intervention Workers, and Trial Reviewers only."""

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
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import (
    TEACHER_TEMPLATE_ROOT,
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.evidence_review_effects import (
    EvidenceReviewEffects,
)
from search_harness.evolution.control.journal import (
    ControlArtifactStore,
    ControlJournal,
)
from search_harness.evolution.research.roles.contracts import (
    InterventionHypothesis,
)
from search_harness.evolution.versioning import TemplateVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the Intervention and Trial Reviewer fragment arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument(
        "--workers-only",
        action="store_true",
        help="Stop after Intervention Workers, before Trial Reviewers.",
    )
    return parser.parse_args(argv)


async def run_intervention_trial_reviews(
    args: argparse.Namespace,
) -> tuple[ControlOutcome, Path, EffectResult | None]:
    """Execute one selected Trial batch and its per-Trial reviews."""

    run_dir = args.run_dir.resolve()
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 3:
        raise ValueError("Intervention fragments require Run schema v3")
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

    local_effects = LocalControlEffects(store=store, config=effects_config)
    controller = EvolutionController(
        run_dir=run_dir,
        effects=local_effects,
        config=control_config,
    )
    outcome = await controller.run(
        stop_before=frozenset({WorkKind.REVIEW_EVIDENCE})
    )
    review_work, trial_paths = _require_trial_review_boundary(run_dir)
    if args.workers_only:
        manifest = _persist_intervention_stage(
            run_dir=run_dir,
            review_work=review_work,
            trial_paths=trial_paths,
        )
        return outcome, manifest, None
    hypothesis = _load_hypothesis(
        Path(review_work.input_refs["hypothesis_artifact"])
    )
    review_result = await EvidenceReviewEffects(
        role_runner=local_effects.role_runner,
        trial_reviewer_template_root=(
            TEACHER_TEMPLATE_ROOT / "trial_reviewer"
        ),
        evidence_reviewer_template_root=(
            TEACHER_TEMPLATE_ROOT / "evidence_reviewer"
        ),
        judge_workers=effects_config.judge_workers,
    ).review(
        hypothesis=hypothesis,
        trial_paths=trial_paths,
        persisted_trial_reviews={},
        budget={},
        prior_obligation=review_work.payload.get("prior_obligation"),
        work_dir=ControlArtifactStore(run_dir / "artifacts").work_dir(
            review_work.work_id
        ),
        trial_reviews_only=True,
    )
    manifest = _persist_trial_review_stage(
        run_dir=run_dir,
        review_work_id=review_work.work_id,
        trial_paths=trial_paths,
        result=review_result,
    )
    _validate_trial_review_result(
        result=review_result,
        expected_count=len(trial_paths),
    )
    return outcome, manifest, review_result


def _persist_intervention_stage(
    *,
    run_dir: Path,
    review_work: WorkItem,
    trial_paths: list[Path],
) -> Path:
    path = (
        ControlArtifactStore(run_dir / "artifacts")
        .work_dir(review_work.work_id)
        / "intervention_stage.json"
    )
    _write_object(
        path,
        {
            "schema_version": 1,
            "status": "completed",
            "review_work_id": review_work.work_id,
            "hypothesis_artifact": review_work.input_refs[
                "hypothesis_artifact"
            ],
            "trial_files": [str(item) for item in trial_paths],
            "charged_to_controller": True,
        },
    )
    return path.resolve()


def _require_ready_boundary(run_dir: Path) -> None:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    queued = state.queued
    if (
        state.status != "running"
        or not queued
        or queued[0].item.kind is not WorkKind.SELECT_TRIAL
    ):
        raise RuntimeError(
            "Run is not waiting for Trial Selection: "
            f"status={state.status}, reason={state.status_reason}"
        )


def _require_trial_review_boundary(
    run_dir: Path,
) -> tuple[WorkItem, list[Path]]:
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
            "Intervention batch did not reach Trial Review boundary: "
            f"status={state.status}, reason={state.status_reason}"
        )
    work = queued[0].item
    trial_refs = [
        value
        for key, value in sorted(work.input_refs.items())
        if key.startswith("trial_") and key[6:].isdigit()
    ]
    if not trial_refs:
        raise RuntimeError("Evidence Review WorkItem has no executed Trials")
    trial_paths = [Path(value).resolve() for value in trial_refs]
    missing = [str(path) for path in trial_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Executed Trial artifacts are missing: {missing}"
        )
    return work, trial_paths


def _load_hypothesis(path: Path) -> dict[str, Any]:
    artifact = _read_object(path)
    output = _required_object(artifact, "output")
    hypothesis = _required_object(output, "hypothesis")
    return InterventionHypothesis.model_validate(hypothesis).model_dump(
        mode="json"
    )


def _persist_trial_review_stage(
    *,
    run_dir: Path,
    review_work_id: str,
    trial_paths: list[Path],
    result: EffectResult,
) -> Path:
    path = (
        ControlArtifactStore(run_dir / "artifacts").work_dir(review_work_id)
        / "trial_review_stage.json"
    )
    _write_object(
        path,
        {
            "schema_version": 1,
            "status": "completed",
            "review_work_id": review_work_id,
            "trial_files": [str(item) for item in trial_paths],
            "trial_reviews": result.outcome["trial_reviews"],
            "artifact_refs": dict(result.artifact_refs),
            "usage": dict(result.usage),
            "charged_to_controller": False,
        },
    )
    return path.resolve()


def _validate_trial_review_result(
    *,
    result: EffectResult,
    expected_count: int,
) -> None:
    raw_reviews = result.outcome.get("trial_reviews")
    if not isinstance(raw_reviews, list) or len(raw_reviews) != expected_count:
        raise RuntimeError(
            "Trial Review count differs from executed Trial count"
        )
    if len(result.artifact_refs) != expected_count:
        raise RuntimeError(
            "Trial Reviewer artifact count differs from executed Trial count"
        )
    for value in result.artifact_refs.values():
        if not Path(value).is_file():
            raise FileNotFoundError(
                f"Trial Reviewer artifact is missing: {value}"
            )


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    """Run one Intervention batch and print Trial Reviewer artifacts."""

    args = parse_args(argv)
    outcome, manifest, review_result = asyncio.run(
        run_intervention_trial_reviews(args)
    )
    if review_result is None:
        print(
            "debug fragment ready: "
            "completed=intervention_workers, "
            "stop_before=trial_reviewers, "
            f"controller_tokens={outcome.total_tokens}"
        )
        print(f"intervention_stage={manifest}")
        print(f"run_dir={args.run_dir.resolve()}")
        return
    print(
        "debug fragment ready: "
        "completed=intervention_workers+trial_reviewers, "
        "stop_before=evidence_reviewer, "
        f"controller_tokens={outcome.total_tokens}, "
        "pending_trial_review_tokens="
        f"{review_result.usage.get('total_tokens', 0)}"
    )
    print(f"trial_review_stage={manifest}")
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
