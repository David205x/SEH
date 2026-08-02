"""Agent 组合对象。"""

from __future__ import annotations

from dataclasses import dataclass

from ..harness.runtime import Harness
from .model import Model


@dataclass(frozen=True)
class Agent:
    """一个可复用 Harness 与一个 Model 的组合。"""

    harness: Harness
    model: Model
