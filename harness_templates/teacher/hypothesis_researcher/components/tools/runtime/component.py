"""Expose explicitly selected built-in Teacher tools."""

from __future__ import annotations

from typing import Any

from search_harness.framework.harness import ComponentFactoryContext
from search_harness.evolution.research.tools import build_builtin_tool


def build(config: dict[str, Any], context: ComponentFactoryContext):
    return build_builtin_tool(config, context)
