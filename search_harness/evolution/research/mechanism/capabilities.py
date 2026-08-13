"""为单个机制生成源码驱动的 Compiler 能力包。"""

from __future__ import annotations

from typing import Any

from ..roles.contracts import MechanismSpec
from .hook_api import HOOK_API_CATALOG_VERSION, query_hook_api
from .hook_api import runtime_input_topic_document
from .hook_authoring import (
    HOOK_AUTHORING_API_VERSION,
    get_hook_authoring_guide,
)
from .runtime_inputs import REFERENCE_MODEL_GATED_FINAL_HOOK, get_runtime_input_topic


_PHASE_SYMBOLS = {
    "pre_prompt": ("HookPhase.PRE_PROMPT",),
    "post_prompt": (
        "HookPhase.POST_PROMPT",
        "stage.model_input",
        "ModelInput",
        "ModelInput.from_messages",
        "ChatMessage",
    ),
    "post_model": (
        "HookPhase.POST_MODEL",
        "stage.raw_model_output",
    ),
    "post_parse": (
        "HookPhase.POST_PARSE",
        "stage.parser_input",
        "stage.parsed_output",
        "ParsedOutput",
        "ParsedOutputKind",
    ),
    "pre_tool": (
        "HookPhase.PRE_TOOL",
        "stage.tool_call",
        "ToolCall",
    ),
    "post_tool": (
        "HookPhase.POST_TOOL",
        "stage.tool_call",
        "stage.tool_result",
        "ToolCall",
        "ToolResult",
    ),
    "pre_final": (
        "HookPhase.PRE_FINAL",
        "stage.final_decision",
        "FinalDecision",
        "FinalDecision.defer",
    ),
    "on_error": (
        "HookPhase.ON_ERROR",
        "stage.error",
    ),
}

_BASE_SYMBOLS = (
    "BaseHook",
    "HookContext",
    "StateRef",
    "HookStateView.get",
    "HookStateView.set",
)

_MODEL_SYMBOLS = (
    "BaseHook.model_profiles",
    "BaseHook.max_model_calls_per_invocation",
    "ChatMessage",
    "ModelInput",
    "ModelInput.from_messages",
    "HookContext.call_model",
    "HookModelRequest",
    "HookModelResponse",
    "HookModelResponse.json_object",
)

_KEEP_CONTRACT_KEYS = frozenset(
    {
        "symbol",
        "kind",
        "type",
        "signature",
        "import",
        "stability",
        "shape",
        "fields",
        "methods",
        "values",
        "read",
        "write",
        "phases",
        "note",
    }
)

_MEMBER_SELECTIONS = {
    "BaseHook": {
        "fields": {
            "BaseHook.hook_id",
            "BaseHook.phases",
            "BaseHook.state_refs",
            "BaseHook.writable_stage_keys",
        },
        "methods": {"BaseHook.handle"},
    },
    "HookContext": {
        "fields": {"HookContext.state"},
        "methods": set(),
    },
}

_DROP_NESTED_KEYS = frozenset(
    {"catalog_version", "generated_from_source", "owner", "summary"}
)


