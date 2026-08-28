"""面向新版 Compiler 的 Hook API 白名单与源码驱动查询。"""

from __future__ import annotations

import inspect
import types
from dataclasses import MISSING, dataclass, fields, is_dataclass
from difflib import get_close_matches
from enum import Enum
from math import ceil
from typing import Any, get_args, get_origin, get_type_hints

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    FinalDecision,
    FinalDecisionAction,
    HookContext,
    HookModelRequest,
    HookModelResponse,
    HookEditOperation,
    HookPhase,
    HookPromptOutput,
    HookPromptProduct,
    HookStateView,
    ModelInput,
    ParsedOutput,
    ParsedOutputKind,
    StateRef,
    ToolCall,
    ToolResult,
    TrajectoryEvent,
)
from search_harness.framework.harness import STAGE_KEYS_BY_PHASE

from .runtime_inputs import (
    RuntimeInputTopic,
    get_runtime_input_topic,
    list_runtime_input_topics,
    suggest_runtime_input_topics,
)


HOOK_API_CATALOG_VERSION = 4


@dataclass(frozen=True)
class _MemberPolicy:
    """一个显式公开成员的语义元数据。"""

    stability: str | None = None
    shape: str | None = None
    note: str = ""


@dataclass(frozen=True)
class _ObjectPolicy:
    """一个允许 Compiler 查询的源码对象。"""

    target: type[Any]
    category: str
    stability: str
    shape: str
    import_path: str | None
    fields: dict[str, _MemberPolicy]
    methods: dict[str, _MemberPolicy]
    note: str = ""


@dataclass(frozen=True)
class _StatePolicy:
    """一个 loop 管理的可见状态键。"""

    value_type: str
    category: str
    stability: str
    shape: str
    note: str


