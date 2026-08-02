"""Machine-readable projection of assembled Harness Components."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .assembly import AssembledHarnessComponents
from .lifecycle import BaseHook, HookPhase
from .manifest import ComponentDeclaration
from .state import StateRef


_PHASE_ORDER = (
    HookPhase.PRE_PROMPT,
    HookPhase.POST_PROMPT,
    HookPhase.POST_MODEL,
    HookPhase.POST_PARSE,
    HookPhase.PRE_TOOL,
    HookPhase.POST_TOOL,
    HookPhase.PRE_FINAL,
    HookPhase.ON_ERROR,
)


def describe_harness(
    components: AssembledHarnessComponents,
    *,
    component_policies: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Describe declarations, runtime Tools, Extensions and Hook placement."""

    policies = component_policies or {}
    manifest = components.manifest
    enabled_tools = [item for item in manifest.tools if item.enabled]
    tool_instances = list(components.tools.tools)
    tools = []
    for declaration in manifest.tools:
        runtime_tool = None
        if declaration.enabled:
            runtime_tool = tool_instances[enabled_tools.index(declaration)]
        tools.append(
            {
                **_declaration_payload(declaration, policies),
                "tool_name": (
                    runtime_tool.name if runtime_tool is not None else None
                ),
                "description": (
                    runtime_tool.definition.description
                    if runtime_tool is not None
                    else None
                ),
                "parameters": (
                    runtime_tool.definition.to_json_schema()
                    if runtime_tool is not None
                    else None
                ),
            }
        )

    binding_map = {
        binding.instance_id: tuple(
            item for item in binding.components if isinstance(item, BaseHook)
        )
        for binding in components.extensions
    }
    ordered_hooks = [
        hook
        for binding in components.extensions
        for hook in binding_map.get(binding.instance_id, ())
    ]
    execution_order = {
        hook.hook_id: index
        for index, hook in enumerate(ordered_hooks, start=1)
    }
    extensions = [
        {
            **_declaration_payload(declaration, policies),
            "hooks": [
                _hook_payload(hook, execution_order[hook.hook_id])
                for hook in binding_map.get(declaration.instance_id, ())
            ],
        }
        for declaration in manifest.extensions
    ]
    return {
        "schema_version": 1,
        "harness_id": manifest.harness_id,
        "phase_order": list(_PHASE_ORDER),
        "prompt": _declaration_payload(manifest.prompt, policies),
        "output": _declaration_payload(manifest.output, policies),
        "tools": tools,
        "extensions": extensions,
    }


def _declaration_payload(
    declaration: ComponentDeclaration,
    policies: Mapping[str, str],
) -> dict[str, Any]:
    payload = {
        "instance_id": declaration.instance_id,
        "entrypoint": declaration.entrypoint,
        "enabled": declaration.enabled,
        "config": dict(declaration.config),
    }
    policy = policies.get(declaration.instance_id)
    if policy is not None:
        payload["evolution_policy"] = policy
    return payload


def _hook_payload(hook: BaseHook, execution_order: int) -> dict[str, Any]:
    return {
        "hook_id": hook.hook_id,
        "execution_order": execution_order,
        "phases": [phase for phase in _PHASE_ORDER if phase in hook.phases],
        "state_refs": [_state_ref_payload(ref) for ref in hook.state_refs],
        "writable_stage_keys": sorted(hook.writable_stage_keys),
        "model_profiles": sorted(hook.model_profiles),
        "max_model_calls_per_invocation": hook.max_model_calls_per_invocation,
    }


def _state_ref_payload(ref: StateRef) -> dict[str, Any]:
    value_type = ref.value_type
    if isinstance(value_type, tuple):
        type_name = " | ".join(item.__name__ for item in value_type)
    elif isinstance(value_type, type):
        type_name = value_type.__name__
    else:
        type_name = None
    return {
        "key": ref.key,
        "owner": ref.owner,
        "value_type": type_name,
        "writers": sorted(ref.writers),
    }
