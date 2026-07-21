"""Stable identity helpers shared by dataset, evaluation and Adapter paths."""

from __future__ import annotations

import hashlib
import unicodedata


def stable_example_id(raw_id: object, question: str) -> str:
    """Preserve a source ID or derive one deterministically from the question."""

    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    if raw_id is not None:
        raise ValueError("example_id must be a non-empty string when present")
    normalized = normalize_question(question)
    if not normalized:
        raise ValueError("cannot derive example_id from an empty question")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"question_sha256:{digest}"


def normalize_question(question: str) -> str:
    """Normalize representational differences without changing question wording."""

    if not isinstance(question, str):
        raise TypeError("question must be a string")
    normalized = unicodedata.normalize("NFKC", question)
    return " ".join(normalized.split())
