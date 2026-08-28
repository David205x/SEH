"""Build TASK-007 model inputs from allowlisted artifact fields.

This module belongs to the development validation harness.  The production
Experience Summarizer remains independent of files and JSON pointers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ALLOWED_OPERATIONS = {"copy_text", "copy_json", "join_values"}


@dataclass(frozen=True)
class ArtifactProjection:
    """One constructed request plus its program-side provenance audit."""

    direction: str
    attempt: str
    evidence: dict[str, dict[str, Any]]
    evidence_views: dict[str, dict[str, list[dict[str, Any]]]]
    evidence_prompt_variants: dict[str, list[dict[str, Any]]]
    audit: list[dict[str, Any]]


def project_artifact_input(
    *,
    project_root: Path,
    case: Mapping[str, Any],
) -> ArtifactProjection:
    """Resolve one schema-v2 case without summaries, fallback, or truncation."""

    sources = _load_sources(project_root, case)
    audit: list[dict[str, Any]] = []
    projection = _required_mapping(case, "projection")
    direction = _project(
        projection["direction"],
        target="direction",
        sources=sources,
        audit=audit,
    )
    attempt = _project(
        projection["attempt"],
        target="attempt",
        sources=sources,
        audit=audit,
    )

    evidence: dict[str, dict[str, Any]] = {}
    raw_evidence = _required_mapping(projection, "evidence")
    for evidence_ref, raw_observation in raw_evidence.items():
        observation = _as_mapping(raw_observation, f"evidence.{evidence_ref}")
        item: dict[str, Any] = {
            "outcome": _project(
                observation["outcome"],
                target=f"evidence.{evidence_ref}.outcome",
                sources=sources,
                audit=audit,
            ),
            "comparison": _project_optional(
                observation.get("comparison"),
                target=f"evidence.{evidence_ref}.comparison",
                sources=sources,
                audit=audit,
            ),
            "boundary_facts": [],
        }
        raw_boundaries = observation.get("boundary_facts", [])
        if not isinstance(raw_boundaries, list):
            raise TypeError("boundary_facts must be a list")
        for index, raw_boundary in enumerate(raw_boundaries):
            boundary = _as_mapping(
                raw_boundary,
                f"evidence.{evidence_ref}.boundary_facts[{index}]",
            )
            source = _required_string(boundary, "source")
            pointer = _required_string(boundary, "pointer")
            _resolve_pointer(sources[source]["value"], pointer)
            kind = _required_string(boundary, "kind")
            status = _required_string(boundary, "status")
            item["boundary_facts"].append(
                {
                    "kind": kind,
                    "status": status,
                    "statement": (
                        f"{kind} is {status} at {source}#{pointer}."
                    ),
                }
            )
        evidence[evidence_ref] = item

    evidence_views: dict[str, dict[str, list[dict[str, Any]]]] = {}
    raw_views = _required_mapping(projection, "evidence_views")
    for evidence_ref, raw_ref_views in raw_views.items():
        ref_views = _as_mapping(raw_ref_views, f"views.{evidence_ref}")
        evidence_views[evidence_ref] = {}
        for view, raw_details in ref_views.items():
            if not isinstance(raw_details, list) or not raw_details:
                raise TypeError(f"view {evidence_ref}.{view} must be a list")
            details: list[dict[str, Any]] = []
            for index, raw_detail in enumerate(raw_details):
                detail = _as_mapping(
                    raw_detail,
                    f"views.{evidence_ref}.{view}[{index}]",
                )
                details.append(
                    {
                        "selector": _required_string(detail, "selector"),
                        "content": _project(
                            detail["content"],
                            target=(
                                f"evidence_views.{evidence_ref}.{view}."
                                f"{index}.content"
                            ),
                            sources=sources,
                            audit=audit,
                        ),
                    }
                )
            evidence_views[evidence_ref][view] = details

    if set(evidence) != set(evidence_views):
        raise ValueError("evidence refs and evidence-view refs must match")
    evidence_prompt_variants: dict[str, list[dict[str, Any]]] = {
        evidence_ref: [] for evidence_ref in evidence
    }
    raw_variants = projection.get("prompt_variants", {})
    if not isinstance(raw_variants, Mapping):
        raise TypeError("projection.prompt_variants must be an object")
    unknown_variant_refs = set(raw_variants) - set(evidence)
    if unknown_variant_refs:
        raise ValueError(
            "Prompt variants reference unknown evidence refs: "
            f"{sorted(unknown_variant_refs)}"
        )
    for evidence_ref, raw_declarations in raw_variants.items():
        if not isinstance(raw_declarations, list):
            raise TypeError(f"prompt_variants.{evidence_ref} must be a list")
        evidence_prompt_variants[evidence_ref] = [
            _project_variant_declaration(
                raw_declaration,
                label=f"prompt_variants.{evidence_ref}[{index}]",
                sources=sources,
                audit=audit,
            )
            for index, raw_declaration in enumerate(raw_declarations)
        ]
    return ArtifactProjection(
        direction=direction,
        attempt=attempt,
        evidence=evidence,
        evidence_views=evidence_views,
        evidence_prompt_variants=evidence_prompt_variants,
        audit=audit,
    )


def _project_variant_declaration(
    raw_declaration: object,
    *,
    label: str,
    sources: Mapping[str, Mapping[str, Any]],
    audit: list[dict[str, Any]],
) -> dict[str, Any]:
    declaration = dict(_as_mapping(raw_declaration, label))
    declaration["artifact_pointer"] = _project_pointer_declaration(
        declaration.get("artifact_pointer"),
        label=f"{label}.artifact_pointer",
        sources=sources,
        audit=audit,
    )
    raw_results = declaration.get("capability_result_refs", [])
    if not isinstance(raw_results, list):
        raise TypeError(f"{label}.capability_result_refs must be a list")
    results = []
    for index, raw_result in enumerate(raw_results):
        result = dict(_as_mapping(raw_result, f"{label}.result[{index}]"))
        result["artifact_pointer"] = _project_pointer_declaration(
            result.get("artifact_pointer"),
            label=f"{label}.result[{index}].artifact_pointer",
            sources=sources,
            audit=audit,
        )
        results.append(result)
    declaration["capability_result_refs"] = results
    return declaration


def _project_pointer_declaration(
    raw_pointer: object,
    *,
    label: str,
    sources: Mapping[str, Mapping[str, Any]],
    audit: list[dict[str, Any]],
) -> dict[str, str]:
    pointer = _as_mapping(raw_pointer, label)
    source = _required_string(pointer, "source")
    json_pointer = _required_string(pointer, "pointer")
    if source not in sources:
        raise ValueError(f"unknown artifact source alias: {source}")
    _resolve_pointer(sources[source]["value"], json_pointer)
    artifact_ref = str(sources[source]["relative_path"])
    audit.append(
        {
            "target_field": label,
            "artifact_path": artifact_ref,
            "json_pointer": json_pointer,
            "operation": "declare_pointer",
        }
    )
    return {"artifact_ref": artifact_ref, "json_pointer": json_pointer}


def _load_sources(
    project_root: Path,
    case: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    raw_sources = _required_mapping(case, "sources")
    sources: dict[str, dict[str, Any]] = {}
    for alias, raw_path in raw_sources.items():
        if not isinstance(raw_path, str) or not raw_path:
            raise TypeError(f"artifact source path must be text: {alias}")
        path = (project_root / raw_path).resolve()
        try:
            path.relative_to(project_root.resolve())
        except ValueError as exc:
            raise ValueError(f"artifact source escapes project root: {path}") from exc
        if not path.is_file():
            raise FileNotFoundError(f"artifact source is missing: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        sources[alias] = {
            "path": path,
            "relative_path": path.relative_to(project_root.resolve()).as_posix(),
            "value": value,
        }
    return sources


def _project_optional(
    spec: object,
    *,
    target: str,
    sources: Mapping[str, Mapping[str, Any]],
    audit: list[dict[str, Any]],
) -> str | None:
    if spec is None:
        return None
    return _project(spec, target=target, sources=sources, audit=audit)


def _project(
    raw_spec: object,
    *,
    target: str,
    sources: Mapping[str, Mapping[str, Any]],
    audit: list[dict[str, Any]],
) -> str:
    spec = _as_mapping(raw_spec, target)
    operation = _required_string(spec, "op")
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported artifact projection operation: {operation}")
    if operation == "join_values":
        raw_values = spec.get("values")
        if not isinstance(raw_values, list) or not raw_values:
            raise TypeError("join_values requires a non-empty values list")
        parts = []
        for raw_value in raw_values:
            value_spec = _as_mapping(raw_value, target)
            rendered = _project(
                value_spec,
                target=target,
                sources=sources,
                audit=audit,
            )
            label = (
                f"{_required_string(value_spec, 'source')}#"
                f"{_required_string(value_spec, 'pointer')}"
            )
            parts.append(f"{label}: {rendered}")
        return "\n".join(parts)

    source = _required_string(spec, "source")
    pointer = _required_string(spec, "pointer")
    if source not in sources:
        raise ValueError(f"unknown artifact source alias: {source}")
    value = _resolve_pointer(sources[source]["value"], pointer)
    if operation == "copy_text":
        if not isinstance(value, str) or not value:
            raise TypeError(f"copy_text target is not non-empty text: {source}#{pointer}")
        rendered = value
    else:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    audit.append(
        {
            "target_field": target,
            "artifact_path": sources[source]["relative_path"],
            "json_pointer": pointer,
            "operation": operation,
            "copied_value": rendered,
        }
    )
    return rendered


def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer}")
    current = value
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit():
                raise ValueError(f"JSON pointer list token is not an index: {pointer}")
            index = int(token)
            if index >= len(current):
                raise KeyError(f"JSON pointer index is missing: {pointer}")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise KeyError(f"JSON pointer key is missing: {pointer}")
            current = current[token]
        else:
            raise TypeError(f"JSON pointer crosses a scalar: {pointer}")
    return current


def _required_mapping(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    item = value.get(field)
    return _as_mapping(item, field)


def _as_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _required_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise TypeError(f"{field} must be non-empty text")
    return item
