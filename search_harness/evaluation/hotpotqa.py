"""HotpotQA answer evaluation with a deterministic exact-match first layer."""

from __future__ import annotations

import re
import string
import unicodedata

from .types import EvaluationCase, StaticDecision, StaticEvaluation


_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class HotpotQAEvaluator:
    """Evaluate short factual answers before escalating non-exact cases."""

    task_name = "hotpotqa"

    def evaluate_static(self, case: EvaluationCase) -> StaticEvaluation:
        if not case.golden_answer or not case.golden_answer.strip():
            return StaticEvaluation(
                decision=StaticDecision.UNRESOLVED,
                reason="golden answer is missing",
            )
        if not case.predicted_answer or not case.predicted_answer.strip():
            return StaticEvaluation(
                decision=StaticDecision.AUTOMATIC_ZERO,
                metrics={"exact_match": 0, "token_f1": 0.0},
                reason="prediction is missing",
            )

        prediction = normalize_answer(case.predicted_answer)
        golden = normalize_answer(case.golden_answer)
        exact_match = int(prediction == golden)
        token_f1 = _token_f1(prediction, golden)
        return StaticEvaluation(
            decision=(
                StaticDecision.PASS if exact_match else StaticDecision.NEEDS_TEACHER
            ),
            metrics={"exact_match": exact_match, "token_f1": token_f1},
        )

    def build_teacher_prompt(self, case: EvaluationCase) -> str:
        return (
            "Judge whether the predicted answer correctly answers the question given "
            "the reference answer. Accept aliases, equivalent wording, and compatible "
            "answer granularity; reject unsupported, contradictory, or different answers.\n\n"
            f"Question:\n{case.question}\n\n"
            f"Reference answer:\n{case.golden_answer}\n\n"
            f"Predicted answer:\n{case.predicted_answer}\n\n"
            "Return exactly one JSON object with no markdown: {\"score\": 0} or {\"score\": 1}."
        )


def normalize_answer(value: str) -> str:
    """Use the standard SQuAD-like normalization for deterministic answer matching."""

    text = unicodedata.normalize("NFKC", value).lower()
    text = "".join(character for character in text if character not in string.punctuation)
    text = _ARTICLES.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _token_f1(prediction: str, golden: str) -> float:
    predicted_tokens = prediction.split()
    golden_tokens = golden.split()
    if not predicted_tokens or not golden_tokens:
        return float(predicted_tokens == golden_tokens)
    overlap = sum(
        min(predicted_tokens.count(token), golden_tokens.count(token))
        for token in set(predicted_tokens)
    )
    if not overlap:
        return 0.0
    precision = overlap / len(predicted_tokens)
    recall = overlap / len(golden_tokens)
    return 2 * precision * recall / (precision + recall)
