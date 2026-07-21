"""Append-only journal for resumable Harness evolution attempts."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterator, Literal

from .validation import ValidationReport
from .workspace import CandidateWorkspace, FileEdit, HarnessSnapshot

if TYPE_CHECKING:
    from .store import HarnessVersionStore, VersionRecord


IterationStatus = Literal["pending", "accepted", "rejected"]


@dataclass(frozen=True)
class IterationEvent:
    """One durable state transition in an evolution attempt."""

    iteration_id: str
    sequence: int
    event_type: str
    timestamp: str
    payload: Mapping[str, Any]
    schema_version: int = 1


@dataclass(frozen=True)
class IterationSummary:
    """Current state derived by folding one iteration's events."""

    iteration_id: str
    parent_version: str
    status: IterationStatus
    candidate_digest: str
    patch_count: int
    accepted_version: str | None = None
    rejection_reason: str | None = None


class IterationSession:
    """Managed candidate whose mutations and decisions are journaled."""

    def __init__(
        self,
        *,
        store: HarnessVersionStore,
        journal: IterationJournal,
        iteration_id: str,
        workspace: CandidateWorkspace,
    ) -> None:
        self._store = store
        self._journal = journal
        self.iteration_id = iteration_id
        self._workspace = workspace

    @property
    def parent_version(self) -> str:
        return self._workspace.parent.version_id

    @property
    def revision(self) -> int:
        return self._workspace.revision

    @property
    def digest(self) -> str:
        return self._workspace.digest

    @property
    def changed_paths(self) -> tuple[PurePosixPath, ...]:
        return self._workspace.changed_paths

    def read_text(self, path: str | PurePosixPath) -> str:
        return self._workspace.read_text(path)

    def exists(self, path: str | PurePosixPath) -> bool:
        return self._workspace.exists(path)

    def apply_patch(self, edits: Iterable[FileEdit]) -> None:
        """Apply and durably record one complete transactional patch."""

        self._ensure_pending()
        operations = tuple(edits)
        with self._workspace.transaction():
            self._workspace.apply_patch(operations)
            self._journal.append_patch(self.iteration_id, operations, self._workspace)

    def add_extension(
        self,
        *,
        instance_id: str,
        files: Mapping[str, str],
        entrypoint: str = "plugin.py:build",
        config: Mapping[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        """Create a mutable extension and journal its exact resulting file diff."""

        self._ensure_pending()
        with self._workspace.transaction():
            before = self._workspace.materialized_files()
            self._workspace.add_extension(
                instance_id=instance_id,
                files=files,
                entrypoint=entrypoint,
                config=config,
                enabled=enabled,
            )
            edits = _text_diff(before, self._workspace.materialized_files())
            self._journal.append_patch(self.iteration_id, edits, self._workspace)

    def validate(self, *, env_file: Path | None = None) -> ValidationReport:
        """Validate the current candidate and record the complete report."""

        self._ensure_pending()
        report = self._store.validate(self._workspace, env_file=env_file)
        self._journal.append(
            self.iteration_id,
            "validation_completed",
            {
                "passed": report.passed,
                "parent_version": report.parent_version,
                "revision": report.revision,
                "candidate_digest": report.candidate_digest,
                "added_paths": list(report.added_paths),
                "modified_paths": list(report.modified_paths),
                "removed_paths": list(report.removed_paths),
                "errors": list(report.errors),
            },
        )
        return report

    @contextmanager
    def stage(self) -> Iterator[Path]:
        """Materialize this pending candidate for one bounded runtime operation."""

        self._ensure_pending()
        with self._store.stage(self._workspace) as plugins_root:
            yield plugins_root

    def accept(
        self,
        *,
        summary: str,
        evaluation: Mapping[str, Any] | None = None,
        env_file: Path | None = None,
    ) -> VersionRecord:
        """Accept the candidate and close this iteration."""

        self._ensure_pending()
        record = self._store.accept(
            self._workspace,
            summary=summary,
            evaluation=evaluation,
            env_file=env_file,
            iteration_id=self.iteration_id,
        )
        self._journal.append(
            self.iteration_id,
            "accepted",
            {
                "version_id": record.version_id,
                "git_commit": record.git_commit,
                "candidate_digest": record.digest,
                "summary": record.summary,
                "evaluation": dict(record.evaluation),
            },
        )
        return record

    def reject(
        self,
        reason: str,
        *,
        evaluation: Mapping[str, Any] | None = None,
    ) -> None:
        """Close this iteration without creating an accepted Git version."""

        self._ensure_pending()
        if not reason.strip():
            raise ValueError("rejection reason must not be empty")
        self._journal.append(
            self.iteration_id,
            "rejected",
            {
                "reason": reason,
                "candidate_digest": self.digest,
                "evaluation": dict(evaluation or {}),
            },
        )

    def _ensure_pending(self) -> None:
        summary = self._journal.get_summary(self.iteration_id)
        if summary.status != "pending":
            raise RuntimeError(
                f"iteration {self.iteration_id} is already {summary.status}"
            )


class IterationJournal:
    """UTF-8 JSONL event store used to reconstruct in-memory candidates."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def start(
        self,
        store: HarnessVersionStore,
        parent: HarnessSnapshot,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> IterationSession:
        iteration_id = _new_iteration_id()
        self.append(
            iteration_id,
            "started",
            {
                "parent_version": parent.version_id,
                "parent_digest": parent.digest,
                "metadata": dict(metadata or {}),
            },
        )
        return IterationSession(
            store=store,
            journal=self,
            iteration_id=iteration_id,
            workspace=CandidateWorkspace(parent),
        )

    def resume(
        self,
        store: HarnessVersionStore,
        iteration_id: str,
    ) -> IterationSession:
        events = self.events(iteration_id)
        if not events:
            raise KeyError(f"unknown iteration: {iteration_id}")
        first = events[0]
        if first.event_type != "started":
            raise ValueError(f"iteration {iteration_id} has no valid start event")
        summary = _fold_events(events)
        if summary.status != "pending":
            raise RuntimeError(f"iteration {iteration_id} is already {summary.status}")

        parent = store.resolve(str(first.payload["parent_version"]))
        if parent.digest != first.payload.get("parent_digest"):
            raise ValueError(f"iteration {iteration_id} parent digest does not match")
        workspace = CandidateWorkspace(parent)
        for event in events:
            if event.event_type != "patch_applied":
                continue
            edits = tuple(_file_edit_from_dict(item) for item in event.payload["edits"])
            workspace.apply_patch(edits)
            if workspace.digest != event.payload.get("candidate_digest"):
                raise ValueError(
                    f"iteration {iteration_id} patch digest mismatch at sequence "
                    f"{event.sequence}"
                )
        return IterationSession(
            store=store,
            journal=self,
            iteration_id=iteration_id,
            workspace=workspace,
        )

    def append_patch(
        self,
        iteration_id: str,
        edits: Iterable[FileEdit],
        workspace: CandidateWorkspace,
    ) -> IterationEvent:
        operations = tuple(edits)
        return self.append(
            iteration_id,
            "patch_applied",
            {
                "edits": [
                    {
                        "operation": edit.operation,
                        "path": edit.path,
                        "content": edit.content,
                    }
                    for edit in operations
                ],
                "workspace_revision": workspace.revision,
                "candidate_digest": workspace.digest,
            },
        )

    def append(
        self,
        iteration_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> IterationEvent:
        events = self.events(iteration_id)
        event = IterationEvent(
            iteration_id=iteration_id,
            sequence=len(events),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=MappingProxyType(dict(payload)),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(_event_to_dict(event), ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        return event

    def events(self, iteration_id: str | None = None) -> tuple[IterationEvent, ...]:
        if not self.path.exists():
            return ()
        result: list[IterationEvent] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                event = _event_from_dict(raw)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid iteration journal event at line {line_number}: {exc}"
                ) from exc
            if iteration_id is None or event.iteration_id == iteration_id:
                result.append(event)
        return tuple(result)

    def list_summaries(self) -> tuple[IterationSummary, ...]:
        grouped: dict[str, list[IterationEvent]] = {}
        for event in self.events():
            grouped.setdefault(event.iteration_id, []).append(event)
        return tuple(_fold_events(tuple(events)) for events in grouped.values())

    def get_summary(self, iteration_id: str) -> IterationSummary:
        events = self.events(iteration_id)
        if not events:
            raise KeyError(f"unknown iteration: {iteration_id}")
        return _fold_events(events)


def _text_diff(
    before: Mapping[PurePosixPath, bytes],
    after: Mapping[PurePosixPath, bytes],
) -> tuple[FileEdit, ...]:
    edits: list[FileEdit] = []
    for path in sorted(set(before) - set(after), key=str):
        edits.append(FileEdit(operation="delete", path=str(path)))
    for path in sorted(set(after), key=str):
        if path in before and before[path] == after[path]:
            continue
        try:
            content = after[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"journal cannot persist non-UTF-8 plugin file: {path}") from exc
        edits.append(FileEdit(operation="write", path=str(path), content=content))
    return tuple(edits)


def _fold_events(events: tuple[IterationEvent, ...]) -> IterationSummary:
    if not events or events[0].event_type != "started":
        raise ValueError("iteration event stream must begin with started")
    expected_sequence = 0
    status: IterationStatus = "pending"
    candidate_digest = str(events[0].payload["parent_digest"])
    patch_count = 0
    accepted_version: str | None = None
    rejection_reason: str | None = None
    for event in events:
        if event.sequence != expected_sequence:
            raise ValueError("iteration event sequence is not contiguous")
        expected_sequence += 1
        if status != "pending":
            raise ValueError("iteration journal contains events after its terminal decision")
        if event.event_type == "patch_applied":
            patch_count += 1
            candidate_digest = str(event.payload["candidate_digest"])
        elif event.event_type == "accepted":
            status = "accepted"
            accepted_version = str(event.payload["version_id"])
            candidate_digest = str(event.payload["candidate_digest"])
        elif event.event_type == "rejected":
            status = "rejected"
            rejection_reason = str(event.payload["reason"])
            candidate_digest = str(event.payload["candidate_digest"])
    return IterationSummary(
        iteration_id=events[0].iteration_id,
        parent_version=str(events[0].payload["parent_version"]),
        status=status,
        candidate_digest=candidate_digest,
        patch_count=patch_count,
        accepted_version=accepted_version,
        rejection_reason=rejection_reason,
    )


def _event_to_dict(event: IterationEvent) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "iteration_id": event.iteration_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "payload": dict(event.payload),
    }


def _event_from_dict(raw: Mapping[str, Any]) -> IterationEvent:
    schema_version = raw["schema_version"]
    if schema_version != 1:
        raise ValueError(f"unsupported iteration schema_version: {schema_version}")
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise TypeError("iteration event payload must be an object")
    return IterationEvent(
        schema_version=schema_version,
        iteration_id=str(raw["iteration_id"]),
        sequence=int(raw["sequence"]),
        event_type=str(raw["event_type"]),
        timestamp=str(raw["timestamp"]),
        payload=MappingProxyType(dict(payload)),
    )


def _file_edit_from_dict(raw: Mapping[str, Any]) -> FileEdit:
    operation = raw.get("operation")
    if operation not in {"write", "delete"}:
        raise ValueError(f"invalid journal file operation: {operation}")
    content = raw.get("content")
    if content is not None and not isinstance(content, str):
        raise TypeError("journal file edit content must be a string or null")
    return FileEdit(operation=operation, path=str(raw["path"]), content=content)


def _new_iteration_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"iteration_{timestamp}_{uuid.uuid4().hex[:8]}"
