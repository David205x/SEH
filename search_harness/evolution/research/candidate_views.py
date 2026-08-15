"""Candidate Reviewer input and query-result views."""

from __future__ import annotations

import json
from typing import Any

from search_harness.evolution.research.resources.stores import (
    CandidateComparisonStore,
)


_TRACE_EVENT_TYPES = frozenset(
    {
        "parsed_output",
        "tool_call",
        "tool_result",
        "tool_error",
        "hook_model_output",
        "hook_applied",
        "hook_error",
        "final_answer_candidate",
        "final_deferred",
        "final_answer",
        "invalid_output",
        "invalid_output_feedback",
        "max_steps_reached",
    }
)
_INLINE_CHANGE_LIMIT = 1200
_PREVIEW_LIMIT = 500
_INLINE_DIFF_LIMIT = 16000
_MAX_CHANGED_CASES = 30


def render_candidate_review_input(
    value: dict[str, Any],
    resource_context: dict[str, Any],
) -> str:
    """Render one non-duplicated Candidate decision brief."""

    validation = _object(value.get("validation_summary"))
    conformance = _object(validation.get("mechanism_conformance"))
    incumbent = _object(validation.get("incumbent_metrics"))
    candidate = _object(validation.get("candidate_metrics"))
    candidate_context = _object(resource_context.get("candidate_review"))
    return "\n\n".join(
        (
            "# Candidate Review Brief",
            (
                "The exact Candidate revision has already passed static Candidate "
                "Validation. The compact Conformance result below is authoritative "
                "within its stated scope; neither fact proves task benefit."
            ),
            "## Mechanism\n" + _jsonl([value.get("mechanism")]),
            "## Conformance summary\n" + _jsonl([conformance]),
            "## Evaluation comparison\n"
            + _metric_comparison(incumbent, candidate),
            "## Candidate change landscape\n"
            + _table(
                ("field", "value"),
                (
                    (
                        "example_count",
                        _value(candidate_context.get("example_count")),
                    ),
                    (
                        "paired_change_counts",
                        _value(candidate_context.get("paired_change_counts")),
                    ),
                    (
                        "harness_diff_available",
                        _value(candidate_context.get("harness_diff_available")),
                    ),
                ),
            ),
            "## Implementation summary\n"
            + _value(value.get("implementation_summary")),
            "## Unresolved risk\n" + _value(value.get("unresolved_risk")),
            "## Historical experience\n"
            + _jsonl(value.get("historical_experience") or []),
            (
                "Begin with `list_candidate_changes` and inspect the Harness diff. "
                "Use paired cases to select decisive replicates, then inspect the "
                "required target, improved, and regressed behavior evidence before "
                "submitting one local recommendation."
            ),
        )
    )


