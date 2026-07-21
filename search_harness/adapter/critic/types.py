"""Stable result contracts for the Critic role."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ReviewDecision = Literal["accept", "reject"]

CRITIC_RESULT_FIELDS = frozenset(
    {"analysis", "problem_directions", "evidence_requests", "review"}
)
REQUIRED_DIRECTION_FIELDS = frozenset(
    {
        "problem",
        "observed_pattern",
        "excluded_causes",
        "desired_behavior",
        "success_criteria",
        "constraints",
    }
)


@dataclass(frozen=True)
class CriticReview:
    """Critic 对一个候选 Harness 的语义验收结论。"""

    decision: ReviewDecision
    reason: str

    def __post_init__(self) -> None:
        if self.decision not in {"accept", "reject"}:
            raise ValueError("critic review decision must be accept or reject")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("critic review reason must be a non-empty string")
        object.__setattr__(self, "reason", self.reason.strip())

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CriticReview":
        _require_exact_fields(payload, {"decision", "reason"}, "critic review")
        decision = payload.get("decision")
        reason = payload.get("reason")
        if decision not in {"accept", "reject"}:
            raise ValueError("critic review decision must be accept or reject")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("critic review reason must be a non-empty string")
        return cls(decision=decision, reason=reason.strip())

    def to_dict(self) -> dict[str, str]:
        return {"decision": self.decision, "reason": self.reason}


@dataclass(frozen=True)
class CriticResult:
    """One Critic analysis with problem directions and optional review."""

    analysis: str
    problem_directions: tuple[dict[str, Any], ...] = ()
    evidence_requests: tuple[str, ...] = ()
    review: CriticReview | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.analysis, str) or not self.analysis.strip():
            raise ValueError("critic result analysis must be a non-empty string")
        normalized_directions = tuple(
            validate_problem_direction(dict(item), index=index)
            for index, item in enumerate(self.problem_directions)
        )
        normalized_requests = tuple(
            _non_empty_string(item, f"critic evidence_requests[{index}]")
            for index, item in enumerate(self.evidence_requests)
        )
        if self.review is not None and not isinstance(self.review, CriticReview):
            raise TypeError("critic result review must be CriticReview or None")
        object.__setattr__(self, "analysis", self.analysis.strip())
        object.__setattr__(self, "problem_directions", normalized_directions)
        object.__setattr__(self, "evidence_requests", normalized_requests)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CriticResult":
        missing = CRITIC_RESULT_FIELDS - set(payload)
        if missing:
            raise ValueError(f"critic result lacks required fields: {sorted(missing)}")
        unknown = set(payload) - CRITIC_RESULT_FIELDS
        if unknown:
            raise ValueError(f"critic result has unsupported fields: {sorted(unknown)}")
        analysis = payload.get("analysis")
        problem_directions = payload.get("problem_directions")
        evidence_requests = payload.get("evidence_requests")
        raw_review = payload.get("review")
        if not isinstance(analysis, str) or not analysis.strip():
            raise ValueError("critic result analysis must be a non-empty string")
        if not isinstance(problem_directions, list) or not all(
            isinstance(item, dict) for item in problem_directions
        ):
            raise ValueError(
                "critic result problem_directions must be an array of objects"
            )
        if not isinstance(evidence_requests, list) or not all(
            isinstance(item, str) for item in evidence_requests
        ):
            raise ValueError("critic result evidence_requests must be an array of strings")
        if raw_review is not None and not isinstance(raw_review, dict):
            raise ValueError("critic result review must be an object or null")
        return cls(
            analysis=analysis.strip(),
            problem_directions=tuple(
                validate_problem_direction(item, index=index)
                for index, item in enumerate(problem_directions)
            ),
            evidence_requests=tuple(
                _non_empty_string(item, f"critic evidence_requests[{index}]")
                for index, item in enumerate(evidence_requests)
            ),
            review=CriticReview.from_dict(raw_review) if raw_review is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis,
            "problem_directions": [
                dict(direction) for direction in self.problem_directions
            ],
            "evidence_requests": list(self.evidence_requests),
            "review": self.review.to_dict() if self.review is not None else None,
        }


def validate_problem_direction(
    payload: dict[str, Any], *, index: int
) -> dict[str, Any]:
    """Validate and normalize one behavioral problem direction."""

    missing = REQUIRED_DIRECTION_FIELDS - set(payload)
    if missing:
        raise ValueError(
            f"Critic problem direction {index} lacks required evidence: {sorted(missing)}"
        )
    unknown = set(payload) - REQUIRED_DIRECTION_FIELDS
    if unknown:
        raise ValueError(
            f"Critic problem direction {index} has unsupported fields: {sorted(unknown)}"
        )
    return {
        "problem": _non_empty_string(
            payload["problem"], f"problem direction {index}.problem"
        ),
        "observed_pattern": _non_empty_string(
            payload["observed_pattern"],
            f"problem direction {index}.observed_pattern",
        ),
        "excluded_causes": _string_array(
            payload["excluded_causes"],
            f"problem direction {index}.excluded_causes",
        ),
        "desired_behavior": _non_empty_string(
            payload["desired_behavior"],
            f"problem direction {index}.desired_behavior",
        ),
        "success_criteria": _string_array(
            payload["success_criteria"],
            f"problem direction {index}.success_criteria",
        ),
        "constraints": _string_array(
            payload["constraints"], f"problem direction {index}.constraints"
        ),
    }


def _string_array(value: object, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array of strings")
    return [
        _non_empty_string(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_exact_fields(
    payload: dict[str, Any], expected: set[str], path: str
) -> None:
    missing = expected - set(payload)
    if missing:
        raise ValueError(f"{path} lacks required fields: {sorted(missing)}")
    unknown = set(payload) - expected
    if unknown:
        raise ValueError(f"{path} has unsupported fields: {sorted(unknown)}")
