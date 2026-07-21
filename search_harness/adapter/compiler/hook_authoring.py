"""Versioned, progressively disclosed Hook authoring reference."""

from __future__ import annotations

from typing import Any

from search_harness.core import HookPhase


HOOK_AUTHORING_API_VERSION = 3
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
    """Return one authoritative slice of the current Hook extension API."""

    normalized = topic.strip().casefold()
    if normalized not in HOOK_AUTHORING_TOPICS:
        raise ValueError(f"unsupported Hook authoring topic: {topic}")
    content = _TOPIC_BUILDERS[normalized]()
    return {
        "api_version": HOOK_AUTHORING_API_VERSION,
        "topic": normalized,
        **content,
    }


def _index() -> dict[str, Any]:
    return {
        "topics": {
            "implementation": "Legal imports, BaseHook constructor and build factory skeletons.",
            "lifecycle": "Hook phases, active stage values and execution order.",
            "state_access": "Core, stage, shared and extension state contracts.",
            "model_inference": "Traced student-model calls from a HookContext.",
            "final_decision": "How a Hook accepts or defers a parsed final answer.",
            "manifest": "Extension files, registration and evolution policy.",
        },
        "instruction": (
            "Read every topic relevant to the proposed Hook before writing its files."
        ),
    }


def _implementation() -> dict[str, Any]:
    return {
        "legal_core_imports": [
            "BaseHook",
            "ChatMessage",
            "FinalDecision",
            "FinalDecisionAction",
            "HookContext",
            "HookModelRequest",
            "HookPhase",
            "ModelInput",
            "StateRef",
        ],
        "forbidden_guesses": [
            "Context",
            "HookSpec",
            "HookDeclaration",
            "search_harness.framework.extensions",
        ],
        "rules": [
            "Import Hook runtime symbols from search_harness.core only.",
            "The entrypoint build(config, context) returns one BaseHook or an iterable of BaseHook instances.",
            "BaseHook subclasses implement handle(self, context: HookContext) -> None.",
            "Declare subscribed HookPhase values, writable stage keys, persistent StateRefs and model profiles in super().__init__.",
            "Do not invent wrapper specifications or return dictionaries describing a Hook.",
            "Do not use getattr, hasattr, setattr or delattr to probe runtime APIs; candidate validation rejects them.",
        ],
        "runtime_types": {
            "FinalDecision": {
                "fields": ["action", "answer", "feedback"],
                "constructors": [
                    "FinalDecision.accept(answer)",
                    "FinalDecision.defer(feedback)",
                ],
                "forbidden_guesses": ["is_accepted", "is_deferred"],
            },
            "FinalDecisionAction": ["ACCEPT", "DEFER"],
            "HookModelResponse": {
                "fields": ["raw_output", "metadata"],
                "methods": ["json_object()", "to_dict()"],
                "forbidden_guesses": ["error", "content", "text"],
            },
        },
        "minimal_plugin": (
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            "from search_harness.core import BaseHook, HookContext, HookPhase\n\n\n"
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
        "persistent_state_constructor": (
            "StateRef(\n"
            "    key='extension.example_hook.pending',\n"
            "    owner='example_hook',\n"
            "    value_type=bool,\n"
            "    writers=frozenset({'example_hook'}),\n"
            "    default=False,\n"
            ")"
        ),
    }


def _lifecycle() -> dict[str, Any]:
    return {
        "phases": [
            {"name": HookPhase.PRE_PROMPT, "stage_keys": []},
            {"name": HookPhase.POST_PROMPT, "stage_keys": ["stage.model_input"]},
            {"name": HookPhase.POST_MODEL, "stage_keys": ["stage.raw_model_output"]},
            {
                "name": HookPhase.POST_PARSE,
                "stage_keys": ["stage.parser_input", "stage.parsed_output"],
            },
            {"name": HookPhase.PRE_TOOL, "stage_keys": ["stage.tool_call"]},
            {
                "name": HookPhase.POST_TOOL,
                "stage_keys": ["stage.tool_call", "stage.tool_result"],
            },
            {
                "name": HookPhase.PRE_FINAL,
                "stage_keys": ["stage.final_decision"],
            },
            {"name": HookPhase.ON_ERROR, "stage_keys": ["stage.error"]},
        ],
        "rules": [
            "A Hook may read the complete visible state at every subscribed phase.",
            "A stage key exists only in its listed phase and is discarded immediately after that phase.",
            "Never read stage.model_input from POST_TOOL; it does not exist until the next POST_PROMPT.",
            "Read the original task from core.question instead of extracting it from stage.model_input.",
            "To carry a value across phases, copy it into a declared extension.* or shared.* StateRef.",
            "Only stage keys active in that phase can be declared writable.",
            "Hooks run in manifest order; multiple Hooks returned by one extension run in returned order.",
        ],
        "cross_phase_example": {
            "post_tool": "Set extension.<hook_id>.pending or store derived data from stage.tool_result.",
            "next_post_prompt": "Read the persistent key, modify stage.model_input, then clear the key.",
        },
    }


def _state_access() -> dict[str, Any]:
    return {
        "namespaces": {
            "core.*": "Read-only AgentState projection.",
            "stage.*": "Current phase values; writes require writable_stage_keys.",
            "shared.*": "Declared persistent cross-Hook state.",
            "extension.<hook_id>.*": "Declared persistent state owned by one Hook.",
        },
        "rules": [
            "Read with context.state.get(key).",
            "Write with context.state.set(key, replacement).",
            "Every persistent writable key requires a StateRef with an explicit writer.",
            "Do not mutate values returned by get(); set a replacement so the change is traced.",
            "stage.* is phase-local, not persistent state; never use it for cross-phase communication.",
            "core.question is readable at every phase and should be used for the original task text.",
            "core.* values are deep-copied AgentState.to_dict projections; nested messages and tool interactions are dictionaries, not ChatMessage or ToolInteraction objects.",
        ],
    }


def _model_inference() -> dict[str, Any]:
    return {
        "allowed_profiles": ["student"],
        "call_limit": "Default and recommended maximum is one call per Hook invocation.",
        "semantics": [
            "context.call_model performs one generation and never enters a nested AgentLoop.",
            "The model response does not affect the Actor until the Hook calls context.state.set().",
            "hook_model_output or hook_model_error records the complete request and result.",
            "Do not instantiate HTTP clients or OpenAICompatibleTextModel inside a plugin.",
            "Keep model prompts in UTF-8 files inside the extension directory.",
            "Parse the response explicitly and choose an explicit failure policy; the runtime never silently falls back.",
            "HookModelResponse has raw_output and metadata fields plus json_object() and to_dict() methods; it has no error field.",
        ],
        "example": (
            "response = context.call_model(\n"
            "    HookModelRequest(\n"
            "        profile='student',\n"
            "        purpose='judge_search_sufficiency',\n"
            "        model_input=ModelInput.from_messages([\n"
            "            ChatMessage(role='system', content=self.system_prompt),\n"
            "            ChatMessage(role='user', content=tool_result.content),\n"
            "        ]),\n"
            "    )\n"
            ")\n"
            "decision = response.json_object()\n"
            "context.state.set(self.decision_key, decision)"
        ),
        "base_hook_declaration": {
            "model_profiles": ["student"],
            "max_model_calls_per_invocation": 1,
        },
    }


def _manifest() -> dict[str, Any]:
    return {
        "required_files": [
            "extensions/<instance_id>/plugin.py",
            "extensions/<instance_id>/templates/<prompt_name>.md for model-driven Hooks",
            "harness.json registration",
        ],
        "registration": {
            "instance_id": "<instance_id>",
            "entrypoint": "extensions/<instance_id>/plugin.py:build",
            "enabled": True,
            "config": {},
            "evolution_policy": "mutable",
        },
        "rules": [
            "New model-created components must be mutable.",
            "The implementation and manifest registration belong to one file transaction.",
            "A component directory cannot be shared by multiple component instances.",
        ],
    }


def _final_decision() -> dict[str, Any]:
    return {
        "stage_key": "stage.final_decision",
        "decision_type": "FinalDecision",
        "actions": {
            "accept": "FinalDecision.accept(answer) completes the AgentLoop.",
            "defer": "FinalDecision.defer(feedback) continues on the next turn.",
        },
        "rules": [
            "Use PRE_FINAL when a Hook must enforce completion of its own strategy.",
            "Declare stage.final_decision in writable_stage_keys before replacing it.",
            "A deferred decision is terminal for the current phase and cannot be changed back to accept by a later Hook.",
            "Defer feedback is appended as a user message after the Actor's original output.",
            "A defer consumes the current step and remains bounded by core.max_steps.",
            "Do not fabricate invalid ParsedOutput values in POST_PARSE to delay completion.",
        ],
        "example": (
            "from search_harness.core import FinalDecision\n\n"
            "def handle(self, context):\n"
            "    status = context.state.get('extension.controller.status')\n"
            "    decision = context.state.get('stage.final_decision')\n"
            "    if status != 'completed':\n"
            "        context.state.set(\n"
            "            'stage.final_decision',\n"
            "            FinalDecision.defer('Complete the required workflow before answering.'),\n"
            "        )\n"
            "        return\n"
            "    context.state.set('stage.final_decision', FinalDecision.accept(decision.answer))"
        ),
    }


_TOPIC_BUILDERS = {
    "index": _index,
    "implementation": _implementation,
    "lifecycle": _lifecycle,
    "state_access": _state_access,
    "model_inference": _model_inference,
    "final_decision": _final_decision,
    "manifest": _manifest,
}
