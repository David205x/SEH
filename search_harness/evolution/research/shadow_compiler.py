"""Shadow Compiler packet and managed Prompt Product lowering."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .mechanism.hook_api import HOOK_API_CATALOG_VERSION, query_hook_api
from .roles.contracts import (
    ShadowCompilerInput,
    ShadowDecisionTask,
    ShadowHookPromptProduct,
)


_BASE_SYMBOLS = (
    "BaseHook",
    "HookContext",
    "HookStateView.get",
    "HookStateView.set",
    "StateRef",
)
_PHASE_SYMBOLS = {
    "post_prompt": ("HookPhase.POST_PROMPT", "stage.model_input", "ModelInput"),
    "post_model": ("HookPhase.POST_MODEL", "stage.raw_model_output"),
    "post_parse": (
        "HookPhase.POST_PARSE",
        "stage.parser_input",
        "stage.parsed_output",
        "ParsedOutput",
    ),
    "pre_tool": ("HookPhase.PRE_TOOL", "stage.tool_call", "ToolCall"),
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
        "FinalDecisionAction",
    ),
}
_PROMPT_SYMBOLS = (
    "BaseHook.model_profiles",
    "BaseHook.max_model_calls_per_invocation",
    "HookContext.call_prompt_product",
    "HookPromptProduct",
    "HookPromptOutput",
    "HookEditOperation",
)
_KEEP_CONTRACT_KEYS = frozenset(
    {
        "symbol",
        "kind",
        "type",
        "signature",
        "import",
        "summary",
        "stability",
        "shape",
        "fields",
        "methods",
        "values",
        "read",
        "write",
        "phases",
        "note",
        "default",
    }
)


def build_managed_prompt_products(
    compiler_input: ShadowCompilerInput,
) -> dict[str, dict[str, Any]]:
    """Build immutable runtime payloads keyed by Hook phase."""

    phase_tasks = {
        phase.phase: phase.task for phase in compiler_input.mechanism.phases
    }
    return {
        product.phase: _managed_product_payload(
            product=product,
            task=phase_tasks[product.phase],
        )
        for product in compiler_input.prompt_products
    }


def build_shadow_compiler_capability_packet(
    compiler_input: ShadowCompilerInput,
) -> dict[str, Any]:
    """Build one compact source-derived packet for a Shadow Mechanism."""

    managed = build_managed_prompt_products(compiler_input)
    symbols = list(_BASE_SYMBOLS)
    phase_views = []
    for phase in compiler_input.mechanism.phases:
        symbols.extend(_PHASE_SYMBOLS[phase.phase])
        for item in phase.task.inputs:
            symbols.extend(
                source
                for source in item.sources
                if source.startswith(("core.", "stage."))
            )
        for text in (
            *phase.guards,
            phase.on_success,
            phase.fallback.default,
            phase.fallback.uncertain or "",
            phase.fallback.exhausted or "",
        ):
            symbols.extend(
                re.findall(
                    r"\b(?:core|stage)\.[A-Za-z_][A-Za-z0-9_]*\b",
                    text,
                )
            )
        binding = managed.get(phase.phase)
        if binding is not None:
            symbols.extend(_PROMPT_SYMBOLS)
        phase_views.append(
            {
                "phase": phase.phase,
                "guards": list(phase.guards),
                "task": phase.task.model_dump(mode="json"),
                "on_success": phase.on_success,
                "fallback": phase.fallback.model_dump(mode="json"),
                "activation_limit": phase.activation_limit,
                "prompt_product_ref": (
                    binding["product_ref"] if binding is not None else None
                ),
            }
        )
    contracts = []
    unresolved = []
    for symbol in dict.fromkeys(symbols):
        try:
            contracts.append(_compact_contract(query_hook_api(symbol)))
        except ValueError:
            unresolved.append(symbol)
    return {
        "packet_version": 1,
        "catalog_versions": {"hook_api": HOOK_API_CATALOG_VERSION},
        "selection": {
            "strategy": "shadow_phase_task_exact",
            "phases": phase_views,
            "managed_hook_prompts": {
                phase: payload["product_ref"]
                for phase, payload in managed.items()
            },
            "unresolved_symbols": unresolved,
        },
        "contracts": contracts,
        "runtime_input_documents": [],
        "authoring": {
            "query_policy": [
                "Additional public contracts already contain the complete "
                "selected API for this Mechanism.",
                "Do not query a symbol already present in the capability "
                "packet.",
                "Use at most three exact queries, only for an absent symbol "
                "required by the implementation.",
            ],
            "prompt_product_rules": [
                "Call bind_hook_prompt_products after registering the target extension.",
                "Import PROMPT_PRODUCTS from the generated sibling module.",
                "Call context.call_prompt_product(PROMPT_PRODUCTS[context.phase]) only after deterministic guards pass.",
                "Do not construct HookModelRequest, model messages, Prompt text, thinking mode, or response parsing for a managed Prompt phase.",
                "Apply HookPromptOutput.value only to the exact target and scope declared by on_success; the Prompt Product never mutates Hook state.",
            ],
            "result_contracts": {
                "decision": (
                    "value is positive, negative, or uncertain; only positive "
                    "executes on_success"
                ),
                "generation": (
                    "value is non-empty generated text or None; Compiler applies "
                    "the declared replacement scope and preservation rules"
                ),
                "structured_edit": (
                    "value is a tuple of validated HookEditOperation values or "
                    "None; Compiler validates declared target scope before applying"
                ),
            },
            "component_rules": [
                "Produce one extension for the complete Mechanism.",
                "Declare only stage keys actually replaced in "
                "writable_stage_keys.",
                "Declare model profile student and enough per-invocation "
                "calls for managed Prompt phases.",
                "Treat activation_limit as the maximum successful on_success "
                "executions per rollout, not as a model-call limit or an "
                "assumption about later Student behavior.",
                "Implement activation_limit with an extension-local integer "
                "StateRef even when Mechanism state is empty: check it before "
                "the Task and increment it in the same Hook transaction as "
                "on_success.",
                "Read public dataclass fields directly; do not use getattr or "
                "other dynamic attribute access.",
                "A Component factory validates its config mapping and may "
                "leave an unused runtime context parameter untouched; do not "
                "consume factory parameters with dummy del statements.",
                "Register the extension in harness.json and mark it mutable "
                "in evolution.json.",
                "Append harness.json.extensions with instance_id, entrypoint "
                "extensions/<instance_id>/component.py:build, and config; set "
                "evolution.json.components[instance_id] to mutable.",
            ],
        },
    }


def _managed_product_payload(
    *,
    product: ShadowHookPromptProduct,
    task: Any,
) -> dict[str, Any]:
    task_kind = (
        "decision"
        if isinstance(task, ShadowDecisionTask)
        else (
            "structured_edit"
            if product.response_adapter == "structured_edit"
            else "generation"
        )
    )
    prompt_digest = hashlib.sha256(product.prompt.encode("utf-8")).hexdigest()
    identity = {
        "phase": product.phase,
        "task_kind": task_kind,
        "inputs": [item.model_dump(mode="json") for item in task.inputs],
        "prompt": product.prompt,
        "thinking_mode": product.thinking_mode,
        "response_adapter": product.response_adapter,
        "task_digest": product.task_digest,
        "input_projection_digest": product.input_projection_digest,
        "prompt_digest": prompt_digest,
        "model_profile": "student",
    }
    digest = hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "product_ref": f"hook_prompt_{digest[:16]}",
        **identity,
    }


def _compact_contract(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key in _KEEP_CONTRACT_KEYS
    }
