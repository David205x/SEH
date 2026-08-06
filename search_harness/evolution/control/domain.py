"""Deterministic domain objects for the evidence-driven Evolution Controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class WorkKind(str, Enum):
    """One bounded role invocation or deterministic control-plane effect."""

    EVALUATE_INCUMBENT = "evaluate_incumbent"
    ANALYZE_FAILURE = "analyze_failure"
    RESEARCH_HYPOTHESIS = "research_hypothesis"
    SELECT_TRIAL = "select_trial"
    EXECUTE_TRIAL = "execute_trial"
    REVIEW_EVIDENCE = "review_evidence"
    DISTILL_MECHANISM = "distill_mechanism"
    COMPILE_CANDIDATE = "compile_candidate"
    STAGE_CANDIDATE = "stage_candidate"
    VERIFY_CONFORMANCE = "verify_conformance"
    EVALUATE_CANDIDATE = "evaluate_candidate"
    REVIEW_CANDIDATE = "review_candidate"
    PROMOTE_CANDIDATE = "promote_candidate"
    REJECT_CANDIDATE = "reject_candidate"


WorkStatus = Literal["queued", "running", "completed", "failed"]
RunStatus = Literal["new", "running", "paused", "completed"]


@dataclass(frozen=True)
class WorkItem:
    """A durable, independently retryable unit selected from the run agenda."""

    work_id: str
    kind: WorkKind
    subject_ref: str
    input_refs: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    parent_work_id: str | None = None
    attempt: int = 1

    def __post_init__(self) -> None:
        if not self.work_id.strip():
            raise ValueError("work_id must not be empty")
        if not self.subject_ref.strip():
            raise ValueError("subject_ref must not be empty")
        if self.attempt < 1:
            raise ValueError("work attempt must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "kind": self.kind.value,
            "subject_ref": self.subject_ref,
            "input_refs": dict(self.input_refs),
            "payload": dict(self.payload),
            "parent_work_id": self.parent_work_id,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorkItem":
        return cls(
            work_id=_required_string(value, "work_id"),
            kind=WorkKind(_required_string(value, "kind")),
            subject_ref=_required_string(value, "subject_ref"),
            input_refs=_string_mapping(value.get("input_refs", {}), "input_refs"),
            payload=_object(value.get("payload", {}), "payload"),
            parent_work_id=_optional_string(value.get("parent_work_id")),
            attempt=_positive_integer(value.get("attempt", 1), "attempt"),
        )


@dataclass
class WorkRecord:
    """Projected execution status for one immutable WorkItem."""

    item: WorkItem
    status: WorkStatus = "queued"
    result_ref: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class EffectResult:
    """Small deterministic result plus references to large persisted artifacts."""

    outcome: dict[str, Any]
    artifact_refs: dict[str, str] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": dict(self.outcome),
            "artifact_refs": dict(self.artifact_refs),
            "usage": dict(self.usage),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EffectResult":
        raw_usage = _object(value.get("usage", {}), "usage")
        usage: dict[str, int] = {}
        for name, amount in raw_usage.items():
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                raise TypeError(f"effect usage '{name}' must be a non-negative integer")
            usage[str(name)] = amount
        return cls(
            outcome=_object(value.get("outcome"), "outcome"),
            artifact_refs=_string_mapping(
                value.get("artifact_refs", {}),
                "artifact_refs",
            ),
            usage=usage,
        )


@dataclass(frozen=True)
class ControlEvent:
    """One append-only state transition in the Controller journal."""

    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ControlEvent":
        return cls(
            sequence=_positive_integer(value.get("sequence"), "sequence"),
            event_type=_required_string(value, "event_type"),
            payload=_object(value.get("payload"), "payload"),
            created_at=_required_string(value, "created_at"),
        )


@dataclass
class ControlState:
    """Journal-derived run state; artifacts remain outside this projection."""

    run_id: str | None = None
    status: RunStatus = "new"
    status_reason: str | None = None
    initial_version: str | None = None
    current_version: str | None = None
    generation: int = 0
    works: dict[str, WorkRecord] = field(default_factory=dict)
    work_order: list[str] = field(default_factory=list)
    transitioned_work_ids: set[str] = field(default_factory=set)
    total_tokens: int = 0
    completed_work_count: int = 0

    @property
    def queued(self) -> tuple[WorkRecord, ...]:
        return tuple(
            self.works[work_id]
            for work_id in self.work_order
            if self.works[work_id].status == "queued"
        )

    @property
    def running(self) -> tuple[WorkRecord, ...]:
        return tuple(
            self.works[work_id]
            for work_id in self.work_order
            if self.works[work_id].status == "running"
        )

    @property
    def pending_transitions(self) -> tuple[WorkRecord, ...]:
        return tuple(
            self.works[work_id]
            for work_id in self.work_order
            if self.works[work_id].status in {"completed", "failed"}
            and work_id not in self.transitioned_work_ids
        )


@dataclass(frozen=True)
class EvolutionControlConfig:
    """Budgets and deterministic gates owned by the formal Controller."""

    max_generations: int = 1
    max_trials_per_hypothesis: int = 4
    max_trial_assignments: int = 12
    max_hypothesis_revisions: int = 2
    max_mechanism_revisions: int = 2
    max_compiler_revisions: int = 2
    max_candidate_revisions: int = 2
    max_work_retries: int = 1
    max_work_items: int = 80
    max_total_tokens: int | None = None
    min_accuracy_delta: float = -0.02
    max_total_token_ratio: float | None = 3.0

    def __post_init__(self) -> None:
        positive = {
            "max_generations": self.max_generations,
            "max_trials_per_hypothesis": self.max_trials_per_hypothesis,
            "max_trial_assignments": self.max_trial_assignments,
            "max_work_items": self.max_work_items,
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")
        non_negative = {
            "max_hypothesis_revisions": self.max_hypothesis_revisions,
            "max_mechanism_revisions": self.max_mechanism_revisions,
            "max_compiler_revisions": self.max_compiler_revisions,
            "max_candidate_revisions": self.max_candidate_revisions,
            "max_work_retries": self.max_work_retries,
        }
        for name, value in non_negative.items():
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be positive when configured")
        if (
            self.max_total_token_ratio is not None
            and self.max_total_token_ratio <= 0
        ):
            raise ValueError("max_total_token_ratio must be positive")
        if not -1.0 <= self.min_accuracy_delta <= 1.0:
            raise ValueError("min_accuracy_delta must be between -1 and 1")


@dataclass(frozen=True)
class ControlOutcome:
    """User-facing result of one Controller invocation."""

    status: RunStatus
    reason: str
    current_version: str
    generation: int
    completed_work_count: int
    total_tokens: int


def project_events(events: list[ControlEvent]) -> ControlState:
    """Replay validated journal events into one deterministic state projection."""

    state = ControlState()
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence:
            raise ValueError(
                "Control journal sequence is not contiguous: "
                f"expected {expected_sequence}, got {event.sequence}"
            )
        expected_sequence += 1
        _apply_event(state, event)
    return state


def effect_total_tokens(result: EffectResult) -> int:
    """Return the normalized total-token contribution of one effect."""

    return int(result.usage.get("total_tokens", 0))


def _apply_event(state: ControlState, event: ControlEvent) -> None:
    payload = event.payload
    if event.event_type == "run_started":
        if state.run_id is not None:
            raise ValueError("Control journal contains multiple run_started events")
        state.run_id = _required_string(payload, "run_id")
        state.initial_version = _required_string(payload, "initial_version")
        state.current_version = state.initial_version
        state.generation = 1
        state.status = "running"
        state.status_reason = None
        return

    if state.run_id is None:
        raise ValueError("Control journal event appears before run_started")

    if event.event_type == "run_resumed":
        state.status = "running"
        state.status_reason = None
        return
    if event.event_type == "run_paused":
        state.status = "paused"
        state.status_reason = _required_string(payload, "reason")
        return
    if event.event_type == "run_completed":
        state.status = "completed"
        state.status_reason = _required_string(payload, "reason")
        return
    if event.event_type == "version_advanced":
        state.current_version = _required_string(payload, "version_id")
        state.generation = _positive_integer(payload.get("generation"), "generation")
        return
    if event.event_type == "work_scheduled":
        item = WorkItem.from_dict(_object(payload.get("work"), "work"))
        existing = state.works.get(item.work_id)
        if existing is not None:
            if existing.item != item:
                raise ValueError(
                    f"work_id was scheduled with different content: {item.work_id}"
                )
            return
        state.works[item.work_id] = WorkRecord(item=item)
        state.work_order.append(item.work_id)
        return

    work_id = _required_string(payload, "work_id")
    try:
        record = state.works[work_id]
    except KeyError as exc:
        raise ValueError(f"journal references unknown work_id: {work_id}") from exc

    if event.event_type == "work_started":
        if record.status != "queued":
            raise ValueError(
                f"work_started requires queued status: {work_id}={record.status}"
            )
        record.status = "running"
        return
    if event.event_type == "work_completed":
        if record.status not in {"running", "queued"}:
            raise ValueError(
                f"work_completed requires running/queued status: "
                f"{work_id}={record.status}"
            )
        record.status = "completed"
        record.result_ref = _required_string(payload, "result_ref")
        record.error = None
        state.completed_work_count += 1
        state.total_tokens += _non_negative_integer(
            payload.get("total_tokens", 0),
            "total_tokens",
        )
        return
    if event.event_type == "work_failed":
        if record.status not in {"running", "queued"}:
            raise ValueError(
                f"work_failed requires running/queued status: {work_id}={record.status}"
            )
        record.status = "failed"
        record.error = _required_string(payload, "error")
        state.total_tokens += _non_negative_integer(
            payload.get("total_tokens", 0),
            "total_tokens",
        )
        return
    if event.event_type == "work_transitioned":
        if record.status not in {"completed", "failed"}:
            raise ValueError(
                f"work_transitioned requires terminal work status: "
                f"{work_id}={record.status}"
            )
        state.transitioned_work_ids.add(work_id)
        return
    raise ValueError(f"unknown Control event type: {event.event_type}")


def _object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object")
    return dict(value)


def _string_mapping(value: object, field_name: str) -> dict[str, str]:
    raw = _object(value, field_name)
    result: dict[str, str] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise TypeError(f"{field_name} must map strings to strings")
        result[key] = item
    return result


def _required_string(value: dict[str, Any], field_name: str) -> str:
    item = value.get(field_name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{field_name} must be a non-empty string")
    return item


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError("optional string must be null or a non-empty string")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    result = _non_negative_integer(value, field_name)
    if result < 1:
        raise ValueError(f"{field_name} must be positive")
    return result


def _non_negative_integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value