_OBJECTS: dict[str, _ObjectPolicy] = {
    "BaseHook": _ObjectPolicy(
        target=BaseHook,
        category="hook",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "hook_id": _MemberPolicy(note="Registered instance identifier."),
            "phases": _MemberPolicy(note="Subscribed HookPhase values."),
            "state_refs": _MemberPolicy(
                note="Persistent state declarations used by this Hook."
            ),
            "writable_stage_keys": _MemberPolicy(
                note="Active stage keys this Hook may replace."
            ),
            "model_profiles": _MemberPolicy(
                stability="experimental",
                note="Small-model profiles this Hook may call.",
            ),
            "max_model_calls_per_invocation": _MemberPolicy(
                stability="experimental",
                note="Per-phase invocation model-call limit.",
            ),
        },
        methods={
            "handle": _MemberPolicy(
                note=(
                    "Implement this method; the pipeline invokes it at each "
                    "subscribed phase."
                )
            )
        },
    ),
    "HookContext": _ObjectPolicy(
        target=HookContext,
        category="hook",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "hook_id": _MemberPolicy(),
            "phase": _MemberPolicy(),
            "state": _MemberPolicy(
                note=(
                    "Use HookStateView.get/set; do not mutate returned values "
                    "in place."
                )
            ),
            "trajectory": _MemberPolicy(
                stability="experimental",
                shape="open",
                note=(
                    "Read-only Trajectory Events emitted before this invocation."
                ),
            ),
        },
        methods={
            "call_model": _MemberPolicy(
                stability="experimental",
                note=(
                    "Run one bounded, traced model request without entering "
                    "another AgentLoop."
                ),
            ),
            "call_prompt_product": _MemberPolicy(
                stability="experimental",
                note=(
                    "Call one program-managed Prompt Product on its frozen "
                    "current-phase state projection. The Compiler applies the "
                    "returned value to the Mechanism target."
                ),
            ),
        },
    ),
    "HookStateView": _ObjectPolicy(
        target=HookStateView,
        category="state",
        stability="stable",
        shape="closed",
        import_path=None,
        fields={},
        methods={
            "get": _MemberPolicy(),
            "set": _MemberPolicy(),
        },
        note=(
            "Runtime-provided through HookContext.state. It is not a Component "
            "construction or import surface."
        ),
    ),
    "StateRef": _ObjectPolicy(
        target=StateRef,
        category="state",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "key": _MemberPolicy(),
            "owner": _MemberPolicy(),
            "value_type": _MemberPolicy(shape="open"),
            "writers": _MemberPolicy(),
            "default": _MemberPolicy(
                shape="open",
                note="Omit this argument when the persistent key has no default.",
            ),
        },
        methods={},
    ),
    "HookPhase": _ObjectPolicy(
        target=HookPhase,
        category="hook",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={},
        methods={},
    ),
    "ChatMessage": _ObjectPolicy(
        target=ChatMessage,
        category="message",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "role": _MemberPolicy(
                note="One of system, user, assistant, or tool."
            ),
            "content": _MemberPolicy(),
        },
        methods={},
    ),
    "ModelInput": _ObjectPolicy(
        target=ModelInput,
        category="message",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={"messages": _MemberPolicy()},
        methods={
            "from_messages": _MemberPolicy(
                note="Construct a ModelInput from an ordered message list."
            )
        },
    ),
    "HookModelRequest": _ObjectPolicy(
        target=HookModelRequest,
        category="model",
        stability="experimental",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "profile": _MemberPolicy(),
            "purpose": _MemberPolicy(),
            "model_input": _MemberPolicy(),
            "thinking_mode": _MemberPolicy(
                note=(
                    "Optional enabled/disabled override for this model call; "
                    "None inherits the selected profile configuration."
                )
            ),
        },
        methods={},
    ),
    "HookModelResponse": _ObjectPolicy(
        target=HookModelResponse,
        category="model",
        stability="experimental",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "raw_output": _MemberPolicy(),
            "metadata": _MemberPolicy(shape="open"),
        },
        methods={
            "json_object": _MemberPolicy(
                note="Parse raw_output as one JSON object or raise ValueError."
            )
        },
    ),
    "HookPromptProduct": _ObjectPolicy(
        target=HookPromptProduct,
        category="model",
        stability="experimental",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "product_ref": _MemberPolicy(),
            "phase": _MemberPolicy(),
            "task_kind": _MemberPolicy(),
            "inputs": _MemberPolicy(),
            "prompt": _MemberPolicy(
                note="Program-managed exact text; Compiler must not rewrite it."
            ),
            "thinking_mode": _MemberPolicy(),
            "response_adapter": _MemberPolicy(),
            "task_digest": _MemberPolicy(),
            "input_projection_digest": _MemberPolicy(),
            "prompt_digest": _MemberPolicy(),
            "model_profile": _MemberPolicy(),
        },
        methods={"from_dict": _MemberPolicy()},
    ),
    "HookPromptOutput": _ObjectPolicy(
        target=HookPromptOutput,
        category="model",
        stability="experimental",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "kind": _MemberPolicy(),
            "value": _MemberPolicy(
                shape="open",
                note=(
                    "Decision label, generated text, validated edit tuple, or "
                    "None according to the managed response adapter."
                ),
            ),
        },
        methods={},
        note=(
            "Private rollout state keys use "
            "extension.<owner_hook_id>.<name>; include the owner Hook in "
            "writers when it updates the key."
        ),
    ),
    "HookEditOperation": _ObjectPolicy(
        target=HookEditOperation,
        category="model",
        stability="experimental",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "operation": _MemberPolicy(),
            "block_id": _MemberPolicy(),
            "anchor_block_id": _MemberPolicy(),
            "position": _MemberPolicy(),
            "role": _MemberPolicy(),
            "content": _MemberPolicy(),
        },
        methods={"from_dict": _MemberPolicy()},
    ),
    "ToolCall": _ObjectPolicy(
        target=ToolCall,
        category="tool",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "name": _MemberPolicy(),
            "arguments": _MemberPolicy(shape="open"),
        },
        methods={},
    ),
    "ToolResult": _ObjectPolicy(
        target=ToolResult,
        category="tool",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "name": _MemberPolicy(),
            "content": _MemberPolicy(),
            "metadata": _MemberPolicy(
                shape="open",
                note=(
                    "Tool-specific metadata; inspect only keys required by "
                    "the mechanism."
                ),
            ),
        },
        methods={},
    ),
    "ParsedOutputKind": _ObjectPolicy(
        target=ParsedOutputKind,
        category="parser",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={},
        methods={},
    ),
    "ParsedOutput": _ObjectPolicy(
        target=ParsedOutput,
        category="parser",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "kind": _MemberPolicy(),
            "tool_call": _MemberPolicy(),
            "final_answer": _MemberPolicy(),
            "inband_thinking": _MemberPolicy(),
            "error": _MemberPolicy(),
        },
        methods={},
    ),
    "FinalDecisionAction": _ObjectPolicy(
        target=FinalDecisionAction,
        category="final",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={},
        methods={},
    ),
    "FinalDecision": _ObjectPolicy(
        target=FinalDecision,
        category="final",
        stability="stable",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "action": _MemberPolicy(),
            "answer": _MemberPolicy(),
            "feedback": _MemberPolicy(),
        },
        methods={
            "accept": _MemberPolicy(),
            "defer": _MemberPolicy(),
        },
    ),
    "TrajectoryEvent": _ObjectPolicy(
        target=TrajectoryEvent,
        category="trace",
        stability="experimental",
        shape="closed",
        import_path="search_harness.framework",
        fields={
            "index": _MemberPolicy(),
            "step": _MemberPolicy(),
            "event_type": _MemberPolicy(),
            "payload": _MemberPolicy(shape="open"),
        },
        methods={},
    ),
}


