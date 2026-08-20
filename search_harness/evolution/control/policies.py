"""Deterministic budgets and promotion gates for the Evolution Controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import ControlState, EvolutionControlConfig


@dataclass(frozen=True)
class PromotionDecision:
    """Auditable result of deterministic safety and model effect gates."""

    passed: bool
    safety_passed: bool
    effect_passed: bool
    reasons: tuple[str, ...]
    safety_reasons: tuple[str, ...]
    reviewer_recommendation: str
    accuracy_delta: float | None
    total_token_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "safety_gate": {
                "passed": self.safety_passed,
                "reasons": list(self.safety_reasons),
            },
            "effect_gate": {
                "passed": self.effect_passed,
                "reviewer_recommendation": self.reviewer_recommendation,
            },
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
    validation_summary: dict[str, Any],
    incumbent_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    config: EvolutionControlConfig,
    effect_goal: str = "task_outcome",
    effect_summary: dict[str, Any] | None = None,
) -> PromotionDecision:
    """Combine a deterministic safety gate with the Reviewer effect gate."""

    incumbent_accuracy = _optional_metric(
        incumbent_metrics,
        "answers",
        "accuracy",
    )
    candidate_accuracy = _optional_metric(
        candidate_metrics,
        "answers",
        "accuracy",
    )
    accuracy_delta = (
        candidate_accuracy - incumbent_accuracy
        if incumbent_accuracy is not None and candidate_accuracy is not None
        else None
    )

    incumbent_tokens = _optional_metric(
        incumbent_metrics,
        "tokens",
        "total_tokens",
    )
    candidate_tokens = _optional_metric(
        candidate_metrics,
        "tokens",
        "total_tokens",
    )
    token_ratio = (
        candidate_tokens / incumbent_tokens
        if (
            candidate_tokens is not None
            and incumbent_tokens is not None
            and incumbent_tokens > 0
        )
        else None
    )

    safety_reasons: list[str] = []
    if validation_summary.get("passed") is not True:
        safety_reasons.append("candidate validation did not pass")
    runner_errors = _runner_error_count(candidate_metrics)
    if runner_errors is None:
        safety_reasons.append(
            "candidate execution status metrics are unavailable"
        )
    elif runner_errors > 0:
        safety_reasons.append(
            f"candidate execution contains runner errors: {runner_errors}"
        )
    if incumbent_accuracy is None:
        safety_reasons.append("incumbent accuracy is unavailable")
    if candidate_accuracy is None:
        safety_reasons.append("candidate accuracy is unavailable")
    accuracy_floor = (
        config.min_accuracy_delta
        if effect_summary is None
        else config.task_outcome_min_accuracy_delta
        if effect_goal == "task_outcome"
        else config.behavioral_min_accuracy_delta
        if effect_goal == "behavioral_intermediate"
        else None
    )
    if accuracy_floor is None:
        safety_reasons.append(f"unknown mechanism effect_goal: {effect_goal}")
    elif accuracy_delta is not None and accuracy_delta < accuracy_floor:
        safety_reasons.append(
            "accuracy regression exceeds the configured safety limit: "
            f"{accuracy_delta:.6f} < {accuracy_floor:.6f}"
        )
    if effect_summary is not None:
        beneficial = _non_negative_summary_count(
            effect_summary,
            "attributed_beneficial_example_count",
        )
        harmful = _non_negative_summary_count(
            effect_summary,
            "attributed_harmful_example_count",
        )
        target = _non_negative_summary_count(
            effect_summary,
            "target_behavior_example_count",
        )
        if effect_goal == "task_outcome":
            if beneficial < (
                config.task_outcome_min_attributed_beneficial_examples
            ):
                safety_reasons.append(
                    "attributable beneficial example count is below the "
                    "task-outcome minimum: "
                    f"{beneficial} < "
                    f"{config.task_outcome_min_attributed_beneficial_examples}"
                )
            if harmful > config.task_outcome_max_attributed_harmful_examples:
                safety_reasons.append(
                    "attributable harmful example count exceeds the "
                    "task-outcome maximum: "
                    f"{harmful} > "
                    f"{config.task_outcome_max_attributed_harmful_examples}"
                )
        elif effect_goal == "behavioral_intermediate":
            if target < config.behavioral_min_target_behavior_examples:
                safety_reasons.append(
                    "target behavior example count is below the behavioral "
                    f"minimum: {target} < "
                    f"{config.behavioral_min_target_behavior_examples}"
                )
            if harmful > config.behavioral_max_attributed_harmful_examples:
                safety_reasons.append(
                    "attributable harmful example count exceeds the "
                    "behavioral maximum: "
                    f"{harmful} > "
                    f"{config.behavioral_max_attributed_harmful_examples}"
                )
    if config.max_total_token_ratio is not None:
        if incumbent_tokens is None:
            safety_reasons.append(
                "incumbent total token count is unavailable"
            )
        elif candidate_tokens is None:
            safety_reasons.append(
                "candidate total token count is unavailable"
            )
        elif incumbent_tokens <= 0:
            safety_reasons.append(
                "incumbent total token count is zero; cost ratio is undefined"
            )
        elif (
            token_ratio is not None
            and token_ratio > config.max_total_token_ratio
        ):
            safety_reasons.append(
                "candidate token ratio exceeds the configured maximum: "
                f"{token_ratio:.6f} > "
                f"{config.max_total_token_ratio:.6f}"
            )
    effect_passed = reviewer_recommendation == "accept"
    reasons = list(safety_reasons)
    if not effect_passed:
        reasons.append("Candidate Reviewer did not recommend acceptance")
    return PromotionDecision(
        passed=not reasons,
        safety_passed=not safety_reasons,
        effect_passed=effect_passed,
        reasons=tuple(reasons),
        safety_reasons=tuple(safety_reasons),
        reviewer_recommendation=reviewer_recommendation,
        accuracy_delta=accuracy_delta,
        total_token_ratio=token_ratio,
    )


def _non_negative_summary_count(
    summary: dict[str, Any],
    name: str,
) -> int:
    value = summary.get(name, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _optional_metric(
    metrics: dict[str, Any],
    section: str,
    name: str,
) -> float | None:
    nested = metrics.get(section)
    if not isinstance(nested, dict):
        return None
    value = nested.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)


def _runner_error_count(metrics: dict[str, Any]) -> int | None:
    execution = metrics.get("execution")
    if not isinstance(execution, dict):
        return None
    counts = execution.get("status_counts")
    if not isinstance(counts, dict):
        return None
    value = counts.get("runner_error", 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value
