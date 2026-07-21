"""Protocols for dataset loading."""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from .types import DatasetExample, DatasetRecordContext


class DatasetLoader(Protocol):
    """Iterable source of canonical dataset examples."""

    def iter_examples(self) -> Iterator[DatasetExample]:
        """Yield examples one by one."""


class DatasetRecordMapper(Protocol):
    """Map one parsed source record to a canonical example."""

    def map_record(
        self,
        record: dict[str, Any],
        context: DatasetRecordContext,
    ) -> DatasetExample | None:
        """Return an example, or None when a record should be skipped."""
