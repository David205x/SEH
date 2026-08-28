"""Expose the single built-in Shadow Prompt Probe tool."""

from __future__ import annotations

from search_harness.evolution.research.tools import build_builtin_tool
from search_harness.framework.harness import ComponentFactoryContext


def build(config: dict[str, object], context: ComponentFactoryContext):
    return build_builtin_tool(config, context)
