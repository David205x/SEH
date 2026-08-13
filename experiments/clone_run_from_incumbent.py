"""Create a fresh Evolution Run from one completed Incumbent Evaluation."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.journal import (
    ControlArtifactStore,
    ControlJournal,
)
from search_harness.evolution.control.transitions import (
    initial_work,
    transition_completed,
)
from search_harness.evolution.experience import file_digest
from search_harness.evolution.versioning import TemplateVersionStore


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_run",
        type=Path,
        help="Existing Evolution Run with a completed Incumbent Evaluation.",
    )
    parser.add_argument(
        "new_run",
        type=Path,
        help="New Evolution Run directory; it must not already exist.",
    )
    return parser.parse_args()


def clone_run_from_incumbent(source_run: Path, new_run: Path) -> Path:
    """Clone baseline evidence and schedule a fresh Failure Analyst work item."""

    source = source_run.resolve()
    destination = new_run.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source Evolution Run does not exist: {source}")
    if destination.exists():
        raise FileExistsError(f"New Evolution Run already exists: {destination}")
    if source == destination or source in destination.parents:
        raise ValueError("New Evolution Run must not be inside the source run")

    run_payload = _read_object(source / "run.json")
    _validate_source_run(source, run_payload)
    source_journal = ControlJournal(source / "events.jsonl")
    source_events = source_journal.read()
    source_state = project_events(source_events)
    evaluation_work = _completed_incumbent_work(source_state)
    if evaluation_work.payload.get("version_id") != run_payload["initial_version"]:
        raise ValueError(
            "Completed Incumbent Evaluation does not match initial_version"
        )
    source_artifacts = ControlArtifactStore(source / "artifacts")
    source_effect = source_artifacts.load_effect(evaluation_work.work_id)

    experience_file = source / "experience_set.jsonl"
    _validate_experience_set(experience_file, run_payload)
    source_work_dir = source_artifacts.work_dir(evaluation_work.work_id)
    relative_refs = _relative_evaluation_refs(source_effect, source_work_dir)

    run_id = uuid4().hex
    new_evaluation = initial_work(
        run_id=run_id,
        version_id=evaluation_work.payload["version_id"],
    )
    staging = destination.with_name(
        f".{destination.name}.{uuid4().hex}.staging"
    )
    if staging.exists():
        raise FileExistsError(f"Staging directory already exists: {staging}")

    try:
        _materialize_clone(
            source=source,
            destination=destination,
            staging=staging,
            run_payload=run_payload,
            run_id=run_id,
            source_work=evaluation_work,
            new_work=new_evaluation,
            source_effect=source_effect,
            relative_refs=relative_refs,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination


def _materialize_clone(
    *,
    source: Path,
    destination: Path,
    staging: Path,
    run_payload: dict[str, Any],
    run_id: str,
    source_work: WorkItem,
    new_work: WorkItem,
    source_effect: EffectResult,
    relative_refs: dict[str, Path],
) -> None:
    staging.mkdir(parents=True)
    source_store = TemplateVersionStore(
        Path(_required_string(run_payload, "version_store"))
    )
    new_store_id = (
        f"{source_store.version_store_id}-clone-{run_id[:12]}"
    )
    _clone_version_store(
        source_store=source_store,
        staged_store=staging / "version_store",
        new_store_id=new_store_id,
        source_run=source,
    )
    copied_experience = staging / "experience_set.jsonl"
    shutil.copy2(source / "experience_set.jsonl", copied_experience)

    final_work_dir = destination / "artifacts" / new_work.work_id
    staged_work_dir = staging / "artifacts" / new_work.work_id
    shutil.copytree(
        source / "artifacts" / source_work.work_id,
        staged_work_dir,
    )
    reused_effect = EffectResult(
        outcome=dict(source_effect.outcome),
        artifact_refs={
            name: str((final_work_dir / relative_path).resolve())
            for name, relative_path in relative_refs.items()
        },
        usage=dict(source_effect.usage),
    )
    _write_object(
        staged_work_dir / "effect.json",
        reused_effect.to_dict(),
    )

    cloned_payload = _cloned_run_payload(
        source=source,
        destination=destination,
        source_payload=run_payload,
        run_id=run_id,
        source_work=source_work,
        new_work=new_work,
        source_effect=source_effect,
        new_store_id=new_store_id,
    )
    _write_object(staging / "run.json", cloned_payload)

    control_config = EvolutionControlConfig(
        **_required_object(cloned_payload, "control_config")
    )
    plan = transition_completed(
        item=new_work,
        result=reused_effect,
        config=control_config,
    )
    if len(plan.next_items) != 1:
        raise RuntimeError("Incumbent transition did not schedule one next work")
    next_work = plan.next_items[0]
    if next_work.kind is not WorkKind.ANALYZE_FAILURE:
        raise RuntimeError("Incumbent transition did not route to Failure Analyst")

    journal = ControlJournal(staging / "events.jsonl")
    journal.append_many(
        [
            (
                "run_started",
                {
                    "run_id": run_id,
                    "initial_version": new_work.payload["version_id"],
                },
            ),
            ("work_scheduled", {"work": new_work.to_dict()}),
            ("work_started", {"work_id": new_work.work_id}),
            (
                "work_completed",
                {
                    "work_id": new_work.work_id,
                    "result_ref": str(
                        (final_work_dir / "effect.json").resolve()
                    ),
                    "total_tokens": 0,
                    "reused_from": {
                        "run": str(source),
                        "work_id": source_work.work_id,
                    },
                },
            ),
            ("work_scheduled", {"work": next_work.to_dict()}),
            ("work_transitioned", {"work_id": new_work.work_id}),
        ]
    )


def _cloned_run_payload(
    *,
    source: Path,
    destination: Path,
    source_payload: dict[str, Any],
    run_id: str,
    source_work: WorkItem,
    new_work: WorkItem,
    source_effect: EffectResult,
    new_store_id: str,
) -> dict[str, Any]:
    payload = dict(source_payload)
    effects_config = _required_object(payload, "effects_config")
    effects_config["experience_file"] = str(
        (destination / "experience_set.jsonl").resolve()
    )
    experience_set = _required_object(payload, "experience_set")
    experience_set["path"] = str(
        (destination / "experience_set.jsonl").resolve()
    )
    payload.update(
        {
            "run_id": run_id,
            "version_store": str((destination / "version_store").resolve()),
            "version_store_id": new_store_id,
            "effects_config": effects_config,
            "experience_set": experience_set,
            "incumbent_evaluation_reuse": {
                "source_run": str(source),
                "source_work_id": source_work.work_id,
                "new_work_id": new_work.work_id,
                "source_usage": dict(source_effect.usage),
                "charged_tokens": 0,
                "source_version_store": _required_string(
                    source_payload,
                    "version_store",
                ),
                "new_version_store": str(
                    (destination / "version_store").resolve()
                ),
                "new_version_store_id": new_store_id,
            },
        }
    )
    return payload


def _clone_version_store(
    *,
    source_store: TemplateVersionStore,
    staged_store: Path,
    new_store_id: str,
    source_run: Path,
) -> None:
    """Copy accepted history while dropping unaccepted Candidate Attempts."""

    if not (source_store.root / ".git").is_dir():
        raise FileNotFoundError(
            f"Source Version Store Git repository is missing: {source_store.root}"
        )
    shutil.copytree(
        source_store.root,
        staged_store,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        copy_function=shutil.copyfile,
    )

    metadata_path = staged_store / "version_store.json"
    metadata = _read_object(metadata_path)
    metadata["version_store_id"] = new_store_id
    metadata["cloned_from"] = {
        "source_run": str(source_run),
        "source_version_store": str(source_store.root),
        "source_version_store_id": source_store.version_store_id,
    }
    _write_object(metadata_path, metadata)

    accepted_attempt_ids = {
        record.candidate_attempt_id
        for record in source_store.list_versions()
        if record.candidate_attempt_id is not None
    }
    metadata_dir = staged_store / ".harness-store"
    for name in ("candidate_attempts.jsonl", "iterations.jsonl"):
        _retain_candidate_attempts(
            metadata_dir / name,
            accepted_attempt_ids=accepted_attempt_ids,
        )

    cloned_store = TemplateVersionStore(staged_store)
    source_versions = source_store.list_versions()
    cloned_versions = cloned_store.list_versions()
    source_identity = [
        (record.version_id, record.digest, record.git_commit)
        for record in source_versions
    ]
    cloned_identity = [
        (record.version_id, record.digest, record.git_commit)
        for record in cloned_versions
    ]
    if cloned_store.version_store_id != new_store_id:
        raise RuntimeError("Cloned Version Store identity was not updated")
    if cloned_identity != source_identity:
        raise RuntimeError("Cloned Version Store changed accepted history")
    for record in cloned_versions:
        cloned_store.resolve(record.version_id)


def _retain_candidate_attempts(
    path: Path,
    *,
    accepted_attempt_ids: set[str],
) -> None:
    if not path.exists():
        return
    retained: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid Candidate Attempt journal at {path}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise TypeError(
                f"Candidate Attempt event must be an object: {path}:{line_number}"
            )
        attempt_id = value.get("candidate_attempt_id", value.get("iteration_id"))
        if attempt_id in accepted_attempt_ids:
            retained.append(line)
    if retained:
        path.write_text("\n".join(retained) + "\n", encoding="utf-8")
    else:
        path.unlink()


def _completed_incumbent_work(state: ControlState) -> WorkItem:
    matches = [
        record.item
        for record in state.works.values()
        if record.item.kind is WorkKind.EVALUATE_INCUMBENT
        and record.item.payload.get("generation") == 1
        and record.status == "completed"
    ]
    if len(matches) != 1:
        raise ValueError(
            "Source run must contain exactly one completed generation-1 "
            "Incumbent Evaluation"
        )
    return matches[0]


def _relative_evaluation_refs(
    effect: EffectResult,
    work_dir: Path,
) -> dict[str, Path]:
    required = {"rollout_file", "report_dir"}
    if set(effect.artifact_refs) != required:
        raise ValueError(
            "Incumbent Evaluation must expose exactly rollout_file and report_dir"
        )
    relative: dict[str, Path] = {}
    for name, raw_path in effect.artifact_refs.items():
        path = Path(raw_path).resolve()
        try:
            relative_path = path.relative_to(work_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Evaluation artifact is outside its work directory: {path}"
            ) from exc
        if not path.exists():
            raise FileNotFoundError(f"Evaluation artifact does not exist: {path}")
        relative[name] = relative_path
    return relative


def _validate_source_run(source: Path, payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 2:
        raise ValueError("Only Evolution Run schema v2 is supported")
    initial_version = _required_string(payload, "initial_version")
    version_store = TemplateVersionStore(
        Path(_required_string(payload, "version_store"))
    )
    expected_store_id = _required_string(payload, "version_store_id")
    if version_store.version_store_id != expected_store_id:
        raise ValueError("Source run Version Store identity does not match")
    versions = version_store.list_versions()
    if not versions or versions[-1].version_id != initial_version:
        raise ValueError(
            "Source baseline is not the latest Accepted Template Version; "
            "a cloned run could not stage comparable candidates"
        )


def _validate_experience_set(
    experience_file: Path,
    payload: dict[str, Any],
) -> None:
    if not experience_file.is_file():
        raise FileNotFoundError(
            f"Source Evolution Set does not exist: {experience_file}"
        )
    experience = _required_object(payload, "experience_set")
    expected_digest = _required_string(experience, "digest")
    actual_digest = file_digest(experience_file)
    if actual_digest != expected_digest:
        raise ValueError(
            "Source Evolution Set digest does not match run.json: "
            f"{actual_digest} != {expected_digest}"
        )


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


def main() -> None:
    args = _parse_args()
    result = clone_run_from_incumbent(args.source_run, args.new_run)
    print(f"Evolution Run created: {result}")
    print("Next work: analyze_failure")


if __name__ == "__main__":
    main()
