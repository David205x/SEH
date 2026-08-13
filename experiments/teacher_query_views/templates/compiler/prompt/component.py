"""Shadow Compiler prompt using formal semantics and an authoring brief."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.teacher_query_views.compiler import build_parent_authoring_view
from experiments.teacher_query_views.prompt import ShadowCompilerPrompt
from search_harness.evolution.research.resources.base import TeacherResources
from search_harness.evolution.research.roles.prompting import load_prompt_spec
from search_harness.framework.harness import ComponentFactoryContext


def build(config: dict[str, Any], context: ComponentFactoryContext, tools: Any):
    del tools
    if config:
        raise ValueError("shadow Compiler prompt does not accept configuration")
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("shadow Compiler prompt requires TeacherResources")
    formal_root = (
        Path(__file__).resolve().parents[5]
        / "harness_templates"
        / "teacher"
        / "compiler"
        / "prompt"
    )
    formal = load_prompt_spec(
        formal_root,
        {"instructions": "system.md", "user_template": "user.md"},
    )
    instructions = formal.instructions + (
        "\n\n## Shadow authoring view\n\n"
        "The initial user message renders the complete mechanism, source-derived "
        "packet, exact parent registries, continuation files, and selected "
        "combination references as one Compiler Implementation Brief. This is a "
        "presentation change only. All formal semantic, safety, API whitelist, "
        "workspace, validation, and terminal rules remain binding. Prefer the "
        "brief before querying or reading; use tools whenever exact source or an "
        "unsettled public API detail is material."
    )
    return ShadowCompilerPrompt(
        instructions=instructions,
        user_template="{{role_input}}\n{{resource_context}}",
        continuation_templates=formal.continuation_templates,
        parent_authoring=build_parent_authoring_view(resources),
    )
