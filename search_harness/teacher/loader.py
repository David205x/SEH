"""从目录模板装配 transport-neutral TeacherAgentSpec。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from search_harness.framework.tooling import DefinedTool, ToolSet
from search_harness.registry.plugin_importer import load_factory, plugin_import_session

from .contracts import get_teacher_role
from .manifest import TeacherAgentManifest, load_teacher_manifest
from .spec import TeacherAgentSpec, TeacherPluginContext, TeacherPromptSpec


def load_teacher_agent_spec(
    template_root: Path,
    *,
    runtime_context: object,
) -> TeacherAgentSpec:
    """加载 Prompt、Tool 和固定角色协议，不创建具体 SDK Agent。"""

    root = template_root.resolve()
    manifest = load_teacher_manifest(root)
    role = get_teacher_role(
        manifest.role.contract_id,
        manifest.role.version,
    )
    if (
        role.output_contract_id != manifest.output_contract.contract_id
        or role.output_contract_version != manifest.output_contract.version
    ):
        declared = (
            f"{manifest.output_contract.contract_id}@"
            f"{manifest.output_contract.version}"
        )
        expected = (
            f"{role.output_contract_id}@{role.output_contract_version}"
        )
        raise ValueError(
            f"Teacher template output contract mismatch: {declared}, expected {expected}"
        )

    context = TeacherPluginContext(
        template_root=root,
        runtime_context=runtime_context,
    )
    with plugin_import_session():
        tools = ToolSet(_load_tools(root, manifest, context))
        prompt = _load_prompt(root, manifest, context)
    return TeacherAgentSpec(
        manifest=manifest,
        role=role,
        prompt=prompt,
        tools=tools,
    )


def _load_tools(
    root: Path,
    manifest: TeacherAgentManifest,
    context: TeacherPluginContext,
) -> tuple[DefinedTool, ...]:
    tools: list[DefinedTool] = []
    for component in manifest.tools:
        if not component.enabled:
            continue
        value = load_factory(root, component)(dict(component.config), context)
        if not _is_defined_tool(value):
            raise TypeError(
                f"Teacher tool plugin '{component.instance_id}' returned an invalid tool"
            )
        tools.append(value)
    return tuple(tools)


def _load_prompt(
    root: Path,
    manifest: TeacherAgentManifest,
    context: TeacherPluginContext,
) -> TeacherPromptSpec:
    value = load_factory(root, manifest.prompt)(
        dict(manifest.prompt.config),
        context,
    )
    if not isinstance(value, TeacherPromptSpec):
        raise TypeError("Teacher prompt plugin must return TeacherPromptSpec")
    return value


def _is_defined_tool(value: Any) -> bool:
    return (
        hasattr(value, "name")
        and isinstance(value.name, str)
        and hasattr(value, "definition")
        and hasattr(value, "run")
        and callable(value.run)
    )

