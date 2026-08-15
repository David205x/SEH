"""Activate the frozen v9 adaptive controller only on routed decompose questions."""

from __future__ import annotations

from typing import Any

from experiments.as_you_can.templates.search_agent_v9_adaptive_decompose.extensions.adaptive_decompose import component as upstream
from experiments.as_you_can.templates.search_agent_v11_routed_adaptive.extensions.question_router.component import ROUTE_KEY


class RoutedAdaptiveHook(upstream.AdaptiveDecomposeHook):
    def handle(self, context: Any) -> None:
        route = context.state.get(ROUTE_KEY, "decompose")
        if route == "delegate":
            return
        super().handle(context)


def build(config: dict[str, Any], context: Any) -> RoutedAdaptiveHook:
    del context
    unknown = set(config) - {"max_searches", "topk", "max_evidence_chars"}
    if unknown:
        raise ValueError(f"routed adaptive has unsupported keys: {sorted(unknown)}")
    values = {
        key: _positive(config.get(key, default), key)
        for key, default in (
            ("max_searches", 2),
            ("topk", 5),
            ("max_evidence_chars", 6000),
        )
    }
    return RoutedAdaptiveHook(**values)


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value
