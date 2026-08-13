"""按 Generation 投影角色流程与路由预算。"""

from __future__ import annotations

from typing import Any

from .models import ObservedEvent, ObservedWorkItem


FLOW_NODES = (
    {
        "kind": "evaluate_incumbent",
        "label": "Incumbent Evaluation",
        "work_kinds": ("evaluate_incumbent",),
    },
    {
        "kind": "analyze_failure",
        "label": "Failure Analyst",
        "work_kinds": ("analyze_failure",),
    },
    {
        "kind": "research_hypothesis",
        "label": "Hypothesis Researcher",
        "work_kinds": ("research_hypothesis",),
    },
    {
        "kind": "execute_trial",
        "label": "Intervention Executor",
        "work_kinds": ("select_trial", "execute_trial"),
    },
    {
        "kind": "trial_reviewer",
        "label": "Trial Reviewer",
        "work_kinds": ("review_evidence",),
    },
    {
        "kind": "review_evidence",
        "label": "Evidence Review",
        "work_kinds": ("review_evidence",),
    },
    {
        "kind": "distill_mechanism",
        "label": "Mechanism Distiller",
        "work_kinds": ("distill_mechanism",),
    },
    {
        "kind": "compile_candidate",
        "label": "Mechanism Compiler",
        "work_kinds": ("compile_candidate",),
    },
    {
        "kind": "stage_candidate",
        "label": "Candidate Validation",
        "work_kinds": ("stage_candidate",),
    },
    {
        "kind": "verify_conformance",
        "label": "Conformance Review",
        "work_kinds": ("verify_conformance",),
    },
    {
        "kind": "evaluate_candidate",
        "label": "Candidate Evaluation",
        "work_kinds": ("evaluate_candidate",),
    },
    {
        "kind": "review_candidate",
        "label": "Candidate Review",
        "work_kinds": ("review_candidate", "reject_candidate"),
    },
    {
        "kind": "promote_candidate",
        "label": "Promotion",
        "work_kinds": ("promote_candidate",),
        "event_types": ("version_advanced",),
    },
)

NODE_FILTERS = {str(node["kind"]): node for node in FLOW_NODES}

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
            "kind": node["kind"],
            "label": node["label"],
            "work_kinds": list(node["work_kinds"]),
            "event_types": list(node.get("event_types", ())),
            "status": _node_status(by_kind.get(str(node["kind"]), [])),
            "count": len(by_kind.get(str(node["kind"]), [])),
            "budget": budgets.get(str(node["kind"])),
        }
        for node in FLOW_NODES
    ]


def node_work_kinds(node_kind: str) -> frozenset[str]:
    """返回一个可视化节点覆盖的 WorkKind 集合。"""

    node = NODE_FILTERS.get(node_kind)
    if node is None:
        raise ValueError(f"unknown flow node: {node_kind}")
    return frozenset(str(kind) for kind in node["work_kinds"])


def filter_node_events(
    events: list[ObservedEvent],
    works: list[ObservedWorkItem],
    node_kind: str,
    generation: int | None,
) -> list[ObservedEvent]:
    """筛选节点 WorkItem 生命周期及直接归属的 Control Event。"""

    node = NODE_FILTERS.get(node_kind)
    if node is None:
        raise ValueError(f"unknown flow node: {node_kind}")
    work_kinds = node_work_kinds(node_kind)
    work_ids = {
        work.work_id
        for work in works
        if (generation is None or work.generation == generation)
        and work.kind in work_kinds
    }
    event_types = frozenset(
        str(event_type) for event_type in node.get("event_types", ())
    )
    return [
        event
        for event in events
        if _event_matches_node(
            event,
            work_ids,
            event_types,
            generation,
        )
    ]


def _event_matches_node(
    event: ObservedEvent,
    work_ids: set[str],
    event_types: frozenset[str],
    generation: int | None,
) -> bool:
    work_id = _control_event_work_id(event)
    if work_id is not None:
        return work_id in work_ids
    return (
        event.event_type in event_types
        and (
            generation is None
            or event.payload.get("generation") == generation
        )
    )


def _control_event_work_id(event: ObservedEvent) -> str | None:
    if event.event_type == "work_scheduled":
        work = event.payload.get("work")
        if isinstance(work, dict) and isinstance(work.get("work_id"), str):
            return work["work_id"]
        return None
    work_id = event.payload.get("work_id")
    return work_id if isinstance(work_id, str) else None


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
