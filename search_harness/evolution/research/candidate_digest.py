"""Deterministic compact outcome summary for one evaluated Candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .resources.stores import CandidateComparisonStore


def build_candidate_outcome_digest(
    *,
    store: CandidateComparisonStore,
    mechanism: dict[str, Any],
    implementation_summary: str,
) -> dict[str, Any]:
    """Summarize paired outcomes and Hook attribution without raw traces."""

    changes = store.list_changes(
        page=1,
        page_size=max(1, len(store.incumbent_cases)),
        change="any",
    )["items"]
    logical_counts = {
        label: sum(item.get("change") == label for item in changes)
        for label in ("improved", "regressed", "unchanged")
    }
    rollout_counts = {
        "improved": 0,
        "regressed": 0,
        "unchanged_correct": 0,
        "unchanged_incorrect": 0,
    }
    hook_labels: dict[str, int] = {}
    modified_examples: set[str] = set()
    beneficial_examples: set[str] = set()
    harmful_examples: set[str] = set()
    nearby: dict[str, list[dict[str, str]]] = {
        "beneficial_activation": [],
        "harmful_activation": [],
        "neutral_activation": [],
        "missed_target": [],
        "false_positive": [],
        "parse_failure": [],
        "unattributed_improvement": [],
        "unattributed_regression": [],
    }
    hook_change_count = 0

    for example_id in sorted(store.incumbent_cases):
        before = _replicate_map(store.incumbent_cases[example_id])
        after = _replicate_map(store.candidate_cases[example_id])
        for replicate_id in sorted(set(before) & set(after)):
            before_score = _score(before[replicate_id].get("score"))
            after_score = _score(after[replicate_id].get("score"))
            if after_score > before_score:
                outcome = "improved"
                rollout_counts["improved"] += 1
            elif after_score < before_score:
                outcome = "regressed"
                rollout_counts["regressed"] += 1
            elif after_score > 0:
                outcome = "unchanged_correct"
                rollout_counts["unchanged_correct"] += 1
            else:
                outcome = "unchanged_incorrect"
                rollout_counts["unchanged_incorrect"] += 1

            record = store.candidate_rollouts.get((example_id, replicate_id), {})
            activity = _hook_activity(record)
            for label, count in activity["labels"].items():
                hook_labels[label] = hook_labels.get(label, 0) + count
            modified = activity["change_count"] > 0
            hook_change_count += activity["change_count"]
            ref = {"example_id": example_id, "replicate_id": replicate_id}
            if modified:
                modified_examples.add(example_id)
                if outcome == "improved":
                    beneficial_examples.add(example_id)
                    nearby["beneficial_activation"].append(ref)
                elif outcome == "regressed":
                    harmful_examples.add(example_id)
                    nearby["harmful_activation"].append(ref)
                else:
                    nearby["neutral_activation"].append(ref)
            elif outcome == "improved":
                nearby["unattributed_improvement"].append(ref)
            elif outcome == "regressed":
                nearby["unattributed_regression"].append(ref)
            if activity["parse_failure"]:
                nearby["parse_failure"].append(ref)

    mechanism_json = json.dumps(
        mechanism,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = {
        "schema_version": 1,
        "effect_goal": mechanism.get("effect_goal", "task_outcome"),
        "mechanism": {
            "goal": mechanism.get("goal"),
            "fingerprint": hashlib.sha256(
                mechanism_json.encode("utf-8")
            ).hexdigest(),
        },
        "implementation_summary": implementation_summary,
        "metrics": {
            "incumbent": _metric_projection(store.incumbent_summary),
            "candidate": _metric_projection(store.candidate_summary),
            "accuracy_delta": _accuracy(store.candidate_summary)
            - _accuracy(store.incumbent_summary),
        },
        "logical_example_changes": logical_counts,
        "rollout_changes": rollout_counts,
        "hook_activity": {
            "decision_label_counts": hook_labels,
            "change_event_count": hook_change_count,
            "target_behavior_example_count": len(modified_examples),
            "attributed_beneficial_example_count": len(beneficial_examples),
            "attributed_harmful_example_count": len(harmful_examples),
        },
        "nearby_cases": {
            key: values[:20] for key, values in nearby.items()
        },
    }
    return digest


def write_candidate_outcome_digest(
    path: Path,
    value: dict[str, Any],
) -> Path:
    """Persist one UTF-8 digest without mutating evaluation artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _replicate_map(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("replicate_id")): item
        for item in case.get("replicates", [])
        if isinstance(item, dict) and item.get("replicate_id") is not None
    }


def _score(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _hook_activity(record: dict[str, Any]) -> dict[str, Any]:
    run = record.get("run")
    trace = run.get("trace", []) if isinstance(run, dict) else []
    labels: dict[str, int] = {}
    change_count = 0
    parse_failure = False
    for event in trace if isinstance(trace, list) else []:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event.get("event_type") == "hook_model_output":
            label = _decision_label(payload.get("raw_output"))
            labels[label] = labels.get(label, 0) + 1
            parse_failure = parse_failure or label == "parse_failure"
        elif event.get("event_type") == "hook_applied":
            changes = payload.get("changes")
            if isinstance(changes, list) and changes:
                change_count += 1
    return {
        "labels": labels,
        "change_count": change_count,
        "parse_failure": parse_failure,
    }


def _decision_label(value: object) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False)
        if value is not None
        else ""
    ).lower()
    stripped = text.strip().strip('"').strip("'")
    if stripped in {"positive", "negative", "uncertain"}:
        return stripped
    for label in ("positive", "negative", "uncertain"):
        if f'"{label}"' in text or f": {label}" in text:
            return label
    return "parse_failure"


def _accuracy(summary: dict[str, Any]) -> float:
    metrics = summary.get("metrics")
    answers = metrics.get("answers") if isinstance(metrics, dict) else None
    value = answers.get("accuracy") if isinstance(answers, dict) else None
    return float(value) if isinstance(value, (int, float)) else 0.0


def _metric_projection(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = summary.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    answers = metrics.get("answers")
    answers = answers if isinstance(answers, dict) else {}
    tokens = metrics.get("tokens")
    tokens = tokens if isinstance(tokens, dict) else {}
    return {
        "accuracy": answers.get("accuracy"),
        "stable_correct_count": answers.get("stable_correct_count"),
        "stable_failure_count": answers.get("stable_failure_count"),
        "unstable_count": answers.get("unstable_count"),
        "total_tokens": tokens.get("total_tokens"),
        "hook_total_tokens": tokens.get("hook_total_tokens"),
    }
