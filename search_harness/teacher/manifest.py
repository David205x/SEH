"""Teacher agent template 的 UTF-8 manifest。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.registry import ComponentSpec, EvolutionPolicy


MANIFEST_FILE_NAME = "harness.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ContractReference:
    """一个代码内稳定协议的版本化引用。"""

    contract_id: str
    version: int


@dataclass(frozen=True)
class TeacherAgentManifest:
    """一个 Teacher Agent 的声明式组件清单。"""

    harness_id: str
    role: ContractReference
    output_contract: ContractReference
    tools: tuple[ComponentSpec, ...]
    prompt: ComponentSpec
    schema_version: int = SCHEMA_VERSION


def load_teacher_manifest(template_root: Path) -> TeacherAgentManifest:
    """读取并验证一个不含 extensions 的 Teacher agent manifest。"""

    path = template_root / MANIFEST_FILE_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Teacher manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Teacher manifest JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("Teacher manifest root must be an object")

    allowed = {
        "schema_version",
        "harness_id",
        "role",
        "output_contract",
        "tools",
        "prompt",
        "extensions",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"Teacher manifest has unsupported fields: {sorted(unknown)}")
    if raw.get("extensions", []) != []:
        raise ValueError("Teacher templates do not support extensions")

    schema_version = _require_int(raw, "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported Teacher manifest schema_version: {schema_version}"
        )
    tools = _parse_components(raw.get("tools"), "tools")
    prompt = _parse_component(raw.get("prompt"), "prompt")
    if not prompt.enabled:
        raise ValueError("Teacher prompt component cannot be disabled")
    instance_ids = [item.instance_id for item in (*tools, prompt)]
    if len(instance_ids) != len(set(instance_ids)):
        raise ValueError("Teacher manifest contains duplicate instance_id values")
    return TeacherAgentManifest(
        schema_version=schema_version,
        harness_id=_require_str(raw, "harness_id"),
        role=_parse_contract_reference(raw.get("role"), "role"),
        output_contract=_parse_contract_reference(
            raw.get("output_contract"),
            "output_contract",
        ),
        tools=tools,
        prompt=prompt,
    )


def _parse_contract_reference(value: object, field: str) -> ContractReference:
    if not isinstance(value, dict):
        raise TypeError(f"Teacher manifest field '{field}' must be an object")
    if set(value) != {"id", "version"}:
        raise ValueError(
            f"Teacher manifest field '{field}' must contain only id and version"
        )
    return ContractReference(
        contract_id=_require_str(value, "id"),
        version=_require_int(value, "version"),
    )


def _parse_components(value: object, field: str) -> tuple[ComponentSpec, ...]:
    if not isinstance(value, list):
        raise TypeError(f"Teacher manifest field '{field}' must be an array")
    return tuple(_parse_component(item, field) for item in value)


def _parse_component(value: object, field: str) -> ComponentSpec:
    if not isinstance(value, dict):
        raise TypeError(f"Teacher manifest {field} entry must be an object")
    allowed = {"instance_id", "entrypoint", "config", "evolution_policy", "enabled"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(
            f"Teacher manifest {field} entry has unsupported fields: {sorted(unknown)}"
        )
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise TypeError("Teacher component enabled must be a boolean")
    try:
        policy = EvolutionPolicy(_require_str(value, "evolution_policy"))
    except ValueError as exc:
        raise ValueError(
            "Teacher component evolution_policy must be fixed or mutable"
        ) from exc
    config = value.get("config")
    if not isinstance(config, dict):
        raise TypeError("Teacher component config must be an object")
    return ComponentSpec(
        instance_id=_require_str(value, "instance_id"),
        entrypoint=_require_str(value, "entrypoint"),
        config=dict(config),
        evolution_policy=policy,
        enabled=enabled,
    )


def _require_str(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Teacher manifest field '{field}' must be a non-empty string")
    return value.strip()


def _require_int(raw: dict[str, Any], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TypeError(f"Teacher manifest field '{field}' must be a positive integer")
    return value
