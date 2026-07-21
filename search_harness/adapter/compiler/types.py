"""Compiler input and output contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from search_harness.versioning import FileEdit


@dataclass(frozen=True)
class CompilerResult:
    """One complete candidate patch or a request for missing evidence."""

    summary: str
    edits: tuple[FileEdit, ...] = ()
    clarification: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CompilerResult":
        expected = {"summary", "edits", "clarification"}
        missing = expected - set(payload)
        if missing:
            raise ValueError(f"compiler result lacks required fields: {sorted(missing)}")
        unknown = set(payload) - expected
        if unknown:
            raise ValueError(f"compiler result has unsupported fields: {sorted(unknown)}")
        summary = payload.get("summary")
        raw_edits = payload.get("edits")
        clarification = payload.get("clarification")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("compiler result summary must be a non-empty string")
        if not isinstance(raw_edits, list):
            raise ValueError("compiler result edits must be an array")
        if clarification is not None and (
            not isinstance(clarification, str) or not clarification.strip()
        ):
            raise ValueError("compiler clarification must be null or a non-empty string")
        edits = tuple(_parse_edit(item) for item in raw_edits)
        paths = [edit.path for edit in edits]
        if len(paths) != len(set(paths)):
            raise ValueError("compiler result cannot edit the same path more than once")
        if bool(edits) == bool(clarification):
            raise ValueError(
                "compiler result must contain either edits or clarification, but not both"
            )
        return cls(
            summary=summary.strip(),
            edits=edits,
            clarification=clarification.strip() if clarification is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "edits": [
                {
                    "operation": edit.operation,
                    "path": edit.path,
                    "content": edit.content,
                }
                for edit in self.edits
            ],
            "clarification": self.clarification,
        }


def _parse_edit(raw: object) -> FileEdit:
    if not isinstance(raw, dict):
        raise ValueError("each compiler edit must be an object")
    expected = {"operation", "path", "content"}
    missing = expected - set(raw)
    if missing:
        raise ValueError(f"compiler edit lacks required fields: {sorted(missing)}")
    unknown = set(raw) - expected
    if unknown:
        raise ValueError(f"compiler edit has unsupported fields: {sorted(unknown)}")
    operation = raw.get("operation")
    if operation not in {"write", "delete"}:
        raise ValueError(f"unsupported compiler edit operation: {operation}")
    path = raw.get("path")
    if not isinstance(path, str):
        raise ValueError("compiler edit path must be a string")
    content = raw.get("content")
    if content is not None and not isinstance(content, str):
        raise ValueError("compiler edit content must be a string or null")
    return FileEdit(operation=operation, path=path, content=content)