def render_candidate_changes(
    store: CandidateComparisonStore,
    *,
    page: int,
    page_size: int,
    change: str,
) -> str:
    """Render a changed-first directory while retaining unchanged drill-down."""

    changes = _all_changes(store)
    counts = {
        label: sum(item.get("change") == label for item in changes)
        for label in ("improved", "regressed", "unchanged")
    }
    if change == "any":
        selected = [item for item in changes if item.get("change") != "unchanged"]
        selected.sort(
            key=lambda item: (
                -abs(float(item.get("success_rate_delta") or 0.0)),
                str(item.get("example_id")),
            )
        )
        if len(selected) > _MAX_CHANGED_CASES:
            selected = selected[:_MAX_CHANGED_CASES]
            clipped_note = (
                f" Only the {_MAX_CHANGED_CASES} largest absolute changes are "
                "shown; use a change filter for the complete category."
            )
        else:
            clipped_note = ""
        note = (
            "Default view lists all material changes before unchanged cases. "
            "Use `change=unchanged` only when a no-change boundary case is needed."
            + clipped_note
        )
    else:
        selected = [item for item in changes if item.get("change") == change]
        note = f"Filtered view: {change}."
    start = (page - 1) * page_size
    page_items = selected[start : start + page_size]
    total_pages = max(1, (len(selected) + page_size - 1) // page_size)
    rows = tuple(
        (
            _value(item.get("example_id")),
            _value(item.get("change")),
            _value(item.get("incumbent_success_rate")),
            _value(item.get("candidate_success_rate")),
            _value(item.get("success_rate_delta")),
            _value(item.get("question")),
        )
        for item in page_items
    )
    return "\n\n".join(
        (
            "# Candidate Change Landscape",
            _table(
                ("improved", "regressed", "unchanged"),
                ((str(counts["improved"]), str(counts["regressed"]), str(counts["unchanged"])),),
            ),
            (
                f"Page {page}/{total_pages}; selected={len(selected)}. {note}"
            ),
            _table(
                ("example_id", "change", "before", "after", "delta", "question"),
                rows,
            ),
        )
    )


def render_candidate_case(
    store: CandidateComparisonStore,
    example_id: str,
) -> str:
    """Render one case with paired replicate and execution deltas."""

    incumbent = store.incumbent_cases[example_id]
    candidate = store.candidate_cases[example_id]
    before_rate = _number(incumbent.get("success_rate"))
    after_rate = _number(candidate.get("success_rate"))
    before_replicates = _replicate_map(incumbent)
    after_replicates = _replicate_map(candidate)
    rows = []
    details = []
    for replicate_id in sorted(set(before_replicates) | set(after_replicates)):
        before = before_replicates.get(replicate_id, {})
        after = after_replicates.get(replicate_id, {})
        before_score = before.get("score")
        after_score = after.get("score")
        rows.append(
            (
                replicate_id,
                _value(before_score),
                _value(after_score),
                _score_change(before_score, after_score),
                _value(before.get("predicted_answer")),
                _value(after.get("predicted_answer")),
            )
        )
        details.append(
            {
                "replicate_id": replicate_id,
                "change": _score_change(before_score, after_score),
                "incumbent": _replicate_facts(before),
                "candidate": _replicate_facts(after),
                "execution_delta": _execution_delta(before, after),
                "candidate_hook_activity": _hook_activity(
                    store.candidate_rollouts.get(
                        (example_id, replicate_id),
                        {},
                    )
                ),
            }
        )
    return "\n\n".join(
        (
            "# Candidate Evaluation Case",
            _table(
                ("field", "incumbent", "candidate", "delta"),
                (
                    (
                        "success_rate",
                        _value(before_rate),
                        _value(after_rate),
                        _value(after_rate - before_rate),
                    ),
                    (
                        "stability",
                        _value(incumbent.get("stability")),
                        _value(candidate.get("stability")),
                        _change_label(before_rate, after_rate),
                    ),
                    (
                        "run_status",
                        _value(incumbent.get("run_status")),
                        _value(candidate.get("run_status")),
                        "n/a",
                    ),
                ),
            ),
            "Question:\n" + _exact_block("question", _value(incumbent.get("question"))),
            "## Replicate outcome map\n"
            + _table(
                (
                    "replicate",
                    "before score",
                    "after score",
                    "change",
                    "before answer",
                    "after answer",
                ),
                tuple(rows),
            ),
            (
                "## Paired replicate facts\n"
                "Execution keeps steps, tool calls, retriever errors, duplicate "
                "queries, and basic token facts; provider call counts and metadata "
                "are excluded. Candidate Hook activity is a compact index for "
                "selecting mixed or anomalous replicates; inspect the paired "
                "trajectory before attributing semantics.\n"
                + _jsonl(details)
            ),
        )
    )


def render_paired_candidate_trajectory(
    store: CandidateComparisonStore,
    *,
    example_id: str,
    replicate_id: str,
) -> str:
    """Render a self-contained paired behavior/effect trajectory."""

    key = (example_id, replicate_id)
    incumbent_record = store.incumbent_rollouts[key]
    candidate_record = store.candidate_rollouts[key]
    store.inspected_trajectories.add(key)
    before_case = _replicate_map(store.incumbent_cases[example_id]).get(
        replicate_id, {}
    )
    after_case = _replicate_map(store.candidate_cases[example_id]).get(
        replicate_id, {}
    )
    question = _object(incumbent_record.get("example")).get("question")
    if not question:
        question = _object(incumbent_record.get("run")).get("question")
    return "\n\n".join(
        (
            "# Paired Candidate Effect Trajectory",
            _table(
                ("field", "incumbent", "candidate", "change"),
                (
                    (
                        "score",
                        _value(before_case.get("score")),
                        _value(after_case.get("score")),
                        _score_change(before_case.get("score"), after_case.get("score")),
                    ),
                    (
                        "answer",
                        _value(before_case.get("predicted_answer")),
                        _value(after_case.get("predicted_answer")),
                        "changed"
                        if before_case.get("predicted_answer")
                        != after_case.get("predicted_answer")
                        else "unchanged",
                    ),
                    (
                        "status",
                        _value(before_case.get("run_status")),
                        _value(after_case.get("run_status")),
                        "n/a",
                    ),
                ),
            ),
            f"Identity: example_id={example_id}; replicate_id={replicate_id}",
            "Question:\n" + _exact_block("question", _value(question)),
            "## Incumbent execution\n" + _jsonl([_replicate_facts(before_case)]),
            "## Candidate execution\n" + _jsonl([_replicate_facts(after_case)]),
            "## Incumbent behavior events\n"
            + _jsonl(_project_behavior_events(incumbent_record)),
            "## Candidate behavior and Hook-effect events\n"
            + _jsonl(_project_behavior_events(candidate_record)),
            (
                "The view preserves actual tool evidence, parsed Student actions, "
                "Hook decisions, effective context changes, fallbacks, final answers, "
                "and errors. Cumulative model-input snapshots, raw outputs duplicated "
                "by parsed events, reasoning, provider usage, provenance, "
                "metadata.results, and omitted inventories are not repeated."
            ),
        )
    )


def render_candidate_trajectory_text(
    store: CandidateComparisonStore,
    *,
    example_id: str,
    replicate_id: str,
    side: str,
    event_index: int,
    field: str,
    offset: int,
    max_characters: int,
) -> str:
    """Read one exact long text field omitted from the default paired view."""

    if side not in {"incumbent", "candidate"}:
        raise ValueError("side must be incumbent or candidate")
    records = (
        store.incumbent_rollouts if side == "incumbent" else store.candidate_rollouts
    )
    record = records[(example_id, replicate_id)]
    trace = _object(record.get("run")).get("trace")
    trace = trace if isinstance(trace, list) else []
    event = next(
        (
            item
            for item in trace
            if isinstance(item, dict) and item.get("index") == event_index
        ),
        None,
    )
    if event is None:
        raise KeyError(f"unknown {side} event index {event_index}")
    payload = _object(event.get("payload"))
    event_type = event.get("event_type")
    if field == "tool_result_content" and event_type == "tool_result":
        content = payload.get("content")
    elif field == "hook_raw_output" and event_type == "hook_model_output":
        content = payload.get("raw_output")
    elif field == "hook_model_input" and event_type == "hook_model_output":
        content = payload.get("model_input")
    elif field == "final_answer" and event_type in {
        "final_answer_candidate",
        "final_answer",
    }:
        content = payload.get("answer")
    else:
        raise ValueError(
            f"field {field} is not available for event type {event.get('event_type')}"
        )
    text = _content_text(content)
    if offset < 0 or max_characters < 1:
        raise ValueError("offset must be non-negative and max_characters positive")
    end = min(len(text), offset + max_characters)
    return "\n\n".join(
        (
            "# Candidate Trajectory Exact Text",
            _table(
                ("field", "value"),
                (
                    ("example_id", example_id),
                    ("replicate_id", replicate_id),
                    ("side", side),
                    ("event_index", str(event_index)),
                    ("event_type", _value(event.get("event_type"))),
                    ("field", field),
                    ("characters", str(len(text))),
                    ("slice", f"{offset}:{end}"),
                    ("remaining_characters", str(max(0, len(text) - end))),
                ),
            ),
            _exact_block("exact_text", text[offset:end]),
        )
    )


def render_candidate_harness_diff(
    store: CandidateComparisonStore,
    *,
    path: str | None,
) -> str:
    """Render a complete small diff or a large-diff directory and path drill-down."""

    value = store.harness_diff()
    if not value.get("available"):
        return "# Candidate Harness Diff\n\n" + _jsonl([value])
    changes = [item for item in value.get("changes", []) if isinstance(item, dict)]
    if path is not None:
        selected = next((item for item in changes if item.get("path") == path), None)
        if selected is None:
            available = ", ".join(str(item.get("path")) for item in changes)
            raise KeyError(f"unknown changed path {path}; available: {available}")
        return "# Candidate Harness File Diff\n\n" + _diff_section(selected)
    total = sum(len(str(item.get("diff") or "")) for item in changes)
    directory = _table(
        ("path", "operation", "diff characters"),
        tuple(
            (
                _value(item.get("path")),
                _value(item.get("operation")),
                str(len(str(item.get("diff") or ""))),
            )
            for item in changes
        ),
    )
    if total <= _INLINE_DIFF_LIMIT:
        body = "\n\n".join(_diff_section(item) for item in changes)
        note = "The complete diff is inline because it is below the size threshold."
    else:
        body = (
            "Full file diffs are available by calling this tool again with an exact "
            "`path` from the directory."
        )
        note = "The aggregate diff exceeded the inline size threshold."
    return "\n\n".join(("# Candidate Harness Diff", directory, note, body))


def _metric_comparison(
    incumbent: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    sections = (
        (
            "answers",
            ("accuracy", "stable_correct_count", "stable_failure_count", "unstable_count", "majority_correct_rate", "pass_at_n", "mean_answer_consistency"),
        ),
        (
            "execution",
            ("completed_rate", "retriever_error_rate", "mean_steps", "mean_tool_calls", "mean_duplicate_queries"),
        ),
        (
            "tokens",
            ("input_tokens", "output_tokens", "student_total_tokens", "hook_total_tokens", "total_tokens"),
        ),
    )
    rows = []
    for section, fields in sections:
        before = _object(incumbent.get(section))
        after = _object(candidate.get(section))
        for field in fields:
            old = before.get(field)
            new = after.get(field)
            rows.append(
                (
                    f"{section}.{field}",
                    _value(old),
                    _value(new),
                    _numeric_delta(old, new),
                )
            )
    return _table(("metric", "incumbent", "candidate", "delta"), tuple(rows))


def _all_changes(store: CandidateComparisonStore) -> list[dict[str, Any]]:
    page_size = 20
    first = store.list_changes(page=1, page_size=page_size, change="any")
    items = list(first.get("items") or [])
    for page in range(2, int(first.get("total_pages") or 1) + 1):
        items.extend(
            store.list_changes(page=page, page_size=page_size, change="any").get(
                "items", []
            )
        )
    return [item for item in items if isinstance(item, dict)]


def _replicate_map(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("replicate_id")): item
        for item in case.get("replicates", [])
        if isinstance(item, dict) and item.get("replicate_id") is not None
    }


def _replicate_facts(value: dict[str, Any]) -> dict[str, Any]:
    execution = _object(value.get("execution"))
    tokens = _object(execution.get("tokens"))
    return {
        "score": value.get("score"),
        "run_status": value.get("run_status"),
        "predicted_answer": value.get("predicted_answer"),
        "runner_error": value.get("runner_error"),
        "execution": {
            "steps": execution.get("steps", "unavailable"),
            "tool_calls": execution.get("tool_calls", "unavailable"),
            "retriever_errors": execution.get("retriever_errors", "unavailable"),
            "duplicate_queries": execution.get("duplicate_queries", "unavailable"),
            "tokens": {
                key: tokens.get(key, "unavailable")
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "student_total_tokens",
                    "hook_total_tokens",
                    "total_tokens",
                )
            },
        },
    }


