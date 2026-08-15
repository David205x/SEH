"""Task-independent records used by offline rollout evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class StaticDecision(str, Enum):
    """Result of the deterministic first evaluation layer."""

    PASS = "pass"
    NEEDS_TEACHER = "needs_teacher"
    AUTOMATIC_ZERO = "automatic_zero"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class StaticEvaluation:
    """Deterministic task-specific result before optional teacher judging."""

    decision: StaticDecision
    metrics: dict[str, float | int | bool | None] = field(default_factory=dict)
    reason: str | None = None


@dataclass(frozen=True)
class EvaluationCase:
    """Question, reference answer and prediction supplied to a task evaluator."""

    example_id: str
    question: str
    golden_answer: str | None
    predicted_answer: str | None


class TaskEvaluator(Protocol):
    """Domain-specific static checker and teacher-judging prompt adapter."""

    task_name: str

    def evaluate_static(self, case: EvaluationCase) -> StaticEvaluation:
        """Return a deterministic result for one prediction."""

    def build_teacher_prompt(self, case: EvaluationCase) -> str:
        """Return the user prompt for a binary semantic judge."""


@dataclass(frozen=True)
class TeacherJudgment:
    """One optional 0/1 decision issued by the configured teacher model."""

    score: int | None
    assessment: str | None = None
    raw_output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "assessment": self.assessment,
            "raw_output": self.raw_output,
            "error": self.error,
            "metadata": dict(self.metadata),
        }
