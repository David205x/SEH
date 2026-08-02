"""一次 Agent Run 的内存行为记录器。"""

from __future__ import annotations

from typing import Any

from .events import TrajectoryEvent


class InMemoryTrajectoryRecorder:
    """按发生顺序追加 Trajectory Event。"""

    def __init__(self) -> None:
        self._events: list[TrajectoryEvent] = []

    def record(
        self,
        event_type: str,
        step: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = TrajectoryEvent(
            index=len(self._events) + 1,
            step=step,
            event_type=event_type,
            payload=dict(payload or {}),
        )
        self._events.append(event)

    @property
    def events(self) -> tuple[TrajectoryEvent, ...]:
        return tuple(self._events)
