"""Run queued Experience Draft side works and one Researcher revision."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    ControlOutcome,
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


_ALLOWED_WORK = frozenset(
    {
        WorkKind.SUMMARIZE_CAPABILITY,
        WorkKind.SUMMARIZE_DIRECTION,
        WorkKind.RESEARCH_HYPOTHESIS,
    }
)


@dataclass(frozen=True)
class _ResearcherRevisionRoute:
    logical_work_id: str
    review_work_id: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the Researcher revision fragment arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args(argv)


async def run_researcher_revision(
    args: argparse.Namespace,
) -> tuple[ControlOutcome, Path, tuple[WorkKind, ...]]:
    """Complete routed side works and resume Hypothesis Researcher once."""

    run_dir = args.run_dir.resolve()
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 3:
        raise ValueError("Researcher revision fragments require Run schema v3")
    route = _require_ready_route(run_dir)

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
    stop_before = frozenset(
        kind for kind in WorkKind if kind not in _ALLOWED_WORK
    )
    outcome = await controller.run(stop_before=stop_before)
    artifact, next_kinds = _require_completed_route(
        run_dir=run_dir,
        route=route,
    )
    return outcome, artifact, next_kinds


def _require_ready_route(run_dir: Path) -> _ResearcherRevisionRoute:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    queued = [record.item for record in state.queued]
    kinds = [item.kind for item in queued]
    expected = [
        WorkKind.SUMMARIZE_CAPABILITY,
        WorkKind.SUMMARIZE_DIRECTION,
        WorkKind.RESEARCH_HYPOTHESIS,
    ]
    if state.status == "running" and kinds == expected:
        researcher = queued[-1]
        _validate_revision_item(researcher)
        if researcher.parent_work_id is None:
            raise ValueError("Researcher revision lacks Evidence Review parent")
        return _ResearcherRevisionRoute(
            logical_work_id=researcher.logical_work_id,
            review_work_id=researcher.parent_work_id,
        )

    if state.status == "paused" and not queued:
        failed = next(
            (
                state.works[work_id]
                for work_id in reversed(state.work_order)
                if state.works[work_id].status == "failed"
                and state.works[work_id].item.kind
                is WorkKind.RESEARCH_HYPOTHESIS
            ),
            None,
        )
        if failed is not None:
            researcher = failed.item
            _validate_revision_item(researcher)
            root = researcher
            while root.parent_work_id is not None:
                parent = state.works.get(root.parent_work_id)
                if (
                    parent is None
                    or parent.item.logical_work_id
                    != researcher.logical_work_id
                ):
                    break
                root = parent.item
            if root.parent_work_id is None:
                raise ValueError(
                    "Researcher retry chain lacks Evidence Review parent"
                )
            return _ResearcherRevisionRoute(
                logical_work_id=researcher.logical_work_id,
                review_work_id=root.parent_work_id,
            )

    raise RuntimeError(
        "Run does not contain the expected Evidence revise route: "
        f"status={state.status}, queued={[item.value for item in kinds]}"
    )


def _validate_revision_item(researcher: WorkItem) -> None:
    if researcher.kind is not WorkKind.RESEARCH_HYPOTHESIS:
        raise RuntimeError(
            "Evidence revise route does not target Hypothesis Researcher"
        )
    continuation = researcher.payload.get("research_continuation")
    if not isinstance(continuation, dict):
        raise ValueError("Researcher revision lacks continuation feedback")
    if continuation.get("feedback_source") != "evidence_reviewer":
        raise ValueError("Researcher revision source is not Evidence Reviewer")
    feedback = continuation.get("feedback")
    if not isinstance(feedback, dict) or feedback.get("decision") != "revise":
        raise ValueError("Researcher continuation is not a revise decision")


def _require_completed_route(
    *,
    run_dir: Path,
    route: _ResearcherRevisionRoute,
) -> tuple[Path, tuple[WorkKind, ...]]:
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    completed = [
        record
        for record in state.works.values()
        if record.item.logical_work_id == route.logical_work_id
        and record.status == "completed"
    ]
    if len(completed) != 1:
        raise RuntimeError("Revised Researcher WorkItem did not complete")
    record = completed[0]
    for kind in (
        WorkKind.SUMMARIZE_CAPABILITY,
        WorkKind.SUMMARIZE_DIRECTION,
    ):
        side_records = [
            item
            for item in state.works.values()
            if item.item.kind is kind
            and item.item.parent_work_id == route.review_work_id
        ]
        if len(side_records) != 1 or side_records[0].status != "completed":
            raise RuntimeError(f"{kind.value} side work did not complete")
    effect = ControlArtifactStore(run_dir / "artifacts").load_effect(
        record.item.work_id
    )
    artifact = effect.artifact_refs.get("hypothesis_artifact")
    if artifact is None or not Path(artifact).is_file():
        raise FileNotFoundError(
            f"Revised Researcher artifact is missing: {artifact}"
        )
    return Path(artifact).resolve(), tuple(
        item.item.kind for item in state.queued
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
    """Run one Evidence-driven Researcher revision boundary."""

    args = parse_args(argv)
    outcome, artifact, next_kinds = asyncio.run(
        run_researcher_revision(args)
    )
    next_text = ",".join(kind.value for kind in next_kinds) or "none"
    print(
        "debug fragment ready: "
        "completed=experience_drafts+research_hypothesis_revision, "
        f"stop_before={next_text}, "
        f"tokens={outcome.total_tokens}"
    )
    print(f"hypothesis_artifact={artifact}")
    print(f"run_dir={args.run_dir.resolve()}")


if __name__ == "__main__":
    main()
