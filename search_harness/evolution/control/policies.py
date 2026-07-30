"""Deterministic budgets and promotion gates for the Evolution Controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import ControlState, EvolutionControlConfig


@dataclass(frozen=True)
class PromotionDecision:
    """Auditable result of the non-model promotion gate."""

    passed: bool
    reasons: tuple[str, ...]
    accuracy_delta: float
    total_token_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "accuracy_delta": self.accuracy_delta,
            "total_token_ratio": self.total_token_ratio,
        }


def stop_reason(
    state: ControlState,
    config: EvolutionControlConfig,
) -> str | None:
    """Return a pause reason before starting another effect, if any."""

    started_count = sum(
        record.status in {"running", "completed", "failed"}
        for record in state.works.values()
    )
    if started_count >= config.max_work_items:
        return (
            f"work-item budget reached: "
            f"{started_count}/{config.max_work_items}"
        )
    if (
        config.max_total_tokens is not None
        and state.total_tokens >= config.max_total_tokens
    ):
        return (
            f"token budget reached: "
            f"{state.total_tokens}/{config.max_total_tokens}"
        )
    return None


def evaluate_promotion(
    *,
    reviewer_recommendation: str,
    incumbent_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    config: EvolutionControlConfig,
) -> PromotionDecision:
    """Combine the advisory review with explicit quality and cost gates."""

    incumbent_accuracy = _metric(
        incumbent_metrics,
        "answers",
        "accuracy",
    )
    candidate_accuracy = _metric(
        candidate_metrics,
        "answers",
        "accuracy",
    )
    accuracy_delta = candidate_accuracy - incumbent_accuracy

    incumbent_tokens = _metric(
        incumbent_metrics,
        "tokens",
        "total_tokens",
    )
    candidate_tokens = _metric(
        candidate_metrics,
        "tokens",
        "total_tokens",
    )
    token_ratio = (
        candidate_tokens / incumbent_tokens
        if incumbent_tokens > 0
        else None
    )

    reasons: list[str] = []
    if reviewer_recommendation != "accept":
        reasons.append(
            "Candidate Reviewer did not recommend acceptance"
        )
    if accuracy_delta < config.min_accuracy_delta:
        reasons.append(
            "accuracy delta is below the configured minimum: "
            f"{accuracy_delta:.6f} < {config.min_accuracy_delta:.6f}"
        )
    if config.max_total_token_ratio is not None:
        if token_ratio is None:
            reasons.append(
                "incumbent total token count is zero; cost ratio is undefined"
            )
        elif token_ratio > config.max_total_token_ratio:
            reasons.append(
                "candidate token ratio exceeds the configured maximum: "
                f"{token_ratio:.6f} > "
                f"{config.max_total_token_ratio:.6f}"
            )
    return PromotionDecision(
        passed=not reasons,
        reasons=tuple(reasons),
        accuracy_delta=accuracy_delta,
        total_token_ratio=token_ratio,
    )


def _metric(
    metrics: dict[str, Any],
    section: str,
    name: str,
) -> float:
    nested = metrics.get(section)
    if not isinstance(nested, dict):
        raise ValueError(f"evaluation metrics lack '{section}'")
    value = nested.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"evaluation metric '{section}.{name}' must be numeric"
        )
    return float(value)
