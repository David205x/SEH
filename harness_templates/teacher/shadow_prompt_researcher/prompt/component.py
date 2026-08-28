"""Shadow Prompt Researcher Prompt Component."""

from __future__ import annotations

from pathlib import Path

from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.evolution.research.roles.spec import TeacherPromptSpec
from search_harness.framework.harness import ComponentFactoryContext
from search_harness.framework.tools import ToolSet


def build(
    config: dict[str, object],
    context: ComponentFactoryContext,
    tools: ToolSet,
) -> TeacherPromptSpec:
    del context, tools
    return load_prompt_spec(Path(__file__).resolve().parent, config)
