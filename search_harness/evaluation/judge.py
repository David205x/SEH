"""Strict binary teacher judge used only after static evaluation is inconclusive."""

from __future__ import annotations

import json
from pathlib import Path

from search_harness.framework import ChatMessage, ModelInput
from search_harness.framework.agent import ModelResponse
from search_harness.integrations.openai_compatible import OpenAICompatibleModel
from search_harness.integrations.openai_compatible import OpenAICompatibleConfig
from search_harness._internal import (
    read_runtime_config,
    teacher_judge_thinking_mode,
)

from .types import EvaluationCase, TaskEvaluator, TeacherJudgment


_SYSTEM_PROMPT = """You are a precise offline evaluator.
Return exactly one JSON object with no markdown using this schema:
{"score": 0 or 1, "assessment": "one or two concise sentences"}
Score 1 means accepted/correct; score 0 means rejected/incorrect. The score and
assessment conclusion must agree.
The assessment must state the decisive scoring basis, contain no hidden reasoning,
and be no longer than 240 characters."""


class TeacherBinaryJudge:
    """Call a teacher model without exposing Student trajectories or harness internals."""

    def __init__(self, model: OpenAICompatibleModel, task_evaluator: TaskEvaluator) -> None:
        self._model = model
        self._task_evaluator = task_evaluator

    def judge(self, case: EvaluationCase) -> TeacherJudgment:
        model_input = ModelInput.from_messages(
            [
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=(
                        self._task_evaluator.build_teacher_prompt(case)
                        + "\n\nReturn the score-and-assessment object specified by "
                        "the system message. Before responding, ensure the numeric "
                        "score agrees with the assessment."
                    ),
                ),
            ]
        )
        try:
            response = self._model.generate(model_input)
        except Exception as exc:
            return TeacherJudgment(score=None, error=f"{type(exc).__name__}: {exc}")

        raw_output = response.raw_output
        try:
            score, assessment = _parse_judgment(raw_output)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return TeacherJudgment(
                score=None,
                raw_output=raw_output,
                error=str(exc),
                metadata=_response_metadata(response),
            )
        return TeacherJudgment(
            score=score,
            assessment=assessment,
            raw_output=raw_output,
            metadata=_response_metadata(response),
        )


def build_teacher_judge_model(
    *,
    env_file: Path | None,
    model_role: str = "teacher",
) -> OpenAICompatibleModel:
    """Build the evaluation Judge with its dedicated reasoning setting."""

    config = OpenAICompatibleConfig.from_env(
        env_file=env_file,
        prefix=model_role,
    )
    thinking_mode = teacher_judge_thinking_mode(
        read_runtime_config(env_file=env_file),
        default=config.configured_thinking_mode,
    )
    return OpenAICompatibleModel(
        config.with_configured_thinking_mode(thinking_mode)
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
