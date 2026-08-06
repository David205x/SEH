"""Deterministic inputs and aggregation for Mechanism Conformance Replay."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from search_harness.datasets import DatasetExample
from .roles.contracts import ConformanceFinding

from ..experience import load_experience_set


CONFORMANCE_REPLICATES = 3

_CONFORMANCE_EVENT_TYPES = frozenset(
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


@dataclass(frozen=True)
class ConformanceCase:
    """One distinct intervention example and its distilled trial evidence."""

    example: DatasetExample
    trial_refs: tuple[str, ...]
    reference_observations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ConformanceSummary:
    """Program-owned suite decision derived from independent findings."""

    decision: str
    finding_counts: dict[str, int]
    per_example: dict[str, dict[str, Any]]
    compiler_feedback: tuple[str, ...]
    finding_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "finding_counts": dict(self.finding_counts),
            "per_example": {
                key: dict(value) for key, value in self.per_example.items()
            },
            "compiler_feedback": list(self.compiler_feedback),
            "finding_refs": list(self.finding_refs),
        }


def project_conformance_trajectory(
    record: dict[str, Any],
) -> dict[str, Any]:
    """投影 Reviewer 判断机制保真所需的完整行为证据。"""

    example = record.get("example")
    example = example if isinstance(example, dict) else {}
    run = record.get("run")
    run = run if isinstance(run, dict) else {}
    trace = run.get("trace")
    trace = trace if isinstance(trace, list) else []
    return {
        "view": "conformance",
        "example": {
            "example_id": example.get("example_id"),
            "question": example.get("question") or run.get("question"),
        },
        "replicate": record.get("replicate"),
        "harness": _conformance_harness(record.get("harness")),
        "run": {
            "status": run.get("status"),
            "answer": run.get("answer"),
            "error": run.get("error"),
        },
        "events": [
            projected
            for event in trace
            if isinstance(event, dict)
            and (projected := _project_conformance_event(event)) is not None
        ],
        "runner_error": record.get("runner_error"),
        "omitted": [
            "repeated Student model_input snapshots",
            "Student and Hook-model reasoning",
            "provider usage metadata",
            "unselected runtime events and filesystem provenance",
        ],
    }


def load_conformance_cases(
    *,
    experience_file: Path,
    trial_files: Iterable[Path],
) -> tuple[ConformanceCase, ...]:
    """Resolve distinct trial example IDs against the frozen Experience Set."""

    examples = {
        example.example_id: example
        for example in load_experience_set(experience_file)
    }
    evidence_by_example: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    order: list[str] = []
    for path in trial_files:
        artifact = _read_object(path)
        role_input = artifact.get("input")
        if not isinstance(role_input, dict):
            raise ValueError(f"intervention trial lacks role input: {path}")
        example_id = role_input.get("example_id")
        if not isinstance(example_id, str) or not example_id.strip():
            raise ValueError(f"intervention trial lacks example_id: {path}")
        if example_id not in examples:
            raise KeyError(
                f"intervention example is absent from Experience Set: "
                f"{example_id}"
            )
        if example_id not in evidence_by_example:
            order.append(example_id)
            evidence_by_example[example_id] = []
        trial_ref = path.parent.name
        evidence_by_example[example_id].append(
            (trial_ref, _reference_observation(artifact, trial_ref))
        )

    if not order:
        raise ValueError("conformance replay requires intervention trials")
    return tuple(
        ConformanceCase(
            example=examples[example_id],
            trial_refs=tuple(
                item[0] for item in evidence_by_example[example_id]
            ),
            reference_observations=tuple(
                item[1] for item in evidence_by_example[example_id]
            ),
        )
        for example_id in order
    )


def aggregate_conformance(
    *,
    cases: Iterable[ConformanceCase],
    findings: Iterable[ConformanceFinding],
    finding_refs: Iterable[str],
) -> ConformanceSummary:
    """Apply the per-example faithful and global failure rules."""

    case_items = tuple(cases)
    finding_items = tuple(findings)
    refs = tuple(finding_refs)
    if len(refs) != len(finding_items):
        raise ValueError("conformance finding refs must match findings")

    expected = {
        (
            case.example.example_id,
            f"r{replicate_index:03d}",
        )
        for case in case_items
        for replicate_index in range(CONFORMANCE_REPLICATES)
    }
    indexed: dict[tuple[str, str], ConformanceFinding] = {}
    for finding in finding_items:
        try:
            example_id, replicate_id = finding.candidate_run_ref.rsplit(
                "/",
                maxsplit=1,
            )
        except ValueError as exc:
            raise ValueError(
                "candidate_run_ref must be <example_id>/<replicate_id>"
            ) from exc
        key = (example_id, replicate_id)
        if key in indexed:
            raise ValueError(
                f"duplicate conformance finding: {finding.candidate_run_ref}"
            )
        indexed[key] = finding
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        raise ValueError(
            f"conformance findings do not match replay suite; "
            f"missing={missing}, extra={extra}"
        )

    counts = Counter(item.verdict for item in finding_items)
    hard_failures = {
        "runtime_error",
        "implementation_mismatch",
    }
    compiler_feedback = _unique(
        item.repair_obligation
        for item in finding_items
        if item.verdict in hard_failures
    )
    per_example: dict[str, dict[str, Any]] = {}
    missing_faithful = []
    for case in case_items:
        example_id = case.example.example_id
        local = [
            indexed[(example_id, f"r{index:03d}")]
            for index in range(CONFORMANCE_REPLICATES)
        ]
        local_counts = Counter(item.verdict for item in local)
        faithful_count = local_counts["faithful"]
        per_example[example_id] = {
            "faithful_count": faithful_count,
            "verdict_counts": dict(local_counts),
            "passed": faithful_count >= 1,
        }
        if faithful_count < 1:
            missing_faithful.append(example_id)
            compiler_feedback.extend(
                _unique(
                    item.repair_obligation
                    for item in local
                    if item.verdict in {"not_observed", "inconclusive"}
                )
            )

    decision = (
        "pass"
        if not (set(counts) & hard_failures) and not missing_faithful
        else "revise_implementation"
    )
    return ConformanceSummary(
        decision=decision,
        finding_counts=dict(counts),
        per_example=per_example,
        compiler_feedback=tuple(_unique(compiler_feedback)),
        finding_refs=refs,
    )


def runtime_error_finding(
    *,
    case: ConformanceCase,
    replicate_id: str,
    error: str,
) -> ConformanceFinding:
    """Create a deterministic finding when no model review is possible."""

    compact_error = " ".join(error.split())[:350]
    return ConformanceFinding(
        trial_refs=list(case.trial_refs),
        candidate_run_ref=f"{case.example.example_id}/{replicate_id}",
        verdict="runtime_error",
        observed_phases=[],
        assessment=f"Candidate rollout failed: {compact_error}",
        repair_obligation=(
            "Repair the compiled Harness so the complete Student rollout "
            f"finishes without this runtime failure: {compact_error}"
        ),
    )


def _reference_observation(
    artifact: dict[str, Any],
    trial_ref: str,
) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    trial = resources.get("intervention_trial")
    if not isinstance(trial, dict):
        raise ValueError(
            f"intervention artifact lacks intervention_trial: {trial_ref}"
        )
    return {
        "trial_ref": trial_ref,
        "phase_plan": trial.get("phase_plan"),
        "activation_counts": trial.get("activation_counts"),
        "context_changes": _project_reference_changes(
            trial.get("context_changes")
        ),
        "phase_effects": trial.get("phase_effects"),
    }


def _conformance_harness(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key)
        for key in ("harness_id", "manifest_digest", "template_digest")
        if key in value
    }


def _project_conformance_event(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    event_type = event.get("event_type")
    if event_type not in _CONFORMANCE_EVENT_TYPES:
        return None
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    if event_type == "hook_model_output":
        projected_payload = {
            key: payload.get(key)
            for key in ("phase", "hook_id", "profile", "purpose", "raw_output")
            if key in payload
        }
    elif event_type == "hook_applied":
        projected_payload = {
            "phase": payload.get("phase"),
            "hook_id": payload.get("hook_id"),
            "changes": _project_hook_changes(payload.get("changes")),
        }
    elif event_type == "tool_result":
        projected_payload = {
            key: payload.get(key)
            for key in ("name", "content")
            if key in payload
        }
    elif event_type == "parsed_output":
        projected_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"inband_thinking", "metadata", "usage"}
        }
    else:
        projected_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"metadata", "usage"}
        }
    return {
        "index": event.get("index"),
        "step": event.get("step"),
        "event_type": event_type,
        "payload": projected_payload,
    }


def _project_hook_changes(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        _project_hook_change(change)
        for change in value
        if isinstance(change, dict)
    ]


def _project_hook_change(change: dict[str, Any]) -> dict[str, Any]:
    key = str(change.get("key", ""))
    before = change.get("before")
    after = change.get("after")
    result: dict[str, Any] = {"key": key}
    if key == "stage.model_input":
        result["message_changes"] = _model_input_changes(before, after)
        return result
    if key == "stage.tool_result":
        result.update(_tool_result_change(before, after))
        return result
    result["before"] = _strip_runtime_metadata(before)
    result["after"] = _strip_runtime_metadata(after)
    return result


def _model_input_changes(before: object, after: object) -> dict[str, Any]:
    before_messages = _messages(before)
    after_messages = _messages(after)
    changes = []
    for block_id in range(1, max(len(before_messages), len(after_messages)) + 1):
        old = before_messages[block_id - 1] if block_id <= len(before_messages) else None
        new = after_messages[block_id - 1] if block_id <= len(after_messages) else None
        if old == new:
            continue
        changes.append(
            {
                "block_id": block_id,
                "before": old,
                "after": new,
            }
        )
    return {
        "before_count": len(before_messages),
        "after_count": len(after_messages),
        "changed_blocks": changes,
    }


def _messages(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    messages = value.get("messages")
    if not isinstance(messages, list):
        return []
    return [
        {
            "role": message.get("role"),
            "content": message.get("content"),
        }
        for message in messages
        if isinstance(message, dict)
    ]


def _tool_result_change(before: object, after: object) -> dict[str, Any]:
    old = _tool_result(before)
    new = _tool_result(after)
    old_content = old.get("content")
    new_content = new.get("content")
    if (
        old.get("name") == new.get("name")
        and isinstance(old_content, str)
        and isinstance(new_content, str)
        and new_content.startswith(old_content)
    ):
        return {
            "name": new.get("name"),
            "original_content_unchanged": True,
            "appended_content": new_content[len(old_content) :],
        }
    return {"before": old, "after": new}


def _tool_result(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: value.get(key)
        for key in ("name", "content")
        if key in value
    }


def _strip_runtime_metadata(value: object) -> object:
    if isinstance(value, list):
        return [_strip_runtime_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _strip_runtime_metadata(item)
        for key, item in value.items()
        if key not in {
            "metadata",
            "usage",
            "reasoning",
            "reasoning_content",
            "thinking",
        }
    }


def _project_reference_changes(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projected = []
    for change in value:
        if not isinstance(change, dict):
            continue
        item = {
            key: _strip_runtime_metadata(item)
            for key, item in change.items()
            if key not in {"model_input_before", "model_input_after"}
        }
        if "model_input_before" in change or "model_input_after" in change:
            item["model_input_change"] = _model_input_changes(
                change.get("model_input_before"),
                change.get("model_input_after"),
            )
        projected.append(item)
    return projected


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return value


def _unique(values: Iterable[str | None]) -> list[str]:
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )
