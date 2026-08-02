"""Agent Run 的有序行为事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TrajectoryEvent:
    """Agent Run 中按发生顺序记录的一个行为事件。"""

    index: int
    step: int
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "step": self.step,
            "event_type": self.event_type,
            "payload": dict(self.payload),
        }
