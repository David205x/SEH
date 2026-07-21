"""Evolution Runner 的 UTF-8 append-only 事件日志。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvolutionEvent:
    """一次可恢复的 Runner 状态转换。"""

    sequence: int
    event_type: str
    iteration: int | None
    timestamp: str
    payload: dict[str, Any]
    schema_version: int = 1


class EvolutionJournal:
    """保存并校验全局连续的 Evolution 事件序列。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        iteration: int | None = None,
    ) -> EvolutionEvent:
        events = self.events()
        event = EvolutionEvent(
            sequence=len(events),
            event_type=event_type,
            iteration=iteration,
            timestamp=datetime.now(UTC).isoformat(),
            payload=dict(payload),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(_to_dict(event), ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        return event

    def events(self) -> tuple[EvolutionEvent, ...]:
        if not self.path.exists():
            return ()
        result: list[EvolutionEvent] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            raw = json.loads(line)
            event = _from_dict(raw)
            if event.sequence != len(result):
                raise ValueError(
                    f"non-contiguous evolution event at line {line_number}"
                )
            result.append(event)
        return tuple(result)

    def find(self, event_type: str, iteration: int) -> EvolutionEvent | None:
        for event in reversed(self.events()):
            if event.event_type == event_type and event.iteration == iteration:
                return event
        return None


def _to_dict(event: EvolutionEvent) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "iteration": event.iteration,
        "timestamp": event.timestamp,
        "payload": event.payload,
    }


def _from_dict(raw: dict[str, Any]) -> EvolutionEvent:
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported evolution event schema_version")
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise TypeError("evolution event payload must be an object")
    iteration = raw.get("iteration")
    if iteration is not None and not isinstance(iteration, int):
        raise TypeError("evolution event iteration must be an integer or null")
    return EvolutionEvent(
        sequence=int(raw["sequence"]),
        event_type=str(raw["event_type"]),
        iteration=iteration,
        timestamp=str(raw["timestamp"]),
        payload=dict(payload),
    )