def _execution_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old = _object(before.get("execution"))
    new = _object(after.get("execution"))
    old_tokens = _object(old.get("tokens"))
    new_tokens = _object(new.get("tokens"))
    return {
        key: _delta_value(old.get(key), new.get(key))
        for key in ("steps", "tool_calls", "retriever_errors", "duplicate_queries")
    } | {
        "tokens": {
            key: _delta_value(old_tokens.get(key), new_tokens.get(key))
            for key in (
                "input_tokens",
                "output_tokens",
                "student_total_tokens",
                "hook_total_tokens",
                "total_tokens",
            )
        }
    }


def _hook_activity(record: dict[str, Any]) -> dict[str, Any]:
    trace = _object(record.get("run")).get("trace")
    trace = trace if isinstance(trace, list) else []
    decisions = []
    changes = []
    for event in trace:
        if not isinstance(event, dict):
            continue
        payload = _object(event.get("payload"))
        event_type = event.get("event_type")
        if event_type == "hook_model_output":
            decisions.append(
                {
                    "event_index": event.get("index"),
                    "step": event.get("step"),
                    "phase": payload.get("phase"),
                    "hook_id": payload.get("hook_id"),
                    "output_preview": _preview(
                        _content_text(payload.get("raw_output"))
                    ),
                }
            )
        elif event_type == "hook_applied":
            raw_changes = payload.get("changes")
            raw_changes = raw_changes if isinstance(raw_changes, list) else []
            targets = [
                str(item.get("key"))
                for item in raw_changes
                if isinstance(item, dict) and item.get("key") is not None
            ]
            changes.append(
                {
                    "event_index": event.get("index"),
                    "step": event.get("step"),
                    "phase": payload.get("phase"),
                    "hook_id": payload.get("hook_id"),
                    "modified_targets": targets,
                }
            )
    return {
        "decision_calls": decisions,
        "hook_change_events": changes,
    }


