"""Shadow score-and-assessment Teacher Judge for focused probes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from search_harness.evaluation.types import EvaluationCase, TaskEvaluator
from search_harness.framework import ChatMessage, ModelInput
from search_harness.framework.agent import ModelResponse
from search_harness.integrations.openai_compatible import OpenAICompatibleModel


_SYSTEM_PROMPT = """You are a precise offline evaluator.
Return exactly one JSON object with no markdown using this schema:
{"score": 0 or 1, "assessment": "one or two concise sentences"}
Score 1 means accepted/correct; score 0 means rejected/incorrect. The score and
assessment conclusion must agree.
The assessment must state the decisive scoring basis, contain no hidden reasoning,
and be no longer than 240 characters."""


@dataclass(frozen=True)
class ShadowTeacherJudgment:
    """Shadow semantic judgment with complete provider evidence retained."""

    score: int | None
    assessment: str | None
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


class ShadowTeacherBinaryJudge:
    """Exercise the proposed Judge contract without changing evaluation code."""

    def __init__(
        self,
        model: OpenAICompatibleModel,
        task_evaluator: TaskEvaluator,
    ) -> None:
        self._model = model
        self._task_evaluator = task_evaluator

    def judge(self, case: EvaluationCase) -> ShadowTeacherJudgment:
        prompt = self._task_evaluator.build_teacher_prompt(case)
        prompt += (
            "\n\nReturn the score-and-assessment object specified by the system message. "
            "Before responding, ensure the numeric score agrees with the assessment."
        )
        model_input = ModelInput.from_messages(
            [
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ]
        )
        try:
            response = self._model.generate(model_input)
        except Exception as exc:
            return ShadowTeacherJudgment(
                score=None,
                assessment=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        raw_output = response.raw_output
        try:
            score, assessment = _parse_judgment(raw_output)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return ShadowTeacherJudgment(
                score=None,
                assessment=None,
                raw_output=raw_output,
                error=str(exc),
                metadata=_response_metadata(response),
            )
        return ShadowTeacherJudgment(
            score=score,
            assessment=assessment,
            raw_output=raw_output,
            metadata=_response_metadata(response),
        )


def _parse_judgment(raw_output: str) -> tuple[int, str]:
    payload = json.loads(raw_output)
    if not isinstance(payload, dict):
        raise TypeError("Teacher output must be one JSON object")
    if set(payload) != {"score", "assessment"}:
        raise ValueError("Teacher output must contain only score and assessment")
    score = payload.get("score")
    if score not in {0, 1}:
        raise ValueError("Teacher score must be 0 or 1")
    assessment = payload.get("assessment")
    if not isinstance(assessment, str) or not assessment.strip():
        raise ValueError("Teacher assessment must be a non-empty string")
    assessment = assessment.strip()
    if len(assessment) > 240:
        raise ValueError("Teacher assessment exceeds 240 characters")
    return score, assessment


def _response_metadata(response: ModelResponse) -> dict[str, object]:
    metadata = dict(response.metadata)
    if response.usage:
        metadata["usage"] = dict(response.usage)
    return metadata
