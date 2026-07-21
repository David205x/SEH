"""Loader for the filtered Hotpot-style JSONL files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .jsonl import JsonlDatasetLoader
from .identity import stable_example_id
from .types import DatasetExample, DatasetRecordContext


@dataclass(frozen=True)
class FilteredHotpotJsonlMapper:
    """Map filtered Hotpot-style records into canonical examples."""

    include_raw: bool = False
    required_filter_status: str | None = None

    def map_record(
        self,
        record: dict[str, Any],
        context: DatasetRecordContext,
    ) -> DatasetExample | None:
        if self.required_filter_status is not None:
            status = _filter_status(record, context)
            if status != self.required_filter_status:
                return None

        question = _required_string(record, "question", context)
        try:
            example_id = stable_example_id(record.get("_id"), question)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context.describe()}: {exc}") from exc
        answer = _optional_string(record, "answer", context)
        metadata = _metadata_from_record(record, include_raw=self.include_raw)
        return DatasetExample(
            example_id=example_id,
            question=question,
            answer=answer,
            metadata=metadata,
            source_path=str(context.path),
            line_number=context.line_number,
        )


class FilteredHotpotJsonlLoader(JsonlDatasetLoader):
    """JSONL loader for corpus_filter output files."""

    def __init__(
        self,
        path: Path,
        include_raw: bool = False,
        required_filter_status: str | None = None,
    ) -> None:
        super().__init__(
            path=path,
            mapper=FilteredHotpotJsonlMapper(
                include_raw=include_raw,
                required_filter_status=required_filter_status,
            ),
        )


def _required_string(
    record: dict[str, Any],
    field_name: str,
    context: DatasetRecordContext,
) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context.describe()}: {field_name} must be a non-empty string")
    return value


def _optional_string(
    record: dict[str, Any],
    field_name: str,
    context: DatasetRecordContext,
) -> str | None:
    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{context.describe()}: {field_name} must be a string")
    return value


def _metadata_from_record(
    record: dict[str, Any],
    include_raw: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field_name in ("type", "level", "supporting_facts"):
        if field_name in record:
            metadata[field_name] = record[field_name]

    filter_record = record.get("_filter")
    if filter_record is not None:
        if not isinstance(filter_record, dict):
            raise ValueError("_filter must be an object when present")
        metadata["filter"] = filter_record
        for field_name in (
            "status",
            "confidence",
            "evidence",
            "missing_entities",
            "retrieval_queries",
            "reason",
            "error_type",
            "error",
        ):
            if field_name in filter_record:
                metadata[f"filter_{field_name}"] = filter_record[field_name]

    if include_raw:
        metadata["raw_record"] = record
    return metadata


def _filter_status(record: dict[str, Any], context: DatasetRecordContext) -> str | None:
    filter_record = record.get("_filter")
    if filter_record is None:
        return None
    if not isinstance(filter_record, dict):
        raise ValueError(f"{context.describe()}: _filter must be an object when present")
    status = filter_record.get("status")
    if status is None:
        return None
    if not isinstance(status, str):
        raise ValueError(f"{context.describe()}: _filter.status must be a string")
    return status
