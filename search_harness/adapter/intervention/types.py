"""Small value objects shared by the Intervention runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search_harness.core import HookPhase, ModelInput


@dataclass(frozen=True)
class PrefixSelector:
    """Identify one inclusive lifecycle boundary in a rollout record."""

    rollout_file: Path
    example_id: str
    replicate_id: str
    step: int
    phase: str

    def __post_init__(self) -> None:
        if not self.example_id.strip():
            raise ValueError("prefix example_id must not be empty")
        if not self.replicate_id.strip():
            raise ValueError("prefix replicate_id must not be empty")
        if self.step < 1:
            raise ValueError("prefix step must be positive")
        if self.phase not in HookPhase.ALL:
            raise ValueError(f"unknown prefix phase: {self.phase}")


@dataclass(frozen=True)
class ReconstructedPrefix:
    """Model-visible prefix plus source evidence retained for the Worker."""

    selector: PrefixSelector
    example: dict[str, Any]
    source_run: dict[str, Any]
    model_input: ModelInput
    stage_values: dict[str, Any]
    retained_trace: tuple[dict[str, Any], ...]
    source_record: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class InterventionAction:
    """One terminal action selected by a Worker at a Hook activation."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "payload": dict(self.payload),
            "reason": self.reason,
        }
