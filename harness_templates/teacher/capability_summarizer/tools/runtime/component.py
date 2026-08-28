"""Capability Summarizer built-in tool adapter."""

from __future__ import annotations

from typing import Any

from search_harness.evolution.research.tools import build_builtin_tool
from search_harness.framework.harness import ComponentFactoryContext
from search_harness.framework.tools import CallableTool


def build(config: dict[str, Any], context: ComponentFactoryContext) -> CallableTool:
    return build_builtin_tool(config, context)
