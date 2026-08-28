"""Role-specific model views for Compiler authoring inputs and API queries."""

from __future__ import annotations

import json
from typing import Any


def render_compiler_resource_context(context: dict[str, Any]) -> str:
    """Render complete Compiler resources without duplicated API contracts."""

    compiler = _object(context.get("compiler"))
    packet = _object(compiler.get("capability_packet"))
    continuation = _object(compiler.get("continuation"))
    lines = [
        "# Compiler Resource Context",
        "",
        "## Parent workspace",
        _json_block(
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
                    "exact_api_query",
                )
            }
        ),
    ]
    if continuation:
        lines.extend(
            (
                "",
                "## Continuation workspace",
                _json_block(continuation),
                "",
                "### Exact changed files",
                _render_changed_files(
                    _object(compiler.get("continuation_changed_files"))
                ),
            )
        )
    else:
        lines.extend(("", "## Continuation workspace", "none"))
    lines.extend(("", render_compiler_capability_packet(packet)))
    return "\n".join(lines)


def render_compiler_capability_packet(packet: dict[str, Any]) -> str:
    """Render one source-derived packet with each public contract once."""

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
        and str(contract.get("symbol")) not in documented_symbols
    ]
    lines = [
        "## Source-derived capability packet",
        "",
        "### Selection",
        _json_block(_packet_selection_view(_object(packet.get("selection")))),
        "",
        "### Runtime Input Topics",
    ]
    if documents:
        for document in documents:
            if not isinstance(document, dict):
                continue
            lines.extend(
                (
                    f"#### {document.get('runtime_input_id', 'unavailable')}",
                    str(
                        document.get("native_reference")
                        or json.dumps(
                            document,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                )
            )
    else:
        lines.append("none")
    lines.extend(("", "### Additional public contracts", "```jsonl"))
    if unique_contracts:
        lines.extend(
            json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            for item in unique_contracts
        )
    else:
        lines.append("none")
    lines.extend(
        (
            "```",
            "",
            "### Authoring contract",
            _json_block(_object(packet.get("authoring"))),
            "",
            "### Catalog versions",
            _json_block(_object(packet.get("catalog_versions"))),
        )
    )
    return "\n".join(lines)


def render_hook_api_result(result: dict[str, Any]) -> str:
    """Prefer the native reference and omit its duplicated structured contract."""

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
                "symbol_suggestions: "
                + _inline(result.get("symbol_suggestions")),
                f"remaining_unique_queries: {remaining}",
            )
        )
    if result.get("query_kind") == "runtime_input_topic":
        document = _object(result.get("document"))
        body = document.get("native_reference") or json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
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
    body = native or json.dumps(
        contract,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "\n".join(
        (
            f"resolved_symbol: {result.get('query')}",
            f"source: {result.get('source', 'unavailable')}",
            "related_runtime_inputs: "
            + _inline(result.get("related_runtime_inputs")),
            f"remaining_unique_queries: {remaining}",
            str(body),
        )
    )


def _packet_selection_view(selection: dict[str, Any]) -> dict[str, Any]:
    """Keep API selection facts while dropping Mechanism fields repeated in input."""

    managed = selection.get("managed_hook_prompts")
    if isinstance(managed, dict):
        phases = selection.get("phases")
        phases = phases if isinstance(phases, list) else []
        return {
            "strategy": selection.get("strategy"),
            "managed_hook_prompts": managed,
            "phase_prompt_bindings": [
                {
                    "phase": item.get("phase"),
                    "prompt_product_ref": item.get("prompt_product_ref"),
                }
                for item in phases
                if isinstance(item, dict)
            ],
            "unresolved_symbols": selection.get("unresolved_symbols"),
        }
    phase_rules = selection.get("phase_rules")
    phase_rules = phase_rules if isinstance(phase_rules, list) else []
    return {
        "strategy": selection.get("strategy"),
        "phase_api_inputs": [
            {
                key: rule.get(key)
                for key in (
                    "phase",
                    "exact_decision_inputs",
                    "semantic_decision_inputs",
                    "runtime_inputs",
                )
            }
            for rule in phase_rules
            if isinstance(rule, dict)
        ],
        "exact_required_capabilities": selection.get(
            "exact_required_capabilities"
        ),
        "semantic_required_capabilities": selection.get(
            "semantic_required_capabilities"
        ),
        "unresolved_api_capabilities": selection.get(
            "unresolved_api_capabilities"
        ),
        "unresolved_symbols": selection.get("unresolved_symbols"),
        "unresolved_runtime_inputs": selection.get(
            "unresolved_runtime_inputs"
        ),
    }


def _render_changed_files(files: dict[str, Any]) -> str:
    if not files:
        return "none"
    sections = []
    for path, content in files.items():
        sections.append(f"<candidate_file path={json.dumps(path)}>")
        sections.append("<deleted>" if content is None else str(content))
        sections.append("</candidate_file>")
    return "\n".join(sections)


def _json_block(value: object) -> str:
    return "```json\n" + json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n```"


def _inline(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ", ".join(str(item) for item in value)


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
