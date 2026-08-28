"""Deterministic domain objects for the evidence-driven Evolution Controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from search_harness.evolution.identifiers import (
    make_generation_id,
    make_logical_work_id,
    make_research_attempt_id,
    make_settlement_id,
    make_work_id,
    validate_identifier,
)


class WorkKind(str, Enum):
    """One bounded role invocation or deterministic control-plane effect."""

    EVALUATE_INCUMBENT = "evaluate_incumbent"
    ANALYZE_FAILURE = "analyze_failure"
    RESEARCH_HYPOTHESIS = "research_hypothesis"
    SELECT_TRIAL = "select_trial"
    EXECUTE_TRIAL = "execute_trial"
    REVIEW_EVIDENCE = "review_evidence"
    DISTILL_MECHANISM = "distill_mechanism"
    VERIFY_HOOK_FEASIBILITY = "verify_hook_feasibility"
    COMPILE_CANDIDATE = "compile_candidate"
    STAGE_CANDIDATE = "stage_candidate"
    VERIFY_CONFORMANCE = "verify_conformance"
    EVALUATE_CANDIDATE = "evaluate_candidate"
    REVIEW_CANDIDATE = "review_candidate"
    SUMMARIZE_CAPABILITY = "summarize_capability"
    SUMMARIZE_DIRECTION = "summarize_direction"
    PROMOTE_CANDIDATE = "promote_candidate"
    REJECT_CANDIDATE = "reject_candidate"


WorkStatus = Literal["queued", "running", "completed", "failed"]
RunStatus = Literal["new", "running", "paused", "completed"]


@dataclass(frozen=True)
class TrajectoryLineage:
    """Typed location of one work or outcome in a Controller Run."""

    run_id: str
    generation: int
    generation_id: str
    research_attempt: int
    research_attempt_id: str
    candidate_attempt_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.run_id, "run_id")
        validate_identifier(self.generation_id, "generation_id")
        validate_identifier(self.research_attempt_id, "research_attempt_id")
        _positive_integer(self.generation, "generation")
        _positive_integer(self.research_attempt, "research_attempt")
        expected_generation_id = make_generation_id(
            self.run_id,
            self.generation,
        )
        if self.generation_id != expected_generation_id:
            raise ValueError(
                "generation_id does not match run_id and generation: "
                f"{self.generation_id} != {expected_generation_id}"
            )
        expected_research_id = make_research_attempt_id(
            self.generation_id,
            self.research_attempt,
        )
        if self.research_attempt_id != expected_research_id:
            raise ValueError(
                "research_attempt_id does not match generation and attempt: "
                f"{self.research_attempt_id} != {expected_research_id}"
            )
        if self.candidate_attempt_id is not None:
            validate_identifier(
                self.candidate_attempt_id,
                "candidate_attempt_id",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generation": self.generation,
            "generation_id": self.generation_id,
            "research_attempt": self.research_attempt,
            "research_attempt_id": self.research_attempt_id,
            "candidate_attempt_id": self.candidate_attempt_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TrajectoryLineage":
        return cls(
            run_id=_required_string(value, "run_id"),
            generation=_positive_integer(value.get("generation"), "generation"),
            generation_id=_required_string(value, "generation_id"),
            research_attempt=_positive_integer(
                value.get("research_attempt"),
                "research_attempt",
            ),
            research_attempt_id=_required_string(value, "research_attempt_id"),
            candidate_attempt_id=_optional_string(
                value.get("candidate_attempt_id")
            ),
        )


@dataclass(frozen=True)
class WorkItem:
    """A durable, independently retryable unit selected from the run agenda."""

    work_id: str
    logical_work_id: str
    work_index: int
    kind: WorkKind
    subject_ref: str
    lineage: TrajectoryLineage
    input_refs: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    parent_work_id: str | None = None
    attempt: int = 1

    def __post_init__(self) -> None:
        validate_identifier(self.work_id, "work_id")
        validate_identifier(self.logical_work_id, "logical_work_id")
        _positive_integer(self.work_index, "work_index")
        if not self.subject_ref.strip():
            raise ValueError("subject_ref must not be empty")
        _positive_integer(self.attempt, "attempt")
        expected_logical = make_logical_work_id(
            self.lineage.research_attempt_id,
            self.work_index,
            self.kind.value,
        )
        if self.logical_work_id != expected_logical:
            raise ValueError(
                "logical_work_id does not match lineage, work_index, and kind: "
                f"{self.logical_work_id} != {expected_logical}"
            )
        expected_work = make_work_id(self.logical_work_id, self.attempt)
        if self.work_id != expected_work:
            raise ValueError(
                "work_id does not match logical_work_id and attempt: "
                f"{self.work_id} != {expected_work}"
            )
        if self.parent_work_id is not None:
            validate_identifier(self.parent_work_id, "parent_work_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "logical_work_id": self.logical_work_id,
            "work_index": self.work_index,
            "kind": self.kind.value,
            "subject_ref": self.subject_ref,
            "lineage": self.lineage.to_dict(),
            "input_refs": dict(self.input_refs),
            "payload": dict(self.payload),
            "parent_work_id": self.parent_work_id,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorkItem":
        return cls(
            work_id=_required_string(value, "work_id"),
            logical_work_id=_required_string(value, "logical_work_id"),
            work_index=_positive_integer(value.get("work_index"), "work_index"),
            kind=WorkKind(_required_string(value, "kind")),
            subject_ref=_required_string(value, "subject_ref"),
            lineage=TrajectoryLineage.from_dict(
                _object(value.get("lineage"), "lineage")
            ),
            input_refs=_string_mapping(value.get("input_refs", {}), "input_refs"),
            payload=_object(value.get("payload", {}), "payload"),
            parent_work_id=_optional_string(value.get("parent_work_id")),
            attempt=_positive_integer(value.get("attempt"), "attempt"),
        )


@dataclass
class WorkRecord:
    """Projected execution status for one immutable WorkItem."""

    item: WorkItem
    status: WorkStatus = "queued"
    result_ref: str | None = None
    error: str | None = None
    failure_artifact: str | None = None
    failure_stage: str | None = None
    terminal_event_sequence: int | None = None


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


class SettlementClass(str, Enum):
    """Durable outcome classification at one lifecycle boundary."""

    SETTLED_POSITIVE = "settled_positive"
    SETTLED_NEGATIVE = "settled_negative"
    INVALID_INDETERMINATE = "invalid_indeterminate"


class SettlementScope(str, Enum):
    """Lifecycle object closed by one settlement."""

    CANDIDATE_ATTEMPT = "candidate_attempt"
    RESEARCH_ATTEMPT = "research_attempt"
    WORK_ATTEMPT = "work_attempt"


@dataclass(frozen=True)
class SettlementDraft:
    """Transition-produced settlement facts awaiting durable source binding."""

    scope: SettlementScope
    classification: SettlementClass
    terminal_code: str
    verdict: str
    candidate_attempt_id: str | None = None
    revision_owner: str | None = None
    revision_obligation: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.terminal_code, "terminal_code")
        if not self.verdict.strip():
            raise ValueError("settlement verdict must not be empty")
        if self.candidate_attempt_id is not None:
            validate_identifier(
                self.candidate_attempt_id,
                "candidate_attempt_id",
            )
        if self.scope is SettlementScope.CANDIDATE_ATTEMPT:
            if self.candidate_attempt_id is None:
                raise ValueError(
                    "candidate_attempt settlement requires candidate_attempt_id"
                )
        elif self.candidate_attempt_id is not None:
            raise ValueError(
                "candidate_attempt_id is only valid for candidate settlements"
            )
        if (self.revision_owner is None) != (self.revision_obligation is None):
            raise ValueError(
                "revision_owner and revision_obligation must be set together"
            )


@dataclass(frozen=True)
class OutcomeSource:
    """Durable event, work, verdict, and artifact source of a settlement."""

    event_sequence: int
    work_id: str
    logical_work_id: str
    work_kind: WorkKind
    verdict: str
    result_ref: str | None = None
    artifact_refs: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        _positive_integer(self.event_sequence, "event_sequence")
        validate_identifier(self.work_id, "work_id")
        validate_identifier(self.logical_work_id, "logical_work_id")
        if not self.verdict.strip():
            raise ValueError("verdict must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_sequence": self.event_sequence,
            "work_id": self.work_id,
            "logical_work_id": self.logical_work_id,
            "work_kind": self.work_kind.value,
            "verdict": self.verdict,
            "result_ref": self.result_ref,
            "artifact_refs": dict(self.artifact_refs),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OutcomeSource":
        return cls(
            event_sequence=_positive_integer(
                value.get("event_sequence"),
                "event_sequence",
            ),
            work_id=_required_string(value, "work_id"),
            logical_work_id=_required_string(value, "logical_work_id"),
            work_kind=WorkKind(_required_string(value, "work_kind")),
            verdict=_required_string(value, "verdict"),
            result_ref=_optional_string(value.get("result_ref")),
            artifact_refs=_string_mapping(
                value.get("artifact_refs", {}),
                "artifact_refs",
            ),
            error=_optional_string(value.get("error")),
        )


@dataclass(frozen=True)
class TrajectorySettlement:
    """Append-only typed closure of one lifecycle object."""

    settlement_id: str
    scope: SettlementScope
    classification: SettlementClass
    terminal_code: str
    lineage: TrajectoryLineage
    source: OutcomeSource
    revision_owner: str | None = None
    revision_obligation: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.settlement_id, "settlement_id")
        validate_identifier(self.terminal_code, "terminal_code")
        if (self.revision_owner is None) != (self.revision_obligation is None):
            raise ValueError(
                "revision_owner and revision_obligation must be set together"
            )
        expected = make_settlement_id(self.target_id, self.terminal_code)
        if self.settlement_id != expected:
            raise ValueError(
                "settlement_id does not match typed target and terminal_code: "
                f"{self.settlement_id} != {expected}"
            )

    @property
    def target_id(self) -> str:
        """Return the typed target without parsing settlement_id."""

        if self.scope is SettlementScope.CANDIDATE_ATTEMPT:
            candidate_attempt_id = self.lineage.candidate_attempt_id
            if candidate_attempt_id is None:
                raise ValueError(
                    "candidate_attempt settlement requires lineage candidate ID"
                )
            return candidate_attempt_id
        if self.scope is SettlementScope.RESEARCH_ATTEMPT:
            return self.lineage.research_attempt_id
        return self.source.work_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "settlement_id": self.settlement_id,
            "settlement_scope": self.scope.value,
            "classification": self.classification.value,
            "terminal_code": self.terminal_code,
            "lineage": self.lineage.to_dict(),
            "source": self.source.to_dict(),
            "revision_owner": self.revision_owner,
            "revision_obligation": self.revision_obligation,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TrajectorySettlement":
        return cls(
            settlement_id=_required_string(value, "settlement_id"),
            scope=SettlementScope(
                _required_string(value, "settlement_scope")
            ),
            classification=SettlementClass(
                _required_string(value, "classification")
            ),
            terminal_code=_required_string(value, "terminal_code"),
            lineage=TrajectoryLineage.from_dict(
                _object(value.get("lineage"), "lineage")
            ),
            source=OutcomeSource.from_dict(
                _object(value.get("source"), "source")
            ),
            revision_owner=_optional_string(value.get("revision_owner")),
            revision_obligation=_optional_string(
                value.get("revision_obligation")
            ),
        )


def materialize_settlement(
    *,
    draft: SettlementDraft,
    item: WorkItem,
    event_sequence: int,
    result_ref: str | None,
    artifact_refs: dict[str, str],
    error: str | None,
) -> TrajectorySettlement:
    """Bind one transition draft to the persisted terminal work event."""

    lineage = item.lineage
    if draft.candidate_attempt_id is not None:
        lineage = TrajectoryLineage(
            run_id=lineage.run_id,
            generation=lineage.generation,
            generation_id=lineage.generation_id,
            research_attempt=lineage.research_attempt,
            research_attempt_id=lineage.research_attempt_id,
            candidate_attempt_id=draft.candidate_attempt_id,
        )
    source = OutcomeSource(
        event_sequence=event_sequence,
        work_id=item.work_id,
        logical_work_id=item.logical_work_id,
        work_kind=item.kind,
        verdict=draft.verdict,
        result_ref=result_ref,
        artifact_refs=dict(artifact_refs),
        error=error,
    )
    if draft.scope is SettlementScope.CANDIDATE_ATTEMPT:
        target_id = lineage.candidate_attempt_id
        if target_id is None:
            raise ValueError(
                "candidate settlement lacks a candidate_attempt_id"
            )
    elif draft.scope is SettlementScope.RESEARCH_ATTEMPT:
        target_id = lineage.research_attempt_id
    else:
        target_id = source.work_id
    return TrajectorySettlement(
        settlement_id=make_settlement_id(target_id, draft.terminal_code),
        scope=draft.scope,
        classification=draft.classification,
        terminal_code=draft.terminal_code,
        lineage=lineage,
        source=source,
        revision_owner=draft.revision_owner,
        revision_obligation=draft.revision_obligation,
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
    generation_id: str | None = None
    works: dict[str, WorkRecord] = field(default_factory=dict)
    work_order: list[str] = field(default_factory=list)
    transitioned_work_ids: set[str] = field(default_factory=set)
    settlements: dict[str, TrajectorySettlement] = field(default_factory=dict)
    settlement_order: list[str] = field(default_factory=list)
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
    trial_batch_size: int = 3
    max_trial_assignments: int = 12
    max_hypothesis_revisions: int = 2
    max_mechanism_revisions: int = 2
    max_compiler_revisions: int = 2
    max_candidate_revisions: int = 2
    max_work_retries: int = 1
    max_work_items: int = 80
    max_total_tokens: int | None = None
    min_accuracy_delta: float = -0.02
    task_outcome_min_accuracy_delta: float = 0.0
    task_outcome_min_attributed_beneficial_examples: int = 1
    task_outcome_max_attributed_harmful_examples: int = 0
    behavioral_min_accuracy_delta: float = -0.02
    behavioral_min_target_behavior_examples: int = 2
    behavioral_max_attributed_harmful_examples: int = 0
    max_total_token_ratio: float | None = 3.0

    def __post_init__(self) -> None:
        positive = {
            "max_generations": self.max_generations,
            "max_trials_per_hypothesis": self.max_trials_per_hypothesis,
            "trial_batch_size": self.trial_batch_size,
            "max_trial_assignments": self.max_trial_assignments,
            "max_work_items": self.max_work_items,
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.trial_batch_size > self.max_trials_per_hypothesis:
            raise ValueError(
                "trial_batch_size must not exceed "
                "max_trials_per_hypothesis"
            )
        non_negative = {
            "max_hypothesis_revisions": self.max_hypothesis_revisions,
            "max_mechanism_revisions": self.max_mechanism_revisions,
            "max_compiler_revisions": self.max_compiler_revisions,
            "max_candidate_revisions": self.max_candidate_revisions,
            "max_work_retries": self.max_work_retries,
            "task_outcome_min_attributed_beneficial_examples": (
                self.task_outcome_min_attributed_beneficial_examples
            ),
            "task_outcome_max_attributed_harmful_examples": (
                self.task_outcome_max_attributed_harmful_examples
            ),
            "behavioral_min_target_behavior_examples": (
                self.behavioral_min_target_behavior_examples
            ),
            "behavioral_max_attributed_harmful_examples": (
                self.behavioral_max_attributed_harmful_examples
            ),
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
        accuracy_floors = {
            "min_accuracy_delta": self.min_accuracy_delta,
            "task_outcome_min_accuracy_delta": (
                self.task_outcome_min_accuracy_delta
            ),
            "behavioral_min_accuracy_delta": (
                self.behavioral_min_accuracy_delta
            ),
        }
        for name, value in accuracy_floors.items():
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between -1 and 1")


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
        validate_identifier(state.run_id, "run_id")
        state.initial_version = _required_string(payload, "initial_version")
        state.current_version = state.initial_version
        state.generation = _positive_integer(
            payload.get("generation"),
            "generation",
        )
        state.generation_id = _required_string(payload, "generation_id")
        validate_identifier(state.generation_id, "generation_id")
        if state.generation_id != make_generation_id(
            state.run_id,
            state.generation,
        ):
            raise ValueError("run_started generation_id is inconsistent")
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
        state.generation_id = _required_string(payload, "generation_id")
        validate_identifier(state.generation_id, "generation_id")
        if state.generation_id != make_generation_id(
            state.run_id,
            state.generation,
        ):
            raise ValueError("version_advanced generation_id is inconsistent")
        return
    if event.event_type == "work_scheduled":
        item = WorkItem.from_dict(_object(payload.get("work"), "work"))
        if item.lineage.run_id != state.run_id:
            raise ValueError("scheduled work lineage run_id does not match run")
        if item.lineage.generation_id != state.generation_id:
            raise ValueError(
                "scheduled work lineage generation_id does not match state"
            )
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
    if event.event_type == "trajectory_settled":
        settlement = TrajectorySettlement.from_dict(
            _object(payload.get("settlement"), "settlement")
        )
        if settlement.lineage.run_id != state.run_id:
            raise ValueError(
                "trajectory_settled lineage run_id does not match journal run"
            )
        source_work_id = settlement.source.work_id
        source_record = state.works.get(source_work_id)
        if source_record is None:
            raise ValueError(
                "trajectory_settled references unknown source work: "
                f"{source_work_id}"
            )
        if source_record.status not in {"completed", "failed"}:
            raise ValueError(
                "trajectory_settled requires terminal source work: "
                f"{source_work_id}={source_record.status}"
            )
        if (
            source_record.terminal_event_sequence
            != settlement.source.event_sequence
        ):
            raise ValueError(
                "trajectory_settled source event does not match terminal work "
                f"event: {source_work_id}"
            )
        existing = state.settlements.get(settlement.settlement_id)
        if existing is not None:
            if existing != settlement:
                raise ValueError(
                    "settlement_id was replayed with different content: "
                    f"{settlement.settlement_id}"
                )
            return
        state.settlements[settlement.settlement_id] = settlement
        state.settlement_order.append(settlement.settlement_id)
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
        record.failure_artifact = None
        record.failure_stage = None
        record.terminal_event_sequence = event.sequence
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
        record.failure_artifact = _optional_string(
            payload.get("failure_artifact")
        )
        record.failure_stage = _optional_string(payload.get("failure_stage"))
        record.terminal_event_sequence = event.sequence
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
