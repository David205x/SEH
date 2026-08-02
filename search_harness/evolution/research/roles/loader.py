"""通过共享 Harness Assembly 装配 transport-neutral Teacher Agent spec。"""

from __future__ import annotations

from pathlib import Path

from search_harness.framework.harness import assemble_harness_components

from .contracts import get_teacher_role
from .spec import TeacherAgentSpec, TeacherOutputSpec, TeacherPromptSpec


def load_teacher_agent_spec(
    template_root: Path,
    *,
    runtime_context: object,
    role_id: str,
    role_version: int = 1,
) -> TeacherAgentSpec:
    """装配 Template Component，并由调用方绑定稳定 Teacher Role。"""

    role = get_teacher_role(role_id, role_version)
    assembled = assemble_harness_components(
        template_root,
        runtime_context=runtime_context,
    )
    if not isinstance(assembled.prompt, TeacherPromptSpec):
        raise TypeError("Teacher prompt component must return TeacherPromptSpec")
    if not isinstance(assembled.output, TeacherOutputSpec):
        raise TypeError("Teacher output component must return TeacherOutputSpec")
    if assembled.extensions:
        raise ValueError("Teacher Harness does not support Extension Components")
    return TeacherAgentSpec(
        manifest=assembled.manifest,
        role=role,
        prompt=assembled.prompt,
        output=assembled.output,
        tools=assembled.tools,
    )
