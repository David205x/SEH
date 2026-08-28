"""Check TASK-005 lifecycle identifiers and settled trajectory contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from search_harness.evolution.control.domain import (
    ControlEvent,
    SettlementClass,
    SettlementDraft,
    SettlementScope,
    TrajectorySettlement,
    WorkItem,
    materialize_settlement,
    project_events,
)
from search_harness.evolution.control.transitions import initial_work, retry_work


FORBIDDEN_SOURCE_TOKENS = (
    "optimizer_episode_id",
    "solution_attempt_id",
    "prior_solution_attempt_id",
    "iteration_id",
    "checkpoint_store_id",
    "legacy_candidate_attempt_file",
    "legacy_metadata_file",
    "legacy_path",
    "_migrate_legacy_attempt_names",
    "_stable_id",
    "_lineage_id",
    "_derived_id",
)
SCANNED_SOURCES = (
    "search_harness/evolution/identifiers.py",
    "search_harness/evolution/control/domain.py",
    "search_harness/evolution/control/transitions.py",
    "search_harness/evolution/control/controller.py",
    "search_harness/evolution/control/journal.py",
    "search_harness/evolution/control/cli.py",
    "search_harness/evolution/versioning/journal.py",
    "search_harness/evolution/versioning/store.py",
)


def run_check() -> dict[str, Any]:
    """Execute deterministic contract checks and return structured evidence."""

    first = initial_work(run_id="run_check", version_id="harness_v0001")
    retried = retry_work(first)
    _require(first.lineage.run_id == "run_check", "run_id is not lineage root")
    _require(first.lineage.generation == 1, "initial generation is not one")
    _require(first.lineage.generation_id == "run_check_g0001", "bad generation ID")
    _require(
        first.lineage.research_attempt_id == "run_check_g0001_r0001",
        "bad research attempt ID",
    )
    _require(first.logical_work_id in first.work_id, "work hierarchy is unreadable")
    _require(
        retried.logical_work_id == first.logical_work_id,
        "retry changed logical_work_id",
    )
    _require(retried.work_id != first.work_id, "retry did not change work_id")

    candidate_id = "candidate_attempt_check"
    candidate = materialize_settlement(
        draft=SettlementDraft(
            scope=SettlementScope.CANDIDATE_ATTEMPT,
            classification=SettlementClass.SETTLED_POSITIVE,
            terminal_code="candidate_promoted",
            verdict="accepted",
            candidate_attempt_id=candidate_id,
        ),
        item=first,
        event_sequence=3,
        result_ref="artifacts/effect.json",
        artifact_refs={"promotion_artifact": "artifacts/promotion.json"},
        error=None,
    )
    research = materialize_settlement(
        draft=SettlementDraft(
            scope=SettlementScope.RESEARCH_ATTEMPT,
            classification=SettlementClass.SETTLED_NEGATIVE,
            terminal_code="no_matching_trial_prefix",
            verdict="exhausted",
        ),
        item=first,
        event_sequence=3,
        result_ref="artifacts/effect.json",
        artifact_refs={},
        error=None,
    )
    failed = materialize_settlement(
        draft=SettlementDraft(
            scope=SettlementScope.WORK_ATTEMPT,
            classification=SettlementClass.INVALID_INDETERMINATE,
            terminal_code="work_attempt_failed",
            verdict="work_failed",
        ),
        item=retried,
        event_sequence=7,
        result_ref=None,
        artifact_refs={},
        error="RuntimeError: check failure",
    )
    _require(candidate.target_id == candidate_id, "candidate target is incorrect")
    _require(
        research.target_id == first.lineage.research_attempt_id,
        "research target is incorrect",
    )
    _require(failed.target_id == retried.work_id, "work target is incorrect")
    for settlement in (candidate, research, failed):
        _require(
            "scope_id" not in settlement.to_dict(),
            "settlement persisted redundant scope_id",
        )

    events = [
        _event(
            1,
            "run_started",
            {
                "run_id": first.lineage.run_id,
                "initial_version": "harness_v0001",
                "generation": first.lineage.generation,
                "generation_id": first.lineage.generation_id,
            },
        ),
        _event(2, "work_scheduled", {"work": first.to_dict()}),
        _event(
            3,
            "work_completed",
            {
                "work_id": first.work_id,
                "result_ref": "artifacts/effect.json",
                "total_tokens": 0,
            },
        ),
        _event(4, "trajectory_settled", {"settlement": candidate.to_dict()}),
        _event(5, "trajectory_settled", {"settlement": candidate.to_dict()}),
        _event(6, "work_scheduled", {"work": retried.to_dict()}),
        _event(
            7,
            "work_failed",
            {"work_id": retried.work_id, "error": "RuntimeError: check failure"},
        ),
        _event(8, "trajectory_settled", {"settlement": failed.to_dict()}),
    ]
    state = project_events(events)
    _require(len(state.settlements) == 2, "duplicate settlement was projected")

    conflicting = candidate.to_dict()
    conflicting_source = dict(conflicting["source"])
    conflicting_source["verdict"] = "conflicting"
    conflicting["source"] = conflicting_source
    conflict_event = _event(
        6,
        "trajectory_settled",
        {"settlement": TrajectorySettlement.from_dict(conflicting).to_dict()},
    )
    try:
        project_events([*events[:5], conflict_event])
    except ValueError:
        conflict_rejected = True
    else:
        conflict_rejected = False
    _require(conflict_rejected, "conflicting settlement replay was accepted")

    old_work = first.to_dict()
    old_work.pop("lineage")
    try:
        WorkItem.from_dict(old_work)
    except (TypeError, ValueError):
        old_contract_rejected = True
    else:
        old_contract_rejected = False
    _require(old_contract_rejected, "old WorkItem contract was accepted")

    scanned = _scan_sources()
    return {
        "status": "passed",
        "lineage": first.lineage.to_dict(),
        "logical_work_id": first.logical_work_id,
        "retry_work_id": retried.work_id,
        "settlements": [
            {
                "settlement_id": item.settlement_id,
                "scope": item.scope.value,
                "classification": item.classification.value,
                "target_id": item.target_id,
            }
            for item in (candidate, research, failed)
        ],
        "checks": {
            "replay_idempotent": True,
            "conflict_rejected": conflict_rejected,
            "old_contract_rejected": old_contract_rejected,
            "forbidden_source_tokens_absent": True,
        },
        "scanned_sources": scanned,
    }


def _scan_sources() -> list[str]:
    scanned: list[str] = []
    for relative in SCANNED_SOURCES:
        path = PROJECT_ROOT / relative
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_SOURCE_TOKENS:
            _require(token not in text, f"forbidden source token remains: {token}")
        if relative.endswith(("identifiers.py", "domain.py", "transitions.py")):
            _require("hashlib" not in text, f"hash ID dependency remains: {relative}")
        scanned.append(relative)
    return scanned


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, Any],
) -> ControlEvent:
    return ControlEvent(
        sequence=sequence,
        event_type=event_type,
        payload=payload,
        created_at="2026-08-21T00:00:00+00:00",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_check()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