def build_compiler_capability_packet(
    mechanism: MechanismSpec,
) -> dict[str, Any]:
    """按所有 Hook phase 和显式能力需求选择最小公开 API 契约。"""

    phase_selections = []
    phase_symbols: list[str] = []
    all_exact_inputs: list[str] = []
    runtime_input_ids: list[str] = []
    for rule in mechanism.phase_rules:
        phase = rule.phase.strip().casefold()
        try:
            phase_symbols.extend(_PHASE_SYMBOLS[phase])
        except KeyError as exc:
            raise ValueError(f"unsupported Hook phase: {phase}") from exc
        exact_inputs = [
            value
            for value in rule.decision_inputs
            if value.startswith(("core.", "stage."))
        ]
        semantic_inputs = [
            value
            for value in rule.decision_inputs
            if value not in exact_inputs
        ]
        for topic_id in rule.runtime_inputs:
            topic = get_runtime_input_topic(topic_id)
            phase_symbols.extend(topic.symbols)
            runtime_input_ids.append(topic.topic_id)
        all_exact_inputs.extend(exact_inputs)
        phase_selections.append(
            {
                "phase": phase,
                "guards": list(rule.guards),
                "decision_evaluator": rule.decision_evaluator,
                "decision_contract": rule.decision_contract.model_dump(
                    mode="json"
                ),
                "fallback": rule.fallback.model_dump(mode="json"),
                "activation_budget": rule.activation_budget,
                "exact_decision_inputs": exact_inputs,
                "semantic_decision_inputs": semantic_inputs,
                "runtime_inputs": list(rule.runtime_inputs),
            }
        )
    (
        exact_capabilities,
        semantic_capabilities,
        unresolved_capabilities,
    ) = _classify_required_capabilities(
        mechanism.required_capabilities
    )
    model_symbols = (
        _MODEL_SYMBOLS if _requires_model_inference(mechanism) else ()
    )
    symbols = list(
        dict.fromkeys(
            (
                *_BASE_SYMBOLS,
                *phase_symbols,
                *all_exact_inputs,
                *exact_capabilities,
                *model_symbols,
            )
        )
    )
    contracts = []
    unresolved_symbols = []
    for symbol in symbols:
        try:
            contracts.append(_compact_contract(query_hook_api(symbol)))
        except ValueError:
            unresolved_symbols.append(symbol)

    implementation = get_hook_authoring_guide("implementation")
    state_access = get_hook_authoring_guide("state_access")
    manifest = get_hook_authoring_guide("manifest")
    return {
        "packet_version": 9,
        "catalog_versions": {
            "hook_api": HOOK_API_CATALOG_VERSION,
            "authoring_guide": HOOK_AUTHORING_API_VERSION,
        },
        "selection": {
            "strategy": "multi_phase_scoped_exact",
            "phase_rules": phase_selections,
            "exact_required_capabilities": exact_capabilities,
            "semantic_required_capabilities": semantic_capabilities,
            "unresolved_api_capabilities": unresolved_capabilities,
            "unresolved_symbols": unresolved_symbols,
            "unresolved_runtime_inputs": [],
        },
        "contracts": contracts,
        "runtime_input_documents": [
            runtime_input_topic_document(topic_id)
            for topic_id in dict.fromkeys(runtime_input_ids)
        ],
        "authoring": {
            "factory_rules": [
                *implementation["rules"][:4],
                (
                    "Reject non-empty config explicitly when the component "
                    "supports no options."
                ),
                (
                    "Do not add del statements, dummy reads, or no-op "
                    "assignments for factory parameters."
                ),
            ],
            "state_namespaces": state_access["namespaces"],
            "state_rules": state_access["rules"],
            "manifest_changes": manifest["required_changes"],
            "manifest_rules": manifest["rules"],
            "compiler_review_rules": [
                (
                    "Use explicit isinstance checks before accessing fields on "
                    "stage.model_input, stage.tool_call, or stage.tool_result."
                ),
                (
                    "At POST_TOOL, append feedback for the next Student "
                    "generation by replacing stage.tool_result with a "
                    "ToolResult whose content includes the feedback; the "
                    "Loop records that content as the next user-role message."
                ),
                "Do not catch Exception or BaseException.",
                (
                    "A build(config, context) factory must validate or consume "
                    "its config mapping."
                ),
            ],
            **_model_authoring([*exact_capabilities, *model_symbols]),
            **(
                {"reference_hook": REFERENCE_MODEL_GATED_FINAL_HOOK}
                if _requires_model_inference(mechanism)
                and any(rule.phase == "pre_final" for rule in mechanism.phase_rules)
                else {}
            ),
        },
    }


def _compact_contract(contract: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: value
        for key, value in contract.items()
        if key in _KEEP_CONTRACT_KEYS and value not in (None, "", [], {})
    }
    selection = _MEMBER_SELECTIONS.get(str(contract.get("symbol")))
    if selection is not None:
        for collection in ("fields", "methods"):
            if collection in compact:
                compact[collection] = [
                    item
                    for item in compact[collection]
                    if item.get("symbol") in selection[collection]
                ]
    return _strip_nested_metadata(compact)


def _strip_nested_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_nested_metadata(item)
            for key, item in value.items()
            if key not in _DROP_NESTED_KEYS and item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_strip_nested_metadata(item) for item in value]
    return value


def _classify_required_capabilities(
    values: list[str],
) -> tuple[list[str], list[str], list[str]]:
    exact = []
    semantic = []
    unresolved = []
    for value in values:
        try:
            query_hook_api(value)
        except ValueError:
            if _looks_like_api_symbol(value):
                unresolved.append(value)
            else:
                semantic.append(value)
        else:
            exact.append(value)
    return exact, semantic, unresolved


def _looks_like_api_symbol(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    return value.startswith(("core.", "stage.")) or "." in value or (
        bool(value) and value[0].isupper()
    )


def _requires_model_inference(mechanism: MechanismSpec) -> bool:
    if any(
        rule.decision_evaluator == "hook_model"
        for rule in mechanism.phase_rules
    ):
        return True
    text = " ".join(
        [
            *(rule.action for rule in mechanism.phase_rules),
            mechanism.behavioral_pseudocode,
            *mechanism.required_capabilities,
        ]
    ).casefold()
    return any(
        marker in text
        for marker in (
            "hook model",
            "hook-model",
            "model call",
            "call_model",
            "student profile",
            "student-profile",
        )
    )


def _model_authoring(exact_capabilities: list[str]) -> dict[str, Any]:
    if not any(
        value.startswith(
            ("HookModel", "HookContext.call_model", "BaseHook.model")
        )
        for value in exact_capabilities
    ):
        return {}
    guide = get_hook_authoring_guide("model_inference")
    return {
        "allowed_model_profiles": ["student"],
        "model_inference_rules": guide["rules"],
    }