def _project_behavior_events(record: dict[str, Any]) -> list[dict[str, Any]]:
    trace = _object(record.get("run")).get("trace")
    trace = trace if isinstance(trace, list) else []
    events = []
    for event in trace:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        if event_type not in _TRACE_EVENT_TYPES:
            continue
        payload = _object(event.get("payload"))
        if event_type == "tool_result":
            projected = {
                "name": payload.get("name"),
                "content": payload.get("content"),
            }
        elif event_type == "hook_model_output":
            raw_output = _content_text(payload.get("raw_output"))
            model_input = _content_text(payload.get("model_input"))
            projected = {
                key: payload.get(key)
                for key in ("phase", "hook_id", "profile", "purpose")
                if key in payload
            }
            projected["raw_output_characters"] = len(raw_output)
            projected["raw_output_preview"] = _preview(raw_output)
            projected["exact_text_field"] = "hook_raw_output"
            projected["model_input_characters"] = len(model_input)
            projected["model_input_preview"] = _preview(model_input)
            projected["model_input_exact_text_field"] = "hook_model_input"
        elif event_type == "hook_applied":
            projected = {
                "phase": payload.get("phase"),
                "hook_id": payload.get("hook_id"),
                "changes": _project_hook_changes(payload.get("changes")),
            }
        else:
            projected = _strip_noise(payload)
        events.append(
            {
                "index": event.get("index"),
                "step": event.get("step"),
                "event_type": event_type,
                "payload": projected,
            }
        )
    return events


