"""Dataset types shared by loaders and experiment runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatasetRecordContext:
    """Location of a source record inside a dataset file."""

    path: Path
    line_number: int

    def describe(self) -> str:
        return f"{self.path}:{self.line_number}"


@dataclass(frozen=True)
class DatasetExample:
    """Canonical question example consumed by harness runners."""

    example_id: str
    question: str
    answer: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None
    line_number: int | None = None

    def __post_init__(self) -> None:
        if not self.example_id.strip():
            raise ValueError("dataset example_id must not be empty")
        if not self.question.strip():
            raise ValueError("dataset question must not be empty")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "example_id": self.example_id,
            "question": self.question,
            "answer": self.answer,
            "metadata": self.metadata,
        }
        if self.source_path is not None:
            payload["source_path"] = self.source_path
        if self.line_number is not None:
            payload["line_number"] = self.line_number
        return payload
