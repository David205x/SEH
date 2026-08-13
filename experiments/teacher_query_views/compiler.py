"""Model-visible views for the shadow Compiler experiment."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from search_harness.evolution.research.resources.base import TeacherResources


_POST_TOOL_MODEL_REFERENCE = '''\
"""Reference pattern: one-shot model-gated POST_TOOL result guidance."""
from __future__ import annotations
import json
from typing import Any
from search_harness.framework import BaseHook, ChatMessage, HookContext, HookModelRequest, HookPhase, ModelInput, StateRef, ToolCall, ToolResult

_CONSUMED = StateRef(key="extension.reference_post_tool_gate.consumed", owner="reference_post_tool_gate", value_type=bool, writers=frozenset({"reference_post_tool_gate"}), default=False)
_SYSTEM = 'Classify the supplied task, current tool call, and tool result. Return exactly one line: POSITIVE <short action detail>, NEGATIVE, or UNCERTAIN. Replace this generic classifier text with the complete positive, negative, and uncertain rules from the authoritative Mechanism decision contract.'
_GUIDANCE = "Missing evidence: {detail}. Use the available tools to gather this evidence before answering."

class ReferencePostToolGateHook(BaseHook):
    def __init__(self) -> None:
        super().__init__(hook_id="reference_post_tool_gate", phases=frozenset({HookPhase.POST_TOOL}), state_refs=(_CONSUMED,), writable_stage_keys=frozenset({"stage.tool_result"}), model_profiles=frozenset({"student"}), max_model_calls_per_invocation=1)

    def handle(self, context: HookContext) -> None:
        self._handle_post_tool(context)

    def _handle_post_tool(self, context: HookContext) -> None:
        if context.state.get(_CONSUMED.key, False):
            return
        question = context.state.get("core.question")
        tool_call = context.state.get("stage.tool_call")
        tool_result = context.state.get("stage.tool_result")
        if not isinstance(question, str) or not isinstance(tool_call, ToolCall) or not isinstance(tool_result, ToolResult):
            return
        payload = {"question": question, "tool_call": {"name": tool_call.name, "arguments": tool_call.arguments}, "tool_result": {"name": tool_result.name, "content": tool_result.content}}
        response = context.call_model(HookModelRequest(profile="student", purpose="reference_post_tool_gate", model_input=ModelInput.from_messages([ChatMessage(role="system", content=_SYSTEM), ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))])))
        first_line = response.raw_output.strip().splitlines()[0] if response.raw_output.strip() else ""
        parts = first_line.split(maxsplit=1)
        label = parts[0].casefold() if parts else "uncertain"
        detail = parts[1].strip() if len(parts) == 2 else ""
        if label != "positive" or not detail:
            return
        context.state.set("stage.tool_result", ToolResult(name=tool_result.name, content=f"{tool_result.content}\n\n{_GUIDANCE.format(detail=detail)}", metadata=dict(tool_result.metadata)))
        context.state.set(_CONSUMED.key, True)

def build(config: dict[str, Any], context: Any) -> ReferencePostToolGateHook:
    if config:
        raise ValueError("reference_post_tool_gate does not accept configuration")
    return ReferencePostToolGateHook()
'''


_POST_TOOL_REWRITE_REFERENCE = '''\
"""Reference pattern: one-shot Hook-model rewrite of a ToolResult."""
from __future__ import annotations
import json
from typing import Any
from search_harness.framework import BaseHook, ChatMessage, HookContext, HookModelRequest, HookPhase, ModelInput, StateRef, ToolCall, ToolResult

_ATTEMPTED = StateRef(key="extension.reference_result_rewrite.attempted", owner="reference_result_rewrite", value_type=bool, writers=frozenset({"reference_result_rewrite"}), default=False)
_SYSTEM = 'Rewrite the supplied evidence faithfully and compactly. Return exactly one JSON object: {"summary":"..."}. Do not add facts.'

class ReferenceResultRewriteHook(BaseHook):
    def __init__(self) -> None:
        super().__init__(hook_id="reference_result_rewrite", phases=frozenset({HookPhase.POST_TOOL}), state_refs=(_ATTEMPTED,), writable_stage_keys=frozenset({"stage.tool_result"}), model_profiles=frozenset({"student"}), max_model_calls_per_invocation=1)

    def handle(self, context: HookContext) -> None:
        tool_call = context.state.get("stage.tool_call")
        tool_result = context.state.get("stage.tool_result")
        if context.state.get(_ATTEMPTED.key, False) or not isinstance(tool_call, ToolCall) or not isinstance(tool_result, ToolResult):
            return
        context.state.set(_ATTEMPTED.key, True)
        payload = {"tool_call": {"name": tool_call.name, "arguments": tool_call.arguments}, "content": tool_result.content}
        response = context.call_model(HookModelRequest(profile="student", purpose="reference_result_rewrite", model_input=ModelInput.from_messages([ChatMessage(role="system", content=_SYSTEM), ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))])))
        try:
            summary = response.json_object().get("summary")
        except ValueError:
            return
        if not isinstance(summary, str) or not summary.strip():
            return
        context.state.set("stage.tool_result", ToolResult(name=tool_result.name, content=summary.strip(), metadata=dict(tool_result.metadata)))

def build(config: dict[str, Any], context: Any) -> ReferenceResultRewriteHook:
    if config:
        raise ValueError("reference_result_rewrite does not accept configuration")
    return ReferenceResultRewriteHook()
'''


def build_parent_authoring_view(resources: TeacherResources) -> dict[str, Any]:
    """Derive exact registry and continuation facts from the shadow workspace."""

    store = resources.compiler
    if store is None:
        raise ValueError("shadow Compiler requires compiler resources")
    manifest = json.loads(store.workspace.read_text("harness.json"))
    policy = json.loads(store.workspace.read_text("evolution.json"))
    components = policy.get("components")
    components = components if isinstance(components, dict) else {}
    extensions = manifest.get("extensions")
    extensions = extensions if isinstance(extensions, list) else []
    index = []
    for raw in extensions:
        if not isinstance(raw, dict):
            continue
        instance_id = raw.get("instance_id")
        entrypoint = raw.get("entrypoint")
        path = str(entrypoint).split(":", 1)[0] if entrypoint else None
        index.append(
            {
                "instance_id": instance_id,
                "entrypoint": entrypoint,
                "mutability": components.get(instance_id, "unavailable"),
                "source_bytes": (
                    len(store.workspace.read_text(path))
                    if isinstance(path, str) and store.workspace.exists(path)
                    else None
                ),
            }
        )
    continuation_files = None
    if store.continuation is not None:
        continuation_files = {
            str(path): store.workspace.read_text(path)
            if store.workspace.exists(path)
            else None
            for path in store.workspace.changed_paths
        }
    return {
        "manifest": manifest,
        "evolution_policy": policy,
        "extension_index": index,
        "continuation_changed_files": continuation_files,
    }


def render_shadow_compiler_input(
    value: dict[str, Any],
    resource_context: dict[str, Any],
) -> str:
    """Render the complete Compiler task as a layered implementation brief."""

    mechanism = _object(value.get("mechanism"))
    compiler = _object(resource_context.get("compiler"))
    packet = _object(compiler.get("capability_packet"))
    return "\n\n".join(
        (
            "# Compiler Implementation Brief",
            (
                "This is a presentation-only view over the complete validated "
                "Mechanism and source-derived capability packet. Exact parent "
                "files, all public API queries, workspace writes, and validation "
                "remain available through tools."
            ),
            _mechanism_view(mechanism),
            _obligation_view(value),
            _parent_view(compiler),
            _packet_view(packet, mechanism),
            (
                "## Working rule\nUse the packet and selected reference before "
                "querying APIs. Read exact parent files only when their source is "
                "material to this mechanism. Continue an existing candidate in "
                "place, write the smallest complete change, and finalize it."
            ),
        )
    )


def render_shadow_hook_api_result(result: dict[str, Any]) -> str:
    """Render one API query in the most direct model-readable form."""

    status = result.get("status")
    remaining = result.get("remaining_unique_queries", "unavailable")
    if status != "resolved":
        return "\n".join(
            (
                f"status: {status}",
                f"reason: {result.get('reason', 'unavailable')}",
                f"query: {result.get('query', result.get('symbol', 'unavailable'))}",
                "runtime_input_suggestions: "
                + _inline(result.get("runtime_input_suggestions")),
                "symbol_suggestions: " + _inline(result.get("symbol_suggestions")),
                f"remaining_unique_queries: {remaining}",
            )
        )
    if result.get("query_kind") == "runtime_input_topic":
        document = _object(result.get("document"))
        body = document.get("native_reference") or json.dumps(
            document, ensure_ascii=False, separators=(",", ":")
        )
        return "\n".join(
            (
                f"resolved_topic: {result.get('query')}",
                f"source: {result.get('source', 'unavailable')}",
                f"remaining_unique_queries: {remaining}",
                str(body),
            )
        )
    native = result.get("native_reference")
    contract = _object(result.get("contract"))
    body = native or json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
    return "\n".join(
        (
            f"resolved_symbol: {result.get('query')}",
            f"source: {result.get('source', 'unavailable')}",
            "related_runtime_inputs: " + _inline(result.get("related_runtime_inputs")),
            f"remaining_unique_queries: {remaining}",
            str(body),
        )
    )


def _mechanism_view(mechanism: dict[str, Any]) -> str:
    lines = [
        "## Authoritative Mechanism",
        f"goal: {mechanism.get('goal', 'unavailable')}",
        "",
        "### Phase rules",
    ]
    rules = mechanism.get("phase_rules")
    for index, raw in enumerate(rules if isinstance(rules, list) else [], start=1):
        rule = _object(raw)
        lines.extend(
            (
                f"#### {index}. {rule.get('phase', 'unavailable')}",
                "```json",
                json.dumps(rule, ensure_ascii=False, separators=(",", ":")),
                "```",
            )
        )
    for title, key in (
        ("Cross-phase behavioral pseudocode", "behavioral_pseudocode"),
        ("State scope", "state_scope"),
        ("Expected behavior", "expected_behavior"),
    ):
        lines.extend((f"### {title}", str(mechanism.get(key, "unavailable"))))
    lines.append("### Constraints and evidence boundary")
    lines.append(
        json.dumps(
            {
                key: mechanism.get(key)
                for key in (
                    "required_capabilities",
                    "prohibited_behaviors",
                    "observability",
                    "known_limits",
                    "evidence_refs",
                )
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return "\n".join(lines)


def _obligation_view(value: dict[str, Any]) -> str:
    constraints = value.get("implementation_constraints")
    validation = value.get("validation_feedback")
    return "\n".join(
        (
            "## Binding revision obligations",
            _group_obligations(constraints),
            "### Deterministic validation feedback",
            _items(validation),
            (
                "All original obligations above remain binding. Grouping is "
                "navigation only and does not discard provenance."
            ),
        )
    )


def _parent_view(compiler: dict[str, Any]) -> str:
    continuation = compiler.get("continuation")
    return "\n".join(
        (
            "## Parent Authoring View",
            "```json",
            json.dumps(
                {
                    key: compiler.get(key)
                    for key in (
                        "harness_id",
                        "parent_digest",
                        "file_count",
                        "fixed_components",
                        "manifest",
                        "evolution_policy",
                        "extension_index",
                        "continuation",
                        "continuation_changed_files",
                        "exact_api_query",
                    )
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "```",
            (
                "Continuation workspace is active; inspect and repair its changed "
                "files before reading unrelated parent components."
                if isinstance(continuation, dict)
                else "No continuation workspace is active."
            ),
            (
                "Hook-model authoring rule: treat each Mechanism decision_contract "
                "as executable semantics. The local Hook prompt must preserve its "
                "complete positive_rule, negative_rule, uncertain_rule, output "
                "labels, and relevant evidence_coverage boundaries. Reference "
                "classifier wording is illustrative wiring only and must never "
                "replace or weaken the authoritative contract. Prefer the shortest "
                "output protocol that expresses the required action detail; use a "
                "single-line label when nested JSON is not otherwise required."
            ),
        )
    )


def _packet_view(packet: dict[str, Any], mechanism: dict[str, Any]) -> str:
    documents = packet.get("runtime_input_documents")
    documents = documents if isinstance(documents, list) else []
    documented_symbols = {
        str(symbol)
        for document in documents
        if isinstance(document, dict)
        for symbol in (document.get("symbols") or [])
    }
    contracts = packet.get("contracts")
    contracts = contracts if isinstance(contracts, list) else []
    unique_contracts = [
        contract
        for contract in contracts
        if isinstance(contract, dict)
        and contract.get("symbol") not in documented_symbols
    ]
    lines = [
        "## Source-derived Authoring Packet",
        "### Selection and versions",
        "```json",
        json.dumps(
            {
                "packet_version": packet.get("packet_version"),
                "catalog_versions": packet.get("catalog_versions"),
                "selection": packet.get("selection"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "```",
        "### Runtime Input Topics",
    ]
    for document in documents:
        if not isinstance(document, dict):
            continue
        lines.extend(
            (
                f"#### {document.get('runtime_input_id', 'unavailable')}",
                str(document.get("native_reference") or json.dumps(
                    document, ensure_ascii=False, separators=(",", ":")
                )),
            )
        )
    lines.extend(("### Additional public contracts", "```jsonl"))
    lines.extend(
        json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
        for contract in unique_contracts
    )
    if not unique_contracts:
        lines.append("none")
    lines.extend(("```", "### Authoring rules", "```json"))
    authoring = _object(packet.get("authoring"))
    authoring_rules = {
        key: value for key, value in authoring.items() if key != "reference_hook"
    }
    lines.append(json.dumps(authoring_rules, ensure_ascii=False, separators=(",", ":")))
    lines.extend(("```", "### Selected reference patterns"))
    references = _selected_references(packet, mechanism)
    if references:
        for name, source in references:
            lines.extend((f"#### {name}", "```python", source, "```"))
    else:
        lines.append("none: the mechanism does not require a supplied combination reference")
    return "\n".join(lines)


def _selected_references(
    packet: dict[str, Any],
    mechanism: dict[str, Any],
) -> list[tuple[str, str]]:
    rules = mechanism.get("phase_rules")
    rules = rules if isinstance(rules, list) else []
    phases = {
        str(rule.get("phase"))
        for rule in rules
        if isinstance(rule, dict)
        and rule.get("decision_evaluator") == "hook_model"
    }
    references = []
    authoring = _object(packet.get("authoring"))
    existing = authoring.get("reference_hook")
    if "pre_final" in phases and isinstance(existing, str) and existing.strip():
        references.append(("model-gated PRE_FINAL deferral", existing))
    if "post_tool" in phases:
        mechanism_text = " ".join(
            str(value)
            for value in (
                mechanism.get("goal"),
                *(rule.get("action") for rule in rules if isinstance(rule, dict)),
            )
        ).casefold()
        rewrite_markers = ("summar", "rewrite", "replace the search toolresult")
        guidance_markers = ("append", "instruction", "guidance", "follow-up")
        is_rewrite = any(marker in mechanism_text for marker in rewrite_markers)
        is_guidance = any(marker in mechanism_text for marker in guidance_markers)
        if is_rewrite and not is_guidance:
            references.append(
                ("Hook-model POST_TOOL result rewrite", _POST_TOOL_REWRITE_REFERENCE)
            )
        elif is_guidance and not is_rewrite:
            references.append(
                ("model-gated POST_TOOL result guidance", _POST_TOOL_MODEL_REFERENCE)
            )
        else:
            references.extend(
                (
                    (
                        "model-gated POST_TOOL result guidance",
                        _POST_TOOL_MODEL_REFERENCE,
                    ),
                    (
                        "Hook-model POST_TOOL result rewrite",
                        _POST_TOOL_REWRITE_REFERENCE,
                    ),
                )
            )
    return references


def _group_obligations(value: object) -> str:
    items = (
        [
            (index, str(item).strip())
            for index, item in enumerate(value, start=1)
            if str(item).strip()
        ]
        if isinstance(value, list)
        else []
    )
    if not items:
        return "none"
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for source_index, item in items:
        lowered = item.casefold()
        key = "other"
        for candidate, markers in (
            ("predicate boundary", ("classif", "positive", "negative", "predicate")),
            ("action", ("patch", "insert", "defer", "feedback")),
            ("state and lifecycle", ("state", "budget", "activation", "phase")),
            ("runtime integration", ("runtime", "api", "manifest", "import")),
        ):
            if any(marker in lowered for marker in markers):
                key = candidate
                break
        groups[key].append((source_index, item))
    lines = []
    for group, values in groups.items():
        lines.append(f"### {group}")
        lines.extend(
            f"- [constraint_{source_index}] {item}"
            for source_index, item in values
        )
    return "\n".join(lines)


def _items(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return "\n".join(f"- {item}" for item in value)


def _inline(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ", ".join(str(item) for item in value)


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