_STAGE_POLICIES: dict[str, _StatePolicy] = {
    "stage.model_input": _StatePolicy(
        "ModelInput",
        "stage",
        "stable",
        "closed",
        "The value used by the imminent model generation.",
    ),
    "stage.raw_model_output": _StatePolicy(
        "str",
        "stage",
        "stable",
        "closed",
        "Raw model text before parsing.",
    ),
    "stage.parser_input": _StatePolicy(
        "str",
        "stage",
        "stable",
        "closed",
        (
            "The text already consumed by the parser; replacing it does not "
            "re-run parsing."
        ),
    ),
    "stage.parsed_output": _StatePolicy(
        "ParsedOutput",
        "stage",
        "stable",
        "closed",
        "Parsed branch value consumed by the loop after POST_PARSE.",
    ),
    "stage.tool_call": _StatePolicy(
        "ToolCall",
        "stage",
        "stable",
        "closed",
        "At PRE_TOOL it controls execution; at POST_TOOL the call has already run.",
    ),
    "stage.tool_result": _StatePolicy(
        "ToolResult",
        "stage",
        "stable",
        "closed",
        "Tool result recorded into history after POST_TOOL.",
    ),
    "stage.final_decision": _StatePolicy(
        "FinalDecision",
        "stage",
        "stable",
        "closed",
        "Accept or defer the parsed final answer at PRE_FINAL.",
    ),
    "stage.error": _StatePolicy(
        "Exception",
        "stage",
        "stable",
        "open",
        "Terminal error visible at ON_ERROR; replacing it does not resume the run.",
    ),
}


_CORE_POLICIES: dict[str, _StatePolicy] = {
    "core.question": _StatePolicy(
        "str", "core", "stable", "closed", "Original task text."
    ),
    "core.max_steps": _StatePolicy(
        "int", "core", "stable", "closed", "Configured rollout step limit."
    ),
    "core.step": _StatePolicy(
        "int", "core", "stable", "closed", "Current one-based loop step."
    ),
    "core.status": _StatePolicy(
        "str", "core", "stable", "closed", "Current RunStatus value."
    ),
    "core.error": _StatePolicy(
        "str | None",
        "core",
        "experimental",
        "closed",
        "Terminal error text when one has been recorded.",
    ),
    "core.model_inputs": _StatePolicy(
        "list[dict[str, Any]]",
        "core",
        "experimental",
        "open",
        "Serialized prior ModelInput values.",
    ),
    "core.model_outputs": _StatePolicy(
        "list[str]",
        "core",
        "experimental",
        "closed",
        "Raw prior model outputs.",
    ),
    "core.parsed_outputs": _StatePolicy(
        "list[dict[str, Any]]",
        "core",
        "experimental",
        "open",
        (
            "Serialized cumulative ParsedOutput values for history analysis. "
            "At PRE_FINAL use stage.final_decision for the active candidate."
        ),
    ),
    "core.tool_interactions": _StatePolicy(
        "list[dict[str, Any]]",
        "core",
        "experimental",
        "open",
        (
            "Serialized completed pairs with shape "
            "{'tool_call': {'name': str, 'arguments': dict}, "
            "'tool_result': {'name': str, 'content': str}}. "
            "At POST_TOOL this excludes the current stage call/result; at "
            "PRE_FINAL it includes all interactions committed before the "
            "current Hook invocation. This is the preferred Tool history API."
        ),
    ),
    "core.conversation_messages": _StatePolicy(
        "list[dict[str, str]]",
        "core",
        "experimental",
        "open",
        (
            "Serialized follow-up messages with role/content fields retained "
            "for later prompts. At POST_TOOL this includes prior deferred "
            "feedback but excludes the current result. Tool results may be "
            "represented as user-role messages; do not use message roles as "
            "a semantic Tool Result protocol."
        ),
    ),
    "core.hook_state": _StatePolicy(
        "dict[str, Any]",
        "core",
        "experimental",
        "open",
        "Serialized persistent extension/shared state. Prefer declared state keys.",
    ),
}


