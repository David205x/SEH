"""UTF-8 persistence for Evolution Controller events and effect artifacts."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .domain import ControlEvent, EffectResult, project_events


class ControlJournal:
    """Append-only JSONL event journal for one single-writer controller run."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def read(self) -> list[ControlEvent]:
        """Load and validate the complete event stream."""

        if not self.path.exists():
            return []
        events: list[ControlEvent] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid control journal JSON at "
                    f"{self.path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise TypeError(
                    f"control journal event must be an object at "
                    f"{self.path}:{line_number}"
                )
            events.append(
                ControlEvent.from_dict(_migrate_legacy_attempt_names(value))
            )
        project_events(events)
        return events

    def append(
        self,
        event_type: str,
        payload: dict[str, object],
    ) -> ControlEvent:
        """Append and fsync one event with the next contiguous sequence."""

        return self.append_many([(event_type, payload)])[0]

    def append_many(
        self,
        entries: list[tuple[str, dict[str, object]]],
    ) -> list[ControlEvent]:
        """Append a small ordered event batch and return materialized events."""

        if not entries:
            return []
        existing = self.read()
        next_sequence = len(existing) + 1
        created_at = datetime.now(UTC).isoformat()
        events: list[ControlEvent] = []
        for offset, (event_type, payload) in enumerate(entries):
            if not event_type.strip():
                raise ValueError("control event type must not be empty")
            events.append(
                ControlEvent(
                    sequence=next_sequence + offset,
                    event_type=event_type,
                    payload=dict(payload),
                    created_at=created_at,
                )
            )
        project_events([*existing, *events])

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            for event in events:
                file.write(
                    json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
                )
            file.flush()
            os.fsync(file.fileno())
        return events


class ControlArtifactStore:
    """Durably store large effect results outside the event journal."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def work_dir(self, work_id: str) -> Path:
        if not work_id.strip():
            raise ValueError("work_id must not be empty")
        if Path(work_id).name != work_id:
            raise ValueError("work_id must be one safe path component")
        return self.root / work_id

    def effect_path(self, work_id: str) -> Path:
        return self.work_dir(work_id) / "effect.json"

    def has_effect(self, work_id: str) -> bool:
        return self.effect_path(work_id).is_file()

    def write_effect(self, work_id: str, result: EffectResult) -> Path:
        """Atomically persist one completed effect using explicit UTF-8."""

        target = self.effect_path(work_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(
                    result.to_dict(),
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def load_effect(self, work_id: str) -> EffectResult:
        path = self.effect_path(work_id)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(f"effect artifact must be a JSON object: {path}")
        return EffectResult.from_dict(_migrate_legacy_attempt_names(value))


def _migrate_legacy_attempt_names(value: object) -> object:
    """Map legacy Iteration keys at persisted Control read boundaries."""

    if isinstance(value, list):
        return [_migrate_legacy_attempt_names(item) for item in value]
    if not isinstance(value, dict):
        return value
    migrated: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if key == "iteration_id":
            key = "candidate_attempt_id"
        elif key.startswith("iteration_"):
            key = f"candidate_attempt_{key.removeprefix('iteration_')}"
        migrated[key] = _migrate_legacy_attempt_names(raw_value)
    return migrated
