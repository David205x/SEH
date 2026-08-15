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
    failure_layer_counts: dict[str, int]
    recommended_route_counts: dict[str, int]
    recommended_route: str | None
    route_feedback: dict[str, tuple[str, ...]]
    per_example: dict[str, dict[str, Any]]
    compiler_feedback: tuple[str, ...]
    finding_refs: tuple[str, ...]
    local_efficacy_counts: dict[str, int]
    local_efficacy_gate: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "finding_counts": dict(self.finding_counts),
            "failure_layer_counts": dict(self.failure_layer_counts),
            "recommended_route_counts": dict(self.recommended_route_counts),
            "recommended_route": self.recommended_route,
            "route_feedback": {
                key: list(values)
                for key, values in self.route_feedback.items()
            },
            "per_example": {
                key: dict(value) for key, value in self.per_example.items()
            },
            "compiler_feedback": list(self.compiler_feedback),
            "finding_refs": list(self.finding_refs),
            "local_efficacy_counts": dict(self.local_efficacy_counts),
            "local_efficacy_gate": self.local_efficacy_gate,
        }


def project_conformance_trajectory(
    record: dict[str, Any],
    *,
    evaluation: dict[str, Any] | None = None,
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
        "evaluation": evaluation,
        "hook_model_cost": _hook_model_cost(trace),
        "events": [
            projected
            for event in trace
            if isinstance(event, dict)
            and (projected := _project_conformance_event(event)) is not None
        ],
        "runner_error": record.get("runner_error"),
    }


def render_conformance_batch_input(value: dict[str, Any]) -> str:
    """Render shared evidence once and give every replicate an explicit boundary."""

    trajectories = value.get("candidate_trajectory_views")
    trajectories = trajectories if isinstance(trajectories, list) else []
    lines = [
        "# Example-level Conformance Review Batch",
        (
            "Judge each replicate independently. Shared Mechanism and reference "
            "evidence appear once; never infer one finding from another "
            "replicate's behavior."
        ),
        "",
        "## Shared authoritative Mechanism",
        "```json",
        _compact_json(value.get("mechanism")),
        "```",
        "",
        "## Shared reference boundary",
        f"example_id: {value.get('example_id', 'unavailable')}",
        "trial_refs: " + _compact_json(value.get("trial_refs")),
        "```json",
        _compact_json(value.get("reference_observations")),
        "```",
        "",
        "## Candidate rollout views",
    ]
    for item in trajectories:
        item = item if isinstance(item, dict) else {}
        lines.extend(
            (
                f"### replicate {item.get('replicate_id', 'unavailable')}",
                "```json",
                _compact_json(item.get("candidate_trajectory_view")),
                "```",
            )
        )
    lines.extend(
        (
            "",
            "## Submission requirement",
            (
                "Submit exactly one independent finding for every replicate_id "
                "above, in the same order. Apply the full verdict and diagnostic "
                "contract separately to every finding."
            ),
        )
    )
    return "\n".join(lines)


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

    efficacy_counts = Counter(
        item.local_efficacy for item in finding_items
    )
    if efficacy_counts["harmful"]:
        efficacy_gate = "fail"
    elif efficacy_counts["beneficial"]:
        efficacy_gate = "pass"
    else:
        efficacy_gate = "inconclusive"
    decision = (
        "pass"
        if not (set(counts) & hard_failures)
        and not missing_faithful
        and efficacy_gate != "fail"
        else "revise"
    )
    route_feedback = {
        route: tuple(
            _unique(
                item.repair_obligation
                for item in finding_items
                if item.recommended_route == route
            )
        )
        for route in ("evidence", "mechanism", "implementation")
    }
    if (
        efficacy_gate == "fail"
        and not (set(counts) & hard_failures)
        and not missing_faithful
    ):
        route_feedback["evidence"] = tuple(
            _unique(
                [
                    *route_feedback["evidence"],
                    (
                        "The locally faithful Candidate replay produced a "
                        "harmful task outcome. Re-establish that the researched "
                        "mechanism has a supported local task benefit before "
                        "another full Candidate Evaluation."
                    ),
                ]
            )
        )
    recommended_route = next(
        (
            route
            for route in ("evidence", "mechanism", "implementation")
            if route_feedback[route]
        ),
        None,
    )
    return ConformanceSummary(
        decision=decision,
        finding_counts=dict(counts),
        failure_layer_counts=dict(
            Counter(
                item.failure_layer
                for item in finding_items
                if item.failure_layer is not None
            )
        ),
        recommended_route_counts=dict(
            Counter(
                item.recommended_route
                for item in finding_items
                if item.recommended_route is not None
            )
        ),
        recommended_route=recommended_route,
        route_feedback=route_feedback,
        per_example=per_example,
        compiler_feedback=tuple(_unique(compiler_feedback)),
        finding_refs=refs,
        local_efficacy_counts=dict(efficacy_counts),
        local_efficacy_gate=efficacy_gate,
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
        failure_layer="integration",
        decisive_input_summary=(
            "The Candidate rollout ended with an explicit runtime failure "
            "before conformance could be established."
        ),
        recommended_route="implementation",
        local_efficacy="inconclusive",
        local_efficacy_assessment=(
            "The rollout did not complete, so local task effect is unavailable."
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
        "trial_outcome": _project_trial_outcome(trial.get("comparison")),
    }


def _project_trial_outcome(value: object) -> dict[str, Any] | None:
    """Expose only score-level Trial outcomes needed for local preflight."""

    if not isinstance(value, dict):
        return None
    source = value.get("source")
    branch = value.get("branch")
    source = source if isinstance(source, dict) else {}
    branch = branch if isinstance(branch, dict) else {}
    teacher = branch.get("teacher")
    teacher = teacher if isinstance(teacher, dict) else {}
    return {
        "source": {
            "score": source.get("score"),
            "status": source.get("status"),
        },
        "intervention_branch": {
            "score": branch.get("score"),
            "score_source": branch.get("score_source"),
            "teacher_assessment": teacher.get("assessment"),
            "status": branch.get("status"),
        },
        "exact_match_delta": value.get("exact_match_delta"),
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
            for key in (
                "phase",
                "hook_id",
                "profile",
                "purpose",
                "thinking_mode",
                "raw_output",
            )
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


def _hook_model_cost(trace: list[object]) -> dict[str, Any]:
    """Summarize actual Hook-model calls without exposing reasoning metadata."""

    calls = []
    total_tokens = 0
    for event in trace:
        if not isinstance(event, dict) or event.get("event_type") != "hook_model_output":
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        usage = metadata.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        call_tokens = _usage_total(usage)
        total_tokens += call_tokens
        calls.append(
            {
                "step": event.get("step"),
                "phase": payload.get("phase"),
                "hook_id": payload.get("hook_id"),
                "profile": payload.get("profile"),
                "purpose": payload.get("purpose"),
                "thinking_mode": payload.get("thinking_mode", "inherited"),
                "total_tokens": call_tokens,
            }
        )
    return {
        "call_count": len(calls),
        "total_tokens": total_tokens,
        "calls": calls,
    }


def _usage_total(usage: dict[str, Any]) -> int:
    value = usage.get("total_tokens")
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    prompt = usage.get("prompt_tokens", usage.get("prompt_eval_count", 0))
    completion = usage.get(
        "completion_tokens",
        usage.get("eval_count", 0),
    )
    return _non_negative_usage(prompt) + _non_negative_usage(completion)


def _non_negative_usage(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value


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
        old = (
            before_messages[block_id - 1]
            if block_id <= len(before_messages)
            else None
        )
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


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _unique(values: Iterable[str | None]) -> list[str]:
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )
