"""Failure Analyst Prompt Component。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from search_harness.framework.tools import ToolSet
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.spec import TeacherPromptSpec


def build(
    config: dict[str, Any],
    context: Any,
    tools: ToolSet,
) -> TeacherPromptSpec:
    """加载现有 Prompt 资产；ToolSet 由共享 Assembly 统一传入。"""

    del context, tools
    return load_prompt_spec(Path(__file__).resolve().parent, config)
