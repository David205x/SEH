"""Run bounded Hook-model feasibility probes over frozen semantic fixtures."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from search_harness.framework import (
    ChatMessage,
    HookModelBackend,
    HookModelRequest,
    ModelInput,
)

from .roles.contracts import DecisionLabel, MechanismDecisionContract


_LABELS: tuple[DecisionLabel, ...] = (
    "positive",
    "negative",
    "uncertain",
)
_MAX_FIXTURES_PER_LABEL = 2


@dataclass(frozen=True)
class HookEvaluatorFixture:
    """One case-neutral input with a Reviewer-owned expected label."""

    fixture_id: str
    expected_label: DecisionLabel
    input_payload: dict[str, Any]

    def __post_init__(self) -> None:
        fixture_id = self.fixture_id.strip()
        if not fixture_id:
            raise ValueError("hook evaluator fixture_id must not be empty")
        if self.expected_label not in _LABELS:
            raise ValueError(
                f"unsupported Hook evaluator label: {self.expected_label}"
            )
        object.__setattr__(self, "fixture_id", fixture_id)
        object.__setattr__(self, "input_payload", dict(self.input_payload))


@dataclass(frozen=True)
class HookEvaluatorProbeRequest:
    """Frozen decision contract and observed fixtures for one probe batch."""

    predicate_ref: str
    decision_contract: MechanismDecisionContract
    fixtures: tuple[HookEvaluatorFixture, ...]
    repetitions: int = 3
    profile: str = "student"

    def __post_init__(self) -> None:
        predicate_ref = self.predicate_ref.strip()
        profile = self.profile.strip().casefold()
        fixtures = tuple(self.fixtures)
        if not predicate_ref:
            raise ValueError("Hook evaluator predicate_ref must not be empty")
        if not profile:
            raise ValueError("Hook evaluator profile must not be empty")
        if not 1 <= self.repetitions <= 3:
            raise ValueError(
                "Hook evaluator repetitions must be between one and three"
            )
        fixture_ids = [fixture.fixture_id for fixture in fixtures]
        if not fixtures:
            raise ValueError("Hook evaluator probe requires fixtures")
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("Hook evaluator fixture IDs must be unique")
        covered_labels = {fixture.expected_label for fixture in fixtures}
        if not {"positive", "negative"} <= covered_labels:
            raise ValueError(
                "Hook evaluator fixtures must cover positive and negative "
                "labels; uncertain evidence is probed when observed"
            )
        object.__setattr__(self, "predicate_ref", predicate_ref)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "fixtures", fixtures)

    @classmethod
    def from_decision_contract(
        cls,
        *,
        predicate_ref: str,
        decision_contract: MechanismDecisionContract,
        repetitions: int = 3,
        profile: str = "student",
    ) -> "HookEvaluatorProbeRequest":
        """Project case-neutral observed decision evidence into fixtures."""

        evidence = decision_contract.evidence_coverage
        descriptions = {
            "positive": evidence.positive,
            "negative": evidence.negative,
            "uncertain": evidence.uncertain,
        }
        fixtures = tuple(
            HookEvaluatorFixture(
                fixture_id=f"{label}-{index:03d}",
                expected_label=label,
                input_payload={"observation": description},
            )
            for label in _LABELS
            for index, description in enumerate(
                descriptions[label][:_MAX_FIXTURES_PER_LABEL],
                start=1,
            )
        )
        return cls(
            predicate_ref=predicate_ref,
            decision_contract=decision_contract,
            fixtures=fixtures,
            repetitions=repetitions,
            profile=profile,
        )


@dataclass(frozen=True)
class HookEvaluatorProbeObservation:
    """One real Hook-model classification and its bounded diagnostics."""

    fixture_id: str
    repetition: int
    expected_label: DecisionLabel
    observed_label: DecisionLabel | None
    raw_output: str
    parse_error: str | None
    usage: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "repetition": self.repetition,
            "expected_label": self.expected_label,
            "observed_label": self.observed_label,
            "raw_output": self.raw_output,
            "parse_error": self.parse_error,
            "usage": dict(self.usage),
        }


@dataclass(frozen=True)
class HookEvaluatorProbeSummary:
    """Descriptive feasibility evidence without a program-owned pass gate."""

    predicate_ref: str
    profile: str
    repetitions: int
    fixture_summaries: tuple[dict[str, Any], ...]
    observations: tuple[HookEvaluatorProbeObservation, ...]
    label_match_rate: float
    consistent_fixture_count: int
    parse_failure_count: int
    usage: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "predicate_ref": self.predicate_ref,
            "profile": self.profile,
            "repetitions": self.repetitions,
            "fixture_summaries": [
                dict(summary) for summary in self.fixture_summaries
            ],
            "observations": [
                observation.to_dict() for observation in self.observations
            ],
            "label_match_rate": self.label_match_rate,
            "consistent_fixture_count": self.consistent_fixture_count,
            "parse_failure_count": self.parse_failure_count,
            "usage": dict(self.usage),
        }


def run_hook_evaluator_probe(
    *,
    request: HookEvaluatorProbeRequest,
    backend: HookModelBackend,
) -> HookEvaluatorProbeSummary:
    """Run every fixture repeatedly through the production Hook backend."""

    observations = []
    for fixture in request.fixtures:
        for repetition in range(request.repetitions):
            response = backend.generate(
                HookModelRequest(
                    profile=request.profile,
                    purpose=f"probe:{request.predicate_ref}",
                    model_input=_model_input(
                        request.decision_contract,
                        fixture.input_payload,
                    ),
                )
            )
            observed_label, parse_error = _parse_label(response.raw_output)
            observations.append(
                HookEvaluatorProbeObservation(
                    fixture_id=fixture.fixture_id,
                    repetition=repetition,
                    expected_label=fixture.expected_label,
                    observed_label=observed_label,
                    raw_output=response.raw_output,
                    parse_error=parse_error,
                    usage=_normalize_usage(response.metadata.get("usage")),
                )
            )

    fixture_summaries = tuple(
        _summarize_fixture(fixture, observations)
        for fixture in request.fixtures
    )
    parse_failure_count = sum(
        observation.parse_error is not None for observation in observations
    )
    matches = sum(
        observation.observed_label == observation.expected_label
        for observation in observations
    )
    usage = _sum_usage(observation.usage for observation in observations)
    return HookEvaluatorProbeSummary(
        predicate_ref=request.predicate_ref,
        profile=request.profile,
        repetitions=request.repetitions,
        fixture_summaries=fixture_summaries,
        observations=tuple(observations),
        label_match_rate=matches / len(observations),
        consistent_fixture_count=sum(
            bool(summary["consistent"]) for summary in fixture_summaries
        ),
        parse_failure_count=parse_failure_count,
        usage=usage,
    )


def _model_input(
    contract: MechanismDecisionContract,
    input_payload: dict[str, Any],
) -> ModelInput:
    system = (
        "You are a bounded semantic classifier. Evaluate only the supplied "
        "input against this frozen decision contract.\n"
        f"Predicate: {contract.predicate}\n"
        f"Positive: {contract.positive_rule}\n"
        f"Negative: {contract.negative_rule}\n"
        f"Uncertain: {contract.uncertain_rule}\n"
        'Return only one JSON object: {"label":"positive|negative|uncertain"}.'
    )
    return ModelInput.from_messages(
        [
            ChatMessage(role="system", content=system),
            ChatMessage(
                role="user",
                content=json.dumps(input_payload, ensure_ascii=False),
            ),
        ]
    )


def _parse_label(raw_output: str) -> tuple[DecisionLabel | None, str | None]:
    try:
        value = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"
    if not isinstance(value, dict):
        return None, "Hook evaluator output must be a JSON object"
    label = value.get("label")
    if label not in _LABELS:
        return None, "Hook evaluator label must be positive, negative, or uncertain"
    return label, None


def _summarize_fixture(
    fixture: HookEvaluatorFixture,
    observations: list[HookEvaluatorProbeObservation],
) -> dict[str, Any]:
    local = [
        observation
        for observation in observations
        if observation.fixture_id == fixture.fixture_id
    ]
    label_counts = Counter(
        observation.observed_label
        for observation in local
        if observation.observed_label is not None
    )
    parse_failures = sum(
        observation.parse_error is not None for observation in local
    )
    matches = sum(
        observation.observed_label == fixture.expected_label
        for observation in local
    )
    return {
        "fixture_id": fixture.fixture_id,
        "expected_label": fixture.expected_label,
        "observed_label_counts": dict(label_counts),
        "match_rate": matches / len(local),
        "consistent": parse_failures == 0 and len(label_counts) == 1,
        "parse_failure_count": parse_failures,
    }


def _normalize_usage(value: object) -> dict[str, int]:
    usage = value if isinstance(value, dict) else {}
    input_tokens = _integer(
        usage.get("prompt_tokens", usage.get("input_tokens", 0))
    )
    output_tokens = _integer(
        usage.get("completion_tokens", usage.get("output_tokens", 0))
    )
    total_tokens = _integer(usage.get("total_tokens", 0))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _sum_usage(values: Any) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for value in values:
        for key in totals:
            totals[key] += value[key]
    return totals


def _integer(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0
