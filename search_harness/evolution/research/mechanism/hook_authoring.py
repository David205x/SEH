"""新版 Compiler 使用的渐进式 Hook 编写指南。"""

from __future__ import annotations

from typing import Any, Callable

from search_harness.framework import HookPhase

from .hook_api import public_hook_imports


HOOK_AUTHORING_API_VERSION = 7
HOOK_AUTHORING_TOPICS = (
    "index",
    "implementation",
    "lifecycle",
    "state_access",
    "model_inference",
    "final_decision",
    "manifest",
)


def get_hook_authoring_guide(topic: str) -> dict[str, Any]:
    """返回新版 Compiler 的一个 Hook 语义指南分片。"""

    normalized = topic.strip().casefold()
    if normalized not in HOOK_AUTHORING_TOPICS:
        raise ValueError(f"unsupported Hook authoring topic: {topic}")
    return {
        "api_version": HOOK_AUTHORING_API_VERSION,
        "topic": normalized,
        **_TOPIC_BUILDERS[normalized](),
    }


def _index() -> dict[str, Any]:
    return {
        "topics": {
            "implementation": "Public imports, BaseHook contract, and Component Factory.",
            "lifecycle": "Hook phases and phase-local stage state.",
            "state_access": "Core, stage, shared, and extension state semantics.",
            "model_inference": "Bounded traced model calls made by a Hook.",
            "final_decision": "Accepting or deferring a parsed final answer.",
            "manifest": "Component files and Harness registration.",
        },
        "api_discovery": [
            "Use list_hook_api_symbols to discover public classes and state keys.",
            (
                "Use query_hook_api for every class, member, or state key used "
                "by new code."
            ),
            "Private or unlisted members are not part of the Compiler-facing API.",
            (
                "Stable closed values may be used directly after the documented "
                "phase guarantees them."
            ),
            "Experimental or open values require a narrow, mechanism-specific check.",
        ],
    }


def _implementation() -> dict[str, Any]:
    return {
        "public_core_imports": public_hook_imports(),
        "rules": [
            "Import public Hook runtime symbols from search_harness.framework only.",
            (
                "A Component Factory build(config, context) returns one BaseHook or an "
                "iterable of BaseHook instances."
            ),
            (
                "A BaseHook subclass implements "
                "handle(self, context: HookContext) -> None."
            ),
            (
                "Declare phases, writable stage keys, StateRefs, and model "
                "profiles explicitly."
            ),
            "Do not use getattr, hasattr, setattr, or delattr.",
            "Do not probe stable closed framework values with defensive type checks.",
            "Query exact signatures instead of inferring fields from examples.",
        ],
        "minimal_component": (
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            "from search_harness.framework import BaseHook, HookContext, HookPhase\n\n\n"
            "class ExampleHook(BaseHook):\n"
            "    def __init__(self) -> None:\n"
            "        super().__init__(\n"
            "            hook_id='example_hook',\n"
            "            phases=frozenset({HookPhase.POST_PROMPT}),\n"
            "            writable_stage_keys=frozenset({'stage.model_input'}),\n"
            "        )\n\n"
            "    def handle(self, context: HookContext) -> None:\n"
            "        model_input = context.state.get('stage.model_input')\n"
            "        context.state.set('stage.model_input', model_input)\n\n\n"
            "def build(config: dict[str, Any], context: Any) -> BaseHook:\n"
            "    if config:\n"
            "        raise ValueError('example_hook does not accept configuration')\n"
            "    return ExampleHook()\n"
        ),
    }


def _lifecycle() -> dict[str, Any]:
    return {
        "phases": [
            {"name": HookPhase.PRE_PROMPT, "state_queries": []},
            {
                "name": HookPhase.POST_PROMPT,
                "state_queries": ["stage.model_input"],
            },
            {
                "name": HookPhase.POST_MODEL,
                "state_queries": ["stage.raw_model_output"],
            },
            {
                "name": HookPhase.POST_PARSE,
                "state_queries": [
                    "stage.parser_input",
                    "stage.parsed_output",
                ],
            },
            {
                "name": HookPhase.PRE_TOOL,
                "state_queries": ["stage.tool_call"],
            },
            {
                "name": HookPhase.POST_TOOL,
                "state_queries": ["stage.tool_call", "stage.tool_result"],
            },
            {
                "name": HookPhase.PRE_FINAL,
                "state_queries": ["stage.final_decision"],
            },
            {"name": HookPhase.ON_ERROR, "state_queries": ["stage.error"]},
        ],
        "rules": [
            (
                "Query each stage key for its exact type, write semantics, "
                "and active phase."
            ),
            (
                "Stage values disappear after the phase; use declared "
                "persistent state across phases."
            ),
            "Hooks execute in manifest order.",
        ],
    }


def _state_access() -> dict[str, Any]:
    return {
        "namespaces": {
            "core.*": "Read-only serialized AgentState projection.",
            "stage.*": "Phase-local loop values; writes require explicit declaration.",
            "shared.*": "Declared persistent cross-Hook state.",
            "extension.<hook_id>.*": "Declared persistent state owned by one Hook.",
        },
        "rules": [
            (
                "Read through HookContext.state.get and replace through "
                "HookContext.state.set."
            ),
            "Values returned by get are copies; in-place mutation is not committed.",
            "Every persistent writable key requires a StateRef and an explicit writer.",
            "Query core and stage keys before relying on their representation.",
        ],
    }


def _model_inference() -> dict[str, Any]:
    return {
        "required_queries": [
            "BaseHook.model_profiles",
            "BaseHook.max_model_calls_per_invocation",
            "HookContext.call_model",
            "HookModelRequest",
            "HookModelResponse",
        ],
        "rules": [
            "HookContext.call_model performs one generation, not a nested AgentLoop.",
            "The response changes Student behavior only after an explicit state.set.",
            "The runtime traces complete requests, outputs, and model errors.",
            "Do not create HTTP clients or model adapters inside a Component.",
            "Parse model output explicitly and define a deterministic failure policy.",
        ],
    }


def _final_decision() -> dict[str, Any]:
    return {
        "required_queries": [
            "stage.final_decision",
            "FinalDecision",
            "FinalDecision.accept",
            "FinalDecision.defer",
        ],
        "rules": [
            "Use PRE_FINAL to control completion of a Hook-owned strategy.",
            "Declare stage.final_decision writable before replacing it.",
            (
                "A deferred decision cannot be changed back to accept later "
                "in the same phase."
            ),
            "Deferral consumes the current step and remains bounded by core.max_steps.",
        ],
    }


def _manifest() -> dict[str, Any]:
    return {
        "required_changes": [
            "Create a complete components/extensions/<instance_id>/component.py.",
            "Create referenced UTF-8 prompt files when the Hook calls a model.",
            "Register the extension in harness.json in the same candidate transaction.",
            "Register its mutable policy in evolution.json in the same transaction.",
        ],
        "rules": [
            "harness.json contains assembly declarations, not evolution policy.",
            "New model-created components use mutable policy in evolution.json.",
            "Do not modify fixed components.",
            "One component instance owns one component directory.",
        ],
    }


_TOPIC_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "index": _index,
    "implementation": _implementation,
    "lifecycle": _lifecycle,
    "state_access": _state_access,
    "model_inference": _model_inference,
    "final_decision": _final_decision,
    "manifest": _manifest,
}
