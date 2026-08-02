"""Observe every Hook phase and retain compact per-run counters."""

from __future__ import annotations

from typing import Any

from search_harness.framework import BaseHook, HookContext, HookPhase, StateRef


PHASE_COUNTS = "extension.lifecycle_monitor.phase_counts"


class LifecycleMonitorHook(BaseHook):
    """Count phase triggers without changing loop-owned stage values."""

    def __init__(self, hook_id: str = "lifecycle_monitor") -> None:
        super().__init__(
            hook_id=hook_id,
            phases=HookPhase.ALL,
            state_refs=(
                StateRef(
                    key=PHASE_COUNTS,
                    owner=hook_id,
                    value_type=dict,
                    writers=frozenset({hook_id}),
                    default={},
                ),
            ),
        )

    def handle(self, context: HookContext) -> None:
        counts = context.state.get(PHASE_COUNTS)
        if not isinstance(counts, dict):
            raise TypeError("lifecycle phase counts must be an object")
        updated = dict(counts)
        updated[context.phase] = int(updated.get(context.phase, 0)) + 1
        context.state.set(PHASE_COUNTS, updated)


def build(config: dict[str, Any], context: Any) -> LifecycleMonitorHook:
    """Build the read-only lifecycle monitor."""

    del context
    if config:
        raise ValueError(
            f"lifecycle_monitor has unsupported config keys: {sorted(config)}"
        )
    return LifecycleMonitorHook()