def list_hook_api_symbols(
    *,
    category: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """列出 Compiler 可查询的 Hook API，不暴露实现成员。"""

    categories = _categories()
    if category not in categories:
        raise ValueError(
            f"unsupported Hook API category: {category}; "
            f"expected one of {categories}"
        )
    if page < 1:
        raise ValueError("Hook API page must be positive")
    if not 1 <= page_size <= 50:
        raise ValueError("Hook API page_size must be between 1 and 50")

    items = _symbol_summaries()
    if category != "all":
        items = [item for item in items if item["category"] == category]
    total_items = len(items)
    total_pages = max(1, ceil(total_items / page_size))
    start = (page - 1) * page_size
    return {
        "catalog_version": HOOK_API_CATALOG_VERSION,
        "category": category,
        "categories": list(categories),
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "items": items[start : start + page_size],
        "stability_semantics": {
            "stable": "Compiler may rely on the documented signature and semantics.",
            "experimental": (
                "Usable, but query the exact member and avoid assumptions "
                "beyond it."
            ),
        },
        "shape_semantics": {
            "closed": "The documented fields or values are the complete contract.",
            "open": (
                "The container may include component- or provider-specific "
                "content."
            ),
        },
    }


def query_hook_api(symbol: str) -> dict[str, Any]:
    """精确查询一个公开类、成员或状态键的当前源码契约。"""

    normalized = symbol.strip()
    if not normalized:
        raise ValueError("Hook API symbol must not be empty")

    state_policy = _STAGE_POLICIES.get(normalized) or _CORE_POLICIES.get(
        normalized
    )
    if state_policy is not None:
        return _state_payload(normalized, state_policy)

    object_name, separator, member_name = normalized.partition(".")
    policy = _OBJECTS.get(object_name)
    if policy is None:
        raise ValueError(
            f"Hook API symbol is not public or does not exist: {normalized}"
        )
    if not separator:
        return _object_payload(object_name, policy)
    if member_name.startswith("_"):
        raise ValueError(f"Hook API member is internal and not exposed: {normalized}")
    return _member_payload(object_name, member_name, policy)


def query_hook_api_reference(query: str) -> dict[str, Any]:
    """查询 Topic 或精确 symbol，并为未知查询返回可操作建议。"""

    normalized = query.strip()
    if not normalized:
        return {"status": "rejected", "reason": "empty_query"}
    try:
        topic = get_runtime_input_topic(normalized)
    except ValueError:
        topic = None
    if topic is not None:
        return {
            "status": "resolved",
            "query_kind": "runtime_input_topic",
            "query": normalized,
            "document": runtime_input_topic_document(topic.topic_id),
        }
    try:
        contract = query_hook_api(normalized)
    except ValueError:
        symbol_candidates = get_close_matches(
            normalized,
            [item["symbol"] for item in _symbol_summaries()],
            n=6,
            cutoff=0.3,
        )
        return {
            "status": "rejected",
            "reason": "unknown_query",
            "query": normalized,
            "runtime_input_suggestions": suggest_runtime_input_topics(normalized),
            "symbol_suggestions": symbol_candidates,
        }
    return {
        "status": "resolved",
        "query_kind": "symbol",
        "query": normalized,
        "contract": contract,
        "native_reference": _render_native_contract(contract),
        "related_runtime_inputs": [
            topic.topic_id
            for topic in list_runtime_input_topics()
            if normalized in topic.symbols
        ],
    }


def runtime_input_topic_document(topic_id: str) -> dict[str, Any]:
    """把一个受控 Topic 渲染为 Compiler 可直接使用的完整文档。"""

    topic = get_runtime_input_topic(topic_id)
    contracts = [query_hook_api(symbol) for symbol in topic.symbols]
    return {
        "runtime_input_id": topic.topic_id,
        "description": topic.description,
        "preferred_usage": list(topic.preferred_usage),
        "avoid": list(topic.avoid),
        "lifecycle_notes": list(topic.lifecycle_notes),
        "symbols": list(topic.symbols),
        "native_reference": _render_runtime_input_topic(topic, contracts),
    }


def public_hook_imports() -> list[str]:
    """返回 Compiler 可从 ``search_harness.framework`` 导入的公开符号。"""

    return sorted(
        name
        for name, policy in _OBJECTS.items()
        if policy.import_path == "search_harness.framework"
    )


def hook_api_categories() -> tuple[str, ...]:
    """返回公开目录当前支持的查询分类。"""

    return _categories()


def _render_runtime_input_topic(
    topic: RuntimeInputTopic,
    contracts: list[dict[str, Any]],
) -> str:
    """生成紧凑的 Python-native Topic 文档。"""

    lines = [
        f"# Runtime Input Topic: {topic.topic_id}",
        f"# {topic.description}",
        "# Preferred usage:",
        *(f"# - {item}" for item in topic.preferred_usage),
    ]
    if topic.lifecycle_notes:
        lines.extend(
            ["# Lifecycle semantics:", *(f"# - {item}" for item in topic.lifecycle_notes)]
        )
    lines.extend(["# Avoid:", *(f"# - {item}" for item in topic.avoid)])
    if topic.topic_id == "tool":
        lines.extend(
            [
                "class SerializedToolCall(TypedDict):",
                "    name: str  # Registered Tool instance ID.",
                "    arguments: dict[str, Any]  # Validated execution arguments.",
                "class SerializedToolResult(TypedDict):",
                "    name: str  # Tool instance that produced this result.",
                "    content: str  # Student-visible result; format is Tool-specific.",
                "class CompletedToolInteraction(TypedDict):",
                "    tool_call: SerializedToolCall",
                "    tool_result: SerializedToolResult",
            ]
        )
    lines.extend(_render_native_contract(contract) for contract in contracts)
    return "\n".join(lines)


def _render_native_contract(contract: dict[str, Any]) -> str:
    """把一个结构化白名单契约渲染为紧凑 Python 签名。"""

    kind = contract.get("kind")
    symbol = str(contract.get("symbol"))
    note = str(contract.get("note") or contract.get("summary") or "").strip()
    if kind == "state_key":
        phases = contract.get("phases")
        phase_text = (
            f" Available phases: {', '.join(str(item) for item in phases)}."
            if isinstance(phases, list) and phases
            else ""
        )
        return (
            f"def context.state.get(key: Literal[{symbol!r}]) -> {contract['type']}:\n"
            f"    \"\"\"{note}{phase_text} Read: {contract['read']}\n"
            f"    Write: {contract['write']}\"\"\"\n"
            "    ..."
        )
    if kind in {"class", "runtime_view"}:
        lines = [f"class {symbol}:"]
        if note:
            lines.append(f"    \"\"\"{note}\"\"\"")
        signature = contract.get("signature")
        if isinstance(signature, str):
            lines.append(f"    # Constructor: {signature}")
        for field in contract.get("fields", []):
            if isinstance(field, dict):
                suffix = f"  # {field['note']}" if field.get("note") else ""
                lines.append(f"    {str(field['symbol']).split('.')[-1]}: {field['type']}{suffix}")
        for method in contract.get("methods", []):
            if isinstance(method, dict):
                method_note = method.get("note") or method.get("summary") or ""
                lines.append(f"    def {method['signature']}: ...  # {method_note}".rstrip())
        if len(lines) == 1:
            lines.append("    ...")
        return "\n".join(lines)
    if kind in {"method", "field", "constant", "enum_value"}:
        signature = contract.get("signature") or contract.get("type") or "Any"
        return f"{symbol}: {signature}  # {note}".rstrip()
    return f"# {symbol}: {note}".rstrip()


def _categories() -> tuple[str, ...]:
    values = {
        *(policy.category for policy in _OBJECTS.values()),
        *(_STAGE_POLICIES[key].category for key in _STAGE_POLICIES),
        *(_CORE_POLICIES[key].category for key in _CORE_POLICIES),
    }
    return ("all", *sorted(values))


def _symbol_summaries() -> list[dict[str, Any]]:
    items = [
        {
            "symbol": name,
            "kind": _object_kind(policy),
            "category": policy.category,
            "stability": policy.stability,
            "shape": policy.shape,
            "summary": _first_line(inspect.getdoc(policy.target)) or policy.note,
        }
        for name, policy in _OBJECTS.items()
    ]
    for key, policy in {**_STAGE_POLICIES, **_CORE_POLICIES}.items():
        items.append(
            {
                "symbol": key,
                "kind": "state_key",
                "category": policy.category,
                "stability": policy.stability,
                "shape": policy.shape,
                "summary": policy.note,
            }
        )
    return sorted(items, key=lambda item: item["symbol"].casefold())


def _object_payload(name: str, policy: _ObjectPolicy) -> dict[str, Any]:
    target = policy.target
    payload: dict[str, Any] = {
        "catalog_version": HOOK_API_CATALOG_VERSION,
        "symbol": name,
        "kind": _object_kind(policy),
        "category": policy.category,
        "stability": policy.stability,
        "shape": policy.shape,
        "import": (
            f"from {policy.import_path} import {name}"
            if policy.import_path is not None
            else None
        ),
        "summary": inspect.getdoc(target) or "",
        "note": policy.note or None,
        "generated_from_source": True,
    }
    if is_dataclass(target):
        payload["signature"] = _format_signature(name, target)
        payload["fields"] = [
            _field_payload(name, field.name, policy)
            for field in fields(target)
            if field.name in policy.fields
        ]
    elif issubclass(target, Enum):
        payload["values"] = [
            {"name": item.name, "value": item.value} for item in target
        ]
    elif target is HookPhase:
        payload["values"] = [
            {"name": key, "value": value}
            for key, value in vars(target).items()
            if key.isupper() and key != "ALL" and isinstance(value, str)
        ]
    if policy.methods:
        payload["methods"] = [
            _method_payload(name, method_name, policy)
            for method_name in policy.methods
        ]
    return payload


def _member_payload(
    object_name: str,
    member_name: str,
    policy: _ObjectPolicy,
) -> dict[str, Any]:
    if policy.target is HookPhase:
        value = vars(policy.target).get(member_name)
        if member_name != "ALL" and member_name.isupper() and isinstance(value, str):
            return {
                "catalog_version": HOOK_API_CATALOG_VERSION,
                "symbol": f"{object_name}.{member_name}",
                "kind": "constant",
                "owner": object_name,
                "type": "str",
                "value": value,
                "stability": policy.stability,
                "shape": policy.shape,
                "generated_from_source": True,
            }
    if issubclass(policy.target, Enum) and member_name in policy.target.__members__:
        value = policy.target.__members__[member_name]
        return {
            "catalog_version": HOOK_API_CATALOG_VERSION,
            "symbol": f"{object_name}.{member_name}",
            "kind": "enum_value",
            "owner": object_name,
            "value": value.value,
            "stability": policy.stability,
            "shape": policy.shape,
            "generated_from_source": True,
        }
    if member_name in policy.fields:
        return _field_payload(object_name, member_name, policy)
    if member_name in policy.methods:
        return _method_payload(object_name, member_name, policy)
    raise ValueError(
        "Hook API member is not part of the public Compiler-facing contract: "
        f"{object_name}.{member_name}"
    )


def _field_payload(
    object_name: str,
    member_name: str,
    policy: _ObjectPolicy,
) -> dict[str, Any]:
    target = policy.target
    hints = get_type_hints(target, include_extras=True)
    dataclass_fields = {item.name: item for item in fields(target)}
    field = dataclass_fields[member_name]
    member_policy = policy.fields[member_name]
    payload = {
        "catalog_version": HOOK_API_CATALOG_VERSION,
        "symbol": f"{object_name}.{member_name}",
        "kind": "field",
        "owner": object_name,
        "type": _format_type(hints.get(member_name, field.type)),
        "stability": member_policy.stability or policy.stability,
        "shape": member_policy.shape or policy.shape,
        "note": member_policy.note or None,
        "generated_from_source": True,
    }
    default = _field_default(field)
    if default is not None:
        payload["default"] = default
    return payload


def _method_payload(
    object_name: str,
    member_name: str,
    policy: _ObjectPolicy,
) -> dict[str, Any]:
    method = getattr(policy.target, member_name)
    member_policy = policy.methods[member_name]
    return {
        "catalog_version": HOOK_API_CATALOG_VERSION,
        "symbol": f"{object_name}.{member_name}",
        "kind": "method",
        "owner": object_name,
        "signature": _format_signature(member_name, method),
        "stability": member_policy.stability or policy.stability,
        "shape": member_policy.shape or policy.shape,
        "summary": inspect.getdoc(method) or "",
        "note": member_policy.note or None,
        "generated_from_source": True,
    }


def _state_payload(symbol: str, policy: _StatePolicy) -> dict[str, Any]:
    payload = {
        "catalog_version": HOOK_API_CATALOG_VERSION,
        "symbol": symbol,
        "kind": "state_key",
        "category": policy.category,
        "type": policy.value_type,
        "stability": policy.stability,
        "shape": policy.shape,
        "read": f"context.state.get({symbol!r})",
        "write": (
            "core values are read-only"
            if policy.category == "core"
            else (
                f"declare {symbol!r} in BaseHook.writable_stage_keys, then use "
                f"context.state.set({symbol!r}, replacement)"
            )
        ),
        "note": policy.note,
    }
    if policy.category == "stage":
        payload["phases"] = [
            phase
            for phase, keys in STAGE_KEYS_BY_PHASE.items()
            if symbol in keys
        ]
    return payload


def _object_kind(policy: _ObjectPolicy) -> str:
    if policy.target is HookPhase:
        return "constants"
    if issubclass(policy.target, Enum):
        return "enum"
    if policy.target is HookStateView:
        return "runtime_view"
    return "class"


def _format_signature(name: str, target: Any) -> str:
    signature = inspect.signature(target)
    try:
        hints = get_type_hints(target, include_extras=True)
    except TypeError:
        hints = {}
    parameters = []
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        annotation = hints.get(parameter.name, parameter.annotation)
        text = parameter.name
        if annotation is not inspect.Parameter.empty:
            text += f": {_format_type(annotation)}"
        if parameter.default is not inspect.Parameter.empty:
            text += f" = {_format_default(parameter.default)}"
        parameters.append(text)
    return_annotation = hints.get("return", signature.return_annotation)
    suffix = (
        ""
        if return_annotation is inspect.Signature.empty
        else f" -> {_format_type(return_annotation)}"
    )
    return f"{name}({', '.join(parameters)}){suffix}"


def _format_type(annotation: Any) -> str:
    if annotation is Any:
        return "Any"
    if annotation is None or annotation is type(None):
        return "None"
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, types.UnionType):
        return " | ".join(_format_type(item) for item in get_args(annotation))

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is not None:
        if origin is types.UnionType:
            return " | ".join(_format_type(item) for item in arguments)
        name = getattr(origin, "__name__", str(origin).replace("typing.", ""))
        if arguments:
            rendered = ", ".join(
                "..." if item is Ellipsis else _format_type(item)
                for item in arguments
            )
            return f"{name}[{rendered}]"
        return name
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _field_default(field: Any) -> str | None:
    if field.default is not MISSING:
        return _format_default(field.default)
    if field.default_factory is not MISSING:
        return f"{field.default_factory.__name__}()"
    return None


def _format_default(value: Any) -> str:
    if type(value) is object:
        return "<internal sentinel>"
    return repr(value)


def _first_line(value: str | None) -> str:
    return value.splitlines()[0] if value else ""
