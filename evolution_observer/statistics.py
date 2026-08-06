"""从 Journal 与已记录 Effect 中投影首页实验统计。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ObservedEvent, ObservedWorkItem


EVALUATION_KINDS = {"evaluate_incumbent", "evaluate_candidate"}
RESEARCH_KINDS = {
    "analyze_failure",
    "research_hypothesis",
    "select_trial",
    "execute_trial",
    "review_evidence",
    "distill_mechanism",
}
CANDIDATE_KINDS = {
    "compile_candidate",
    "stage_candidate",
    "verify_conformance",
    "review_candidate",
    "promote_candidate",
    "reject_candidate",
}
ROLE_LABELS = {
    "evaluate_incumbent": "Incumbent Evaluation",
    "analyze_failure": "Failure Analyst",
    "research_hypothesis": "Hypothesis Researcher",
    "execute_trial": "Intervention Worker",
    "review_evidence": "Evidence / Trial Review",
    "distill_mechanism": "Mechanism Distiller",
    "compile_candidate": "Compiler",
    "verify_conformance": "Conformance Reviewer",
    "review_candidate": "Candidate Reviewer",
}
ROLE_ID_LABELS = {
    "failure_analyst": "Failure Analyst",
    "hypothesis_researcher": "Hypothesis Researcher",
    "intervention_worker": "Intervention Worker",
    "trial_reviewer": "Trial Reviewer",
    "evidence_reviewer": "Evidence Reviewer",
    "mechanism_distiller": "Mechanism Distiller",
    "compiler": "Compiler",
    "conformance_reviewer": "Conformance Reviewer",
    "candidate_reviewer": "Candidate Reviewer",
}


def project_run_statistics(
    run_dir: Path,
    events: list[ObservedEvent],
    works: list[ObservedWorkItem],
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """返回只使用明确记录字段的统计；不可获取的来源保持 ``None``。"""

    total_tokens = sum(work.total_tokens or 0 for work in works)
    teacher_role_tokens = sum(
        work.total_tokens or 0
        for work in works
        if work.category == "teacher_role"
    )
    evaluation_usage = _evaluation_usage(run_dir, works)
    metadata = run_metadata or {}
    effects_config = metadata.get("effects_config")
    fallback_turn_limit = (
        effects_config.get("teacher_max_turns")
        if isinstance(effects_config, dict)
        else None
    )
    role_usage = _teacher_role_usage(
        run_dir,
        works,
        fallback_turn_limit=(
            fallback_turn_limit
            if isinstance(fallback_turn_limit, int)
            else None
        ),
    )
    elapsed_seconds = _elapsed_seconds(events)
    stage_seconds = _stage_seconds(works)
    stage_total = sum(stage_seconds.values())
    generation_seconds = _generation_seconds(works)
    return {
        "work_items": len(works),
        "completed_work_items": sum(work.status == "completed" for work in works),
        "failed_work_items": sum(work.status == "failed" for work in works),
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed_seconds,
        "current_generation_seconds": generation_seconds["current"],
        "average_generation_seconds": generation_seconds["average"],
        "recorded_model_calls": (
            evaluation_usage["student_calls"] + role_usage["requests"]
        ),
        "recorded_cached_tokens": role_usage["cached_tokens"],
        "cache_scope": "Teacher Role artifacts",
        "model_calls": {
            "student": evaluation_usage["student_calls"],
            "teacher_role": role_usage["requests"],
            "teacher_judge": None,
            "hook_model": None,
        },
        "token_sources": {
            "student": evaluation_usage["student_tokens"],
            "teacher_role": teacher_role_tokens,
            "teacher_judge": None,
            "hook_model": evaluation_usage["hook_tokens"],
            "unclassified": max(
                0,
                total_tokens
                - teacher_role_tokens
                - evaluation_usage["student_tokens"]
                - evaluation_usage["hook_tokens"],
            ),
        },
        "stage_time": {
            name: {
                "seconds": seconds,
                "share": seconds / stage_total if stage_total else 0.0,
            }
            for name, seconds in stage_seconds.items()
        },
        "role_breakdown": _role_breakdown(
            works,
            role_usage["by_kind"],
        ),
        "role_time_breakdown": _role_breakdown(
            works,
            role_usage["by_kind"],
            include_incumbent=True,
        ),
        "role_turns": _role_turn_distribution(role_usage["turn_sessions"]),
        "evolution_metrics": _evolution_metrics(run_dir, works),
    }


def _evaluation_usage(
    run_dir: Path,
    works: list[ObservedWorkItem],
) -> dict[str, int]:
    student_tokens = 0
    hook_tokens = 0
    student_calls = 0
    for work in works:
        if work.kind not in EVALUATION_KINDS or work.result_ref is None:
            continue
        effect = _read_optional_effect(run_dir, work.result_ref)
        if effect is None:
            continue
        outcome = effect.get("outcome")
        metrics = outcome.get("metrics") if isinstance(outcome, dict) else None
        if not isinstance(metrics, dict):
            continue
        tokens = metrics.get("tokens")
        if isinstance(tokens, dict):
            student_tokens += _integer(tokens.get("student_total_tokens"))
            hook_tokens += _integer(tokens.get("hook_total_tokens"))
        execution = metrics.get("execution")
        if isinstance(execution, dict):
            records = _number(execution.get("record_count"))
            mean_calls = _number(execution.get("mean_model_calls"))
            student_calls += round(records * mean_calls)
    return {
        "student_tokens": student_tokens,
        "hook_tokens": hook_tokens,
        "student_calls": student_calls,
    }


def _read_optional_effect(run_dir: Path, reference: str) -> dict[str, Any] | None:
    return _read_optional_json(_reference_path(run_dir, reference))


def _evolution_metrics(
    run_dir: Path,
    works: list[ObservedWorkItem],
) -> list[dict[str, object]]:
    """按 Generation 投影最后一个可用 Candidate 或 Incumbent 指标。"""

    by_generation: dict[int, list[ObservedWorkItem]] = {}
    for work in works:
        if (
            work.kind not in EVALUATION_KINDS
            or work.status != "completed"
            or work.generation is None
            or work.result_ref is None
        ):
            continue
        by_generation.setdefault(work.generation, []).append(work)

    points: list[dict[str, object]] = []
    for generation, evaluation_works in sorted(by_generation.items()):
        selected = _select_generation_evaluation(evaluation_works)
        point = _evaluation_metric_point(run_dir, selected)
        if point is not None:
            points.append(point)
    return points


def _select_generation_evaluation(
    works: list[ObservedWorkItem],
) -> ObservedWorkItem:
    candidates = [work for work in works if work.kind == "evaluate_candidate"]
    selectable = candidates or works
    return max(
        selectable,
        key=lambda work: work.events[-1].sequence if work.events else -1,
    )


def _evaluation_metric_point(
    run_dir: Path,
    work: ObservedWorkItem,
) -> dict[str, object] | None:
    assert work.result_ref is not None
    effect_path = _reference_path(run_dir, work.result_ref)
    effect = _read_optional_json(effect_path)
    if effect is None:
        return None
    outcome = effect.get("outcome")
    metrics = outcome.get("metrics") if isinstance(outcome, dict) else None
    if not isinstance(metrics, dict):
        return None

    answers = metrics.get("answers")
    execution = metrics.get("execution")
    scored_count = _optional_number(
        answers.get("scored_count") if isinstance(answers, dict) else None
    )
    static_pass_count = _optional_number(
        answers.get("static_pass_count") if isinstance(answers, dict) else None
    )
    token_values = _student_token_values(
        run_dir,
        effect_path,
        effect,
    )
    return {
        "generation": work.generation,
        "source": (
            "candidate"
            if work.kind == "evaluate_candidate"
            else "incumbent"
        ),
        "work_id": work.work_id,
        "mean_turns": _optional_number(
            execution.get("mean_steps")
            if isinstance(execution, dict)
            else None
        ),
        "token_minimum": min(token_values) if token_values else None,
        "token_mean": (
            sum(token_values) / len(token_values)
            if token_values
            else None
        ),
        "token_maximum": max(token_values) if token_values else None,
        "matching_accuracy": (
            static_pass_count / scored_count
            if static_pass_count is not None and scored_count
            else None
        ),
        "teacher_judge_accuracy": _optional_number(
            answers.get("accuracy") if isinstance(answers, dict) else None
        ),
        "stability": _optional_number(
            answers.get("mean_answer_consistency")
            if isinstance(answers, dict)
            else None
        ),
    }


def _student_token_values(
    run_dir: Path,
    effect_path: Path,
    effect: dict[str, Any],
) -> list[float]:
    artifact_refs = effect.get("artifact_refs")
    report_dir_ref = (
        artifact_refs.get("report_dir")
        if isinstance(artifact_refs, dict)
        else None
    )
    report_dir = (
        _reference_path(run_dir, report_dir_ref, effect_path.parent)
        if isinstance(report_dir_ref, str)
        else effect_path.parent / "report"
    )
    path = report_dir / "per_rollout.jsonl"
    if not path.is_file():
        local_path = effect_path.parent / "report" / "per_rollout.jsonl"
        path = local_path if local_path.is_file() else path
    values: list[float] = []
    for record in _read_optional_jsonl(path):
        execution = record.get("execution")
        tokens = execution.get("tokens") if isinstance(execution, dict) else None
        value = _optional_number(
            tokens.get("student_total_tokens")
            if isinstance(tokens, dict)
            else None
        )
        if value is not None:
            values.append(value)
    return values


def _teacher_role_usage(
    run_dir: Path,
    works: list[ObservedWorkItem],
    *,
    fallback_turn_limit: int | None,
) -> dict[str, object]:
    requests = 0
    cached_tokens = 0
    by_kind: dict[str, dict[str, int]] = {}
    turn_sessions: list[dict[str, object]] = []
    seen_artifacts: set[Path] = set()
    for work in works:
        if work.category != "teacher_role" or work.result_ref is None:
            continue
        effect_path = _reference_path(run_dir, work.result_ref)
        effect = _read_optional_json(effect_path)
        if effect is None:
            continue
        refs = effect.get("artifact_refs")
        if not isinstance(refs, dict):
            continue
        for reference in refs.values():
            if not isinstance(reference, str):
                continue
            artifact_path = _reference_path(run_dir, reference, effect_path.parent)
            resolved_path = artifact_path.resolve()
            if resolved_path in seen_artifacts:
                continue
            seen_artifacts.add(resolved_path)
            artifact = _read_optional_json(artifact_path)
            if artifact is None:
                continue
            usage = artifact.get("usage")
            if not isinstance(usage, dict):
                continue
            request_count = _integer(usage.get("requests"))
            requests += request_count
            role_usage = by_kind.setdefault(
                work.kind,
                {"calls": 0, "cached_tokens": 0},
            )
            role_usage["calls"] += request_count
            role = artifact.get("role")
            role_id = role.get("id") if isinstance(role, dict) else None
            if isinstance(role_id, str) and request_count > 0:
                role_budget = artifact.get("role_budget")
                recorded_limit = (
                    role_budget.get("max_turns")
                    if isinstance(role_budget, dict)
                    else None
                )
                turn_sessions.append(
                    {
                        "role_id": role_id,
                        "label": ROLE_ID_LABELS.get(role_id, role_id),
                        "generation": work.generation,
                        "turns": request_count,
                        "limit": (
                            recorded_limit
                            if isinstance(recorded_limit, int)
                            else fallback_turn_limit
                        ),
                    }
                )
            calls = usage.get("calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if isinstance(call, dict):
                    cache_hit = _integer(call.get("prompt_cache_hit_tokens"))
                    cached_tokens += cache_hit
                    role_usage["cached_tokens"] += cache_hit
    return {
        "requests": requests,
        "cached_tokens": cached_tokens,
        "by_kind": by_kind,
        "turn_sessions": turn_sessions,
    }


def _role_turn_distribution(sessions: object) -> dict[str, object]:
    recorded_sessions = (
        sessions if isinstance(sessions, list) else []
    )
    generations = sorted(
        {
            session["generation"]
            for session in recorded_sessions
            if isinstance(session, dict)
            and isinstance(session.get("generation"), int)
        }
    )
    return {
        "run": _turn_scope_rows(recorded_sessions),
        "by_generation": {
            str(generation): _turn_scope_rows(
                [
                    session
                    for session in recorded_sessions
                    if session.get("generation") == generation
                ]
            )
            for generation in generations
        },
    }


def _turn_scope_rows(
    sessions: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for session in sessions:
        role_id = session.get("role_id")
        if isinstance(role_id, str):
            grouped.setdefault(role_id, []).append(session)
    rows = []
    for role_id, role_sessions in grouped.items():
        values = sorted(
            int(session["turns"])
            for session in role_sessions
            if isinstance(session.get("turns"), int)
        )
        limits = sorted(
            {
                int(session["limit"])
                for session in role_sessions
                if isinstance(session.get("limit"), int)
            }
        )
        if not values:
            continue
        rows.append(
            {
                "role_id": role_id,
                "label": role_sessions[0]["label"],
                "sample_count": len(values),
                "minimum": values[0],
                "q1": _percentile(values, 0.25),
                "median": _percentile(values, 0.5),
                "mean": sum(values) / len(values),
                "q3": _percentile(values, 0.75),
                "maximum": values[-1],
                "turn_limit": limits[-1] if limits else None,
                "limit_values": limits,
            }
        )
    return sorted(rows, key=lambda row: str(row["label"]))


def _percentile(values: list[int], fraction: float) -> float:
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    return values[lower_index] + (
        values[upper_index] - values[lower_index]
    ) * weight


def _generation_seconds(
    works: list[ObservedWorkItem],
) -> dict[str, float | None]:
    boundaries: dict[int, list[datetime]] = {}
    for work in works:
        if work.generation is None or work.started_at_utc is None:
            continue
        times = boundaries.setdefault(work.generation, [])
        times.append(_parse_time(work.started_at_utc))
        if work.ended_at_utc is not None:
            times.append(_parse_time(work.ended_at_utc))
    durations = {
        generation: max(0.0, (max(times) - min(times)).total_seconds())
        for generation, times in boundaries.items()
        if len(times) >= 2
    }
    if not durations:
        return {"current": None, "average": None}
    current_generation = max(durations)
    return {
        "current": durations[current_generation],
        "average": sum(durations.values()) / len(durations),
    }


def _role_breakdown(
    works: list[ObservedWorkItem],
    recorded_usage: object,
    *,
    include_incumbent: bool = False,
) -> list[dict[str, object]]:
    usage_by_kind = (
        recorded_usage if isinstance(recorded_usage, dict) else {}
    )
    rows: dict[str, dict[str, Any]] = {}
    for work in works:
        is_incumbent = (
            include_incumbent and work.kind == "evaluate_incumbent"
        )
        if work.category != "teacher_role" and not is_incumbent:
            continue
        row = rows.setdefault(
            work.kind,
            {
                "kind": work.kind,
                "label": ROLE_LABELS.get(work.kind, work.kind),
                "seconds": 0.0,
                "work_count": 0,
                "tokens": 0,
                "calls": 0,
                "cached_tokens": 0,
            },
        )
        row["seconds"] += _work_duration(work)
        row["work_count"] += 1
        row["tokens"] += work.total_tokens or 0
    for kind, usage in usage_by_kind.items():
        if kind not in rows or not isinstance(usage, dict):
            continue
        rows[kind]["calls"] = _integer(usage.get("calls"))
        rows[kind]["cached_tokens"] = _integer(usage.get("cached_tokens"))
    total_seconds = sum(float(row["seconds"]) for row in rows.values())
    total_tokens = sum(int(row["tokens"]) for row in rows.values())
    for row in rows.values():
        seconds = float(row["seconds"])
        tokens = int(row["tokens"])
        cached_tokens = int(row["cached_tokens"])
        row["time_share"] = seconds / total_seconds if total_seconds else 0.0
        row["token_share"] = tokens / total_tokens if total_tokens else 0.0
        row["cache_share"] = cached_tokens / tokens if tokens else None
    return sorted(rows.values(), key=lambda row: int(row["tokens"]), reverse=True)


def _reference_path(
    run_dir: Path,
    reference: str,
    base_dir: Path | None = None,
) -> Path:
    path = Path(reference)
    if path.is_absolute():
        return path
    run_relative = run_dir / path
    if run_relative.is_file() or base_dir is None:
        return run_relative
    return base_dir / path


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _read_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _elapsed_seconds(events: list[ObservedEvent]) -> float | None:
    if not events:
        return None
    started = _parse_time(events[0].created_at_utc)
    ended = _parse_time(events[-1].created_at_utc)
    return max(0.0, (ended - started).total_seconds())


def _stage_seconds(works: list[ObservedWorkItem]) -> dict[str, float]:
    totals = {"evaluation": 0.0, "research": 0.0, "candidate": 0.0}
    for work in works:
        if work.started_at_utc is None or work.ended_at_utc is None:
            continue
        duration = _work_duration(work)
        if work.kind in EVALUATION_KINDS:
            totals["evaluation"] += duration
        elif work.kind in RESEARCH_KINDS:
            totals["research"] += duration
        elif work.kind in CANDIDATE_KINDS:
            totals["candidate"] += duration
    return totals


def _work_duration(work: ObservedWorkItem) -> float:
    if work.started_at_utc is None or work.ended_at_utc is None:
        return 0.0
    return max(
        0.0,
        (
            _parse_time(work.ended_at_utc)
            - _parse_time(work.started_at_utc)
        ).total_seconds(),
    )


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _integer(value: object) -> int:
    return value if isinstance(value, int) else 0


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
