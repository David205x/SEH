"""Non-invasive lifecycle hook for verifying a configured HookPipeline."""

from __future__ import annotations

from typing import Any

from search_harness.framework import BaseHook, HookContext, HookPhase


class LifecycleAuditHook(BaseHook):
    """Exercise every phase while relying on the core trace as its audit log."""

    def __init__(self, hook_id: str = "lifecycle_audit") -> None:
        super().__init__(
            hook_id=hook_id,
            phases=HookPhase.ALL,
        )

    def handle(self, context: HookContext) -> None:
        """No-op: HookPipeline records the phase as a hook_applied trace event."""

        del context


def build(config: dict[str, Any], context: Any) -> LifecycleAuditHook:
    """Create the audit hook; configuration is intentionally empty."""

    del context
    if config:
        raise ValueError("lifecycle_audit does not accept configuration")
    return LifecycleAuditHook()
