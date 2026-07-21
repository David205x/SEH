"""Strict binary teacher judge used only after static evaluation is inconclusive."""

from __future__ import annotations

import json
import re

from search_harness.core import ChatMessage, ModelInput
from search_harness.models import OpenAICompatibleTextModel

from .types import EvaluationCase, TaskEvaluator, TeacherJudgment


_SCORE_PATTERN = re.compile(r"\{\s*\"score\"\s*:\s*([01])\s*\}")
_SYSTEM_PROMPT = "You are a precise offline evaluator. Follow the requested JSON format exactly."


class TeacherBinaryJudge:
    """Call a teacher model without exposing actor traces or harness internals."""

    def __init__(self, model: OpenAICompatibleTextModel, task_evaluator: TaskEvaluator) -> None:
        self._model = model
        self._task_evaluator = task_evaluator

    def judge(self, case: EvaluationCase) -> TeacherJudgment:
        model_input = ModelInput.from_messages(
            [
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=self._task_evaluator.build_teacher_prompt(case),
                ),
            ]
        )
        try:
            raw_output = self._model.generate(model_input)
        except Exception as exc:
            return TeacherJudgment(score=None, error=f"{type(exc).__name__}: {exc}")

        score = _parse_score(raw_output)
        if score is None:
            return TeacherJudgment(
                score=None,
                raw_output=raw_output,
                error="teacher output did not contain an exact binary score JSON object",
                metadata=self._model.get_last_generation_metadata(),
            )
        return TeacherJudgment(
            score=score,
            raw_output=raw_output,
            metadata=self._model.get_last_generation_metadata(),
        )


def _parse_score(raw_output: str) -> int | None:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        match = _SCORE_PATTERN.search(raw_output)
        return int(match.group(1)) if match else None
    score = payload.get("score") if isinstance(payload, dict) else None
    return score if score in {0, 1} else None
