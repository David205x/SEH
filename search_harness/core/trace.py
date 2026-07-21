"""Trace recording for core loop rollouts."""

from __future__ import annotations

from typing import Any

from .types import TraceEvent


class InMemoryTraceRecorder:
    """Append-only trace recorder for one rollout."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(
        self,
        event_type: str,
        step: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = TraceEvent(
            index=len(self._events) + 1,
            step=step,
            event_type=event_type,
            payload=dict(payload or {}),
        )
        self._events.append(event)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

