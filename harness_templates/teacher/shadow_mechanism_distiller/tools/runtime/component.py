"""Expose explicitly selected built-in Teacher tools。"""

from __future__ import annotations

from search_harness.evolution.research.tools import build_builtin_tool
from search_harness.framework.harness import ComponentFactoryContext


def build(config: dict[str, object], context: ComponentFactoryContext):
    return build_builtin_tool(config, context)
