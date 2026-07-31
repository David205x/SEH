"""Build the fixed Conformance Reviewer prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from search_harness.teacher.prompting import load_prompt_spec
from search_harness.teacher.spec import (
    TeacherPluginContext,
    TeacherPromptSpec,
)

def build(
    config: dict[str, Any],
    context: TeacherPluginContext,
) -> TeacherPromptSpec:
    """Load the configured UTF-8 prompt templates."""

    del context
    return load_prompt_spec(Path(__file__).resolve().parent, config)
