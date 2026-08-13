"""Shadow Compiler Tool Component factory."""

from __future__ import annotations

from typing import Any

from experiments.teacher_query_views.tools import build_shadow_tool
from search_harness.framework.harness import ComponentFactoryContext


def build(config: dict[str, Any], context: ComponentFactoryContext):
    return build_shadow_tool(config, context)
