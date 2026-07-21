"""Machine-readable topology projection for assembled Harness components."""

from __future__ import annotations

from typing import Any

from search_harness.core import BaseHook, HookPhase, StateRef

from .assembler import HarnessComponents
from .manifest import ComponentSpec


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


def describe_harness(components: HarnessComponents) -> dict[str, Any]:
    """Describe configured components, Hook placement and declared capabilities."""

    manifest = components.manifest
    enabled_tools = [spec for spec in manifest.tools if spec.enabled]
    tool_instances = list(components.tools.tools)
    tools = []
    for spec in manifest.tools:
        runtime_tool = None
        if spec.enabled:
            runtime_tool = tool_instances[enabled_tools.index(spec)]
        tools.append(
            {
                **_spec_payload(spec),
                "tool_name": runtime_tool.name if runtime_tool is not None else None,
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
        binding.instance_id: binding.hooks
        for binding in components.extension_bindings
    }
    execution_order = {
        hook.hook_id: index
        for index, hook in enumerate(components.hooks.hooks, start=1)
    }
    extensions = []
    for spec in manifest.extensions:
        hooks = binding_map.get(spec.instance_id, ())
        extensions.append(
            {
                **_spec_payload(spec),
                "hooks": [
                    _hook_payload(hook, execution_order[hook.hook_id])
                    for hook in hooks
                ],
            }
        )

    return {
        "schema_version": 1,
        "harness_id": manifest.harness_id,
        "phase_order": list(_PHASE_ORDER),
        "prompt": _spec_payload(manifest.prompt),
        "tools": tools,
        "extensions": extensions,
    }


def _spec_payload(spec: ComponentSpec) -> dict[str, Any]:
    return {
        "instance_id": spec.instance_id,
        "entrypoint": spec.entrypoint,
        "enabled": spec.enabled,
        "evolution_policy": spec.evolution_policy.value,
        "config": dict(spec.config),
    }


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