def _project_hook_changes(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        _project_hook_change(item)
        for item in value
        if isinstance(item, dict)
    ]


def _project_hook_change(change: dict[str, Any]) -> dict[str, Any]:
    key = str(change.get("key", "unavailable"))
    before = _strip_noise(change.get("before"))
    after = _strip_noise(change.get("after"))
    if key == "stage.tool_result":
        old = _object(before)
        new = _object(after)
        old_content = old.get("content")
        new_content = new.get("content")
        if (
            isinstance(old_content, str)
            and isinstance(new_content, str)
            and new_content.startswith(old_content)
        ):
            return {
                "target": key,
                "effect": "content appended before entering Student context",
                "tool": new.get("name"),
                "source_content_characters": len(old_content),
                "source_content_preview": _preview(old_content),
                "effective_content_characters": len(new_content),
                "appended_content": new_content[len(old_content) :],
            }
    return {
        "target": key,
        "effect": "content replaced before entering Student context",
        "source": _compact_change_side(before),
        "effective": _compact_change_side(after),
    }


def _compact_change_side(value: object) -> object:
    text = _content_text(value)
    if len(text) <= _INLINE_CHANGE_LIMIT:
        return value
    return {"characters": len(text), "preview": _preview(text)}


def _strip_noise(value: object) -> object:
    if isinstance(value, list):
        return [_strip_noise(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in {"omitted", "usage", "reasoning", "reasoning_content", "thinking", "inband_thinking"}:
            continue
        if key == "metadata" and isinstance(item, dict):
            metadata = {
                subkey: _strip_noise(subvalue)
                for subkey, subvalue in item.items()
                if subkey != "results"
            }
            if metadata:
                result[key] = metadata
            continue
        result[key] = _strip_noise(item)
    return result


def _diff_section(change: dict[str, Any]) -> str:
    path = _value(change.get("path"))
    operation = _value(change.get("operation"))
    return f"## {path} ({operation})\n\n```diff\n{change.get('diff') or ''}\n```"


def _score_change(before: object, after: object) -> str:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return _change_label(float(before), float(after))
    return "unavailable"


def _change_label(before: float, after: float) -> str:
    if after > before:
        return "improved"
    if after < before:
        return "regressed"
    return "unchanged"


def _numeric_delta(before: object, after: object) -> str:
    delta = _delta_value(before, after)
    return _value(delta)


def _delta_value(before: object, after: object) -> float | int | str:
    if not isinstance(before, (int, float)) or isinstance(before, bool):
        return "unavailable"
    if not isinstance(after, (int, float)) or isinstance(after, bool):
        return "unavailable"
    return after - before


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _preview(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) <= _PREVIEW_LIMIT:
        return compact
    return compact[: _PREVIEW_LIMIT - 1].rstrip() + "…"


def _table(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> str:
    if not rows:
        rows = (tuple("none" for _ in headers),)
    header = "| " + " | ".join(_cell(item) for item in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_cell(item) for item in row) + " |" for row in rows]
    return "\n".join((header, divider, *body))


def _jsonl(items: object) -> str:
    values = list(items) if isinstance(items, (list, tuple)) else []
    if not values:
        return "none"
    body = "\n".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in values
    )
    return f"```jsonl\n{body}\n```"


def _exact_block(label: str, content: str) -> str:
    return f"<{label}>\n{content}\n</{label}>"


def _value(value: object) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _cell(value: object) -> str:
    return _value(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
