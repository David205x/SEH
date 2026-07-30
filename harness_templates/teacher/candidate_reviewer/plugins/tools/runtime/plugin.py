"""Expose explicitly selected built-in Teacher tools."""

from __future__ import annotations

from typing import Any

from search_harness.teacher.builtin_tools import build_builtin_tool
from search_harness.teacher.spec import TeacherPluginContext


def build(config: dict[str, Any], context: TeacherPluginContext):
    return build_builtin_tool(config, context)
