"""Strict binary teacher judge used only after static evaluation is inconclusive."""

from __future__ import annotations

import json
import re
from dataclasses import replace
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


_SCORE_PATTERN = re.compile(r"\{\s*\"score\"\s*:\s*([01])\s*\}")
_SYSTEM_PROMPT = "You are a precise offline evaluator. Follow the requested JSON format exactly."


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
                        + "\n\nReturn exactly one JSON object with no markdown: "
                        '{"score": 0} or {"score": 1}.'
                    ),
                ),
            ]
        )
        try:
            response = self._model.generate(model_input)
        except Exception as exc:
            return TeacherJudgment(score=None, error=f"{type(exc).__name__}: {exc}")

        raw_output = response.raw_output
        score = _parse_score(raw_output)
        if score is None:
            return TeacherJudgment(
                score=None,
                raw_output=raw_output,
                error="teacher output did not contain an exact binary score JSON object",
                metadata=_response_metadata(response),
            )
        return TeacherJudgment(
            score=score,
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
        default=config.thinking_mode,
    )
    return OpenAICompatibleModel(
        replace(
            config,
            thinking_mode=(
                thinking_mode
                if config.thinking_mode is not None
                else None
            ),
        )
    )


def _parse_score(raw_output: str) -> int | None:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        match = _SCORE_PATTERN.search(raw_output)
        return int(match.group(1)) if match else None
    score = payload.get("score") if isinstance(payload, dict) else None
    return score if score in {0, 1} else None


def _response_metadata(response: ModelResponse) -> dict[str, object]:
    metadata = dict(response.metadata)
    if response.usage:
        metadata["usage"] = dict(response.usage)
    return metadata
