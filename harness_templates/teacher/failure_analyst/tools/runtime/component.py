"""Failure Analyst Tool Component factory。"""

from __future__ import annotations

from typing import Any

from search_harness.evolution.research.tools import build_builtin_tool


def build(config: dict[str, Any], context: Any):
    return build_builtin_tool(config, context)
