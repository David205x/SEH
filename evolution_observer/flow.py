"""按 Generation 投影角色流程与路由预算。"""

from __future__ import annotations

from typing import Any

from .models import ObservedWorkItem


FLOW_NODES = (
    ("evaluate_incumbent", "Incumbent Evaluation"),
    ("analyze_failure", "Failure Analyst"),
    ("research_hypothesis", "Hypothesis Researcher"),
    ("execute_trial", "Intervention Executor"),
    ("trial_reviewer", "Trial Reviewer"),
    ("review_evidence", "Evidence Review"),
    ("distill_mechanism", "Mechanism Distiller"),
    ("compile_candidate", "Mechanism Compiler"),
    ("stage_candidate", "Candidate Validation"),
    ("verify_conformance", "Conformance Review"),
    ("evaluate_candidate", "Candidate Evaluation"),
    ("review_candidate", "Candidate Review"),
    ("promote_candidate", "Promotion"),
)

ROUTE_BUDGETS = (
    (
        "research_hypothesis",
        "hypothesis_revisions",
        "Hypothesis revisions",
        "max_hypothesis_revisions",
    ),
    (
        "execute_trial",
        "trial_assignments",
        "Trial assignments",
        "max_trial_assignments",
    ),
    (
        "trial_reviewer",
        "successful_trials",
        "Successful trials",
        "max_trials_per_hypothesis",
    ),
    (
        "distill_mechanism",
        "mechanism_revisions",
        "Mechanism revisions",
        "max_mechanism_revisions",
    ),
    (
        "compile_candidate",
        "compiler_revisions",
        "Compiler revisions",
        "max_compiler_revisions",
    ),
    (
        "review_candidate",
        "candidate_revisions",
        "Candidate revisions",
        "max_candidate_revisions",
    ),
)


def project_generation_flows(
    works: list[ObservedWorkItem],
    run_metadata: dict[str, Any],
    run_status: str,
) -> list[dict[str, object]]:
    """将累计 WorkItem 拆分为互不叠加的 Generation flow。"""

    generation_numbers = sorted(
        {
            work.generation
            for work in works
            if work.generation is not None
        }
    )
    control_config = run_metadata.get("control_config")
    limits = control_config if isinstance(control_config, dict) else {}
    flows = []
    for generation in generation_numbers:
        generation_works = [
            work for work in works if work.generation == generation
        ]
        route_usage = _route_usage(generation_works)
        flows.append(
            {
                "generation": generation,
                "status": _generation_status(
                    generation,
                    generation_numbers,
                    generation_works,
                    run_status,
                ),
                "has_next_generation": generation < generation_numbers[-1],
                "flow": _flow_projection(
                    generation_works,
                    route_usage,
                    limits,
                ),
            }
        )
    return flows


def _flow_projection(
    works: list[ObservedWorkItem],
    route_usage: dict[str, int],
    limits: dict[str, Any],
) -> list[dict[str, object]]:
    by_kind: dict[str, list[ObservedWorkItem]] = {}
    for work in works:
        by_kind.setdefault(work.kind, []).append(work)
        if work.kind == "review_evidence":
            by_kind.setdefault("trial_reviewer", []).append(work)
    budgets = _budget_projection(route_usage, limits)
    return [
        {
            "kind": kind,
            "label": label,
            "status": _node_status(by_kind.get(kind, [])),
            "count": len(by_kind.get(kind, [])),
            "budget": budgets.get(kind),
        }
        for kind, label in FLOW_NODES
    ]


def _budget_projection(
    route_usage: dict[str, int],
    limits: dict[str, Any],
) -> dict[str, dict[str, object]]:
    budgets = {}
    for node_kind, usage_key, label, limit_key in ROUTE_BUDGETS:
        limit = limits.get(limit_key)
        if not isinstance(limit, int) or limit <= 0:
            continue
        used = route_usage[usage_key]
        budgets[node_kind] = {
            "key": limit_key,
            "label": label,
            "used": used,
            "limit": limit,
            "share": min(used / limit, 1.0),
            "exhausted": used >= limit,
        }
    return budgets


def _route_usage(works: list[ObservedWorkItem]) -> dict[str, int]:
    work_by_id = {work.work_id: work for work in works}

    def parent_kind(work: ObservedWorkItem) -> str | None:
        parent = work_by_id.get(work.parent_work_id or "")
        return parent.kind if parent is not None else None

    return {
        "hypothesis_revisions": sum(
            work.kind == "research_hypothesis"
            and parent_kind(work) in {"execute_trial", "review_evidence"}
            for work in works
        ),
        "trial_assignments": sum(
            work.kind == "execute_trial" for work in works
        ),
        "successful_trials": sum(
            work.kind == "review_evidence" for work in works
        ),
        "mechanism_revisions": sum(
            work.kind == "distill_mechanism"
            and parent_kind(work) == "compile_candidate"
            for work in works
        ),
        "compiler_revisions": sum(
            work.kind == "compile_candidate"
            and parent_kind(work) == "stage_candidate"
            for work in works
        ),
        "candidate_revisions": sum(
            parent_kind(work) == "reject_candidate" for work in works
        ),
    }


def _generation_status(
    generation: int,
    generations: list[int],
    works: list[ObservedWorkItem],
    run_status: str,
) -> str:
    if any(
        work.kind == "promote_candidate" and work.status == "completed"
        for work in works
    ):
        return "accepted"
    if generation == generations[-1] and run_status in {
        "paused",
        "failed",
        "running",
    }:
        return run_status
    if any(work.status == "running" for work in works):
        return "running"
    if any(work.status == "failed" for work in works):
        return "failed"
    return "incomplete"


def _node_status(works: list[ObservedWorkItem]) -> str:
    if not works:
        return "not_reached"
    latest = max(
        works,
        key=lambda work: (
            work.events[-1].sequence if work.events else -1
        ),
    )
    return latest.status
