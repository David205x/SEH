"""Generic UTF-8 JSONL dataset loader."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Iterator

from .protocols import DatasetRecordMapper
from .types import DatasetExample, DatasetRecordContext


class JsonlDatasetLoader:
    """Read JSON objects from a JSONL file and map them to examples."""

    def __init__(self, path: Path, mapper: DatasetRecordMapper) -> None:
        self.path = path
        self.mapper = mapper

    def iter_examples(self) -> Iterator[DatasetExample]:
        if not self.path.exists():
            raise FileNotFoundError(f"dataset file does not exist: {self.path}")
        if not self.path.is_file():
            raise ValueError(f"dataset path is not a file: {self.path}")

        with self.path.open("r", encoding="utf-8") as file:
            for line_number, raw_line in enumerate(file, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                context = DatasetRecordContext(
                    path=self.path,
                    line_number=line_number,
                )
                record = _parse_json_object(line, context)
                example = self.mapper.map_record(record, context)
                if example is not None:
                    yield example

    def load(self, limit: int | None = None) -> list[DatasetExample]:
        if limit is not None and limit < 0:
            raise ValueError("dataset load limit must not be negative")

        examples: list[DatasetExample] = []
        for example in self.iter_examples():
            if limit is not None and len(examples) >= limit:
                break
            examples.append(example)
        return examples


def _parse_json_object(line: str, context: DatasetRecordContext) -> dict[str, object]:
    try:
        parsed = json.loads(line)
    except JSONDecodeError as exc:
        raise ValueError(f"{context.describe()}: invalid JSONL record") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{context.describe()}: JSONL record must be an object")
    return parsed
