"""UTF-8 manifest schema for one external Harness plugin root."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


MANIFEST_FILE_NAME = "harness.json"
SCHEMA_VERSION = 1


class EvolutionPolicy(str, Enum):
    """Whether a component may be changed by future Harness evolution."""

    FIXED = "fixed"
    MUTABLE = "mutable"


@dataclass(frozen=True)
class ComponentSpec:
    """One configured tool, prompt, or extension instance."""

    instance_id: str
    entrypoint: str
    config: dict[str, Any]
    evolution_policy: EvolutionPolicy
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("component instance_id must not be empty")
        if not self.entrypoint.strip():
            raise ValueError("component entrypoint must not be empty")
        module_path, separator, factory_name = self.entrypoint.partition(":")
        if separator != ":" or not module_path.endswith(".py") or not factory_name:
            raise ValueError("entrypoint must be relative_file.py:factory_name")
        relative = Path(module_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("entrypoint must stay inside the plugins root")
        if not isinstance(self.config, dict):
            raise TypeError("component config must be an object")


@dataclass(frozen=True)
class HarnessManifest:
    """Complete configured component set for one Harness instance."""

    harness_id: str
    tools: tuple[ComponentSpec, ...]
    prompt: ComponentSpec
    extensions: tuple[ComponentSpec, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported harness schema_version: {self.schema_version}")
        if not self.harness_id.strip():
            raise ValueError("harness_id must not be empty")
        instance_ids = [item.instance_id for item in (*self.tools, self.prompt, *self.extensions)]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("harness manifest contains duplicate instance_id values")


def load_manifest(plugins_root: Path) -> HarnessManifest:
    """Read and validate one UTF-8 ``harness.json`` file."""

    path = plugins_root / MANIFEST_FILE_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"plugins manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in plugins manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("harness manifest root must be an object")

    allowed = {"schema_version", "harness_id", "tools", "prompt", "extensions"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"harness manifest has unsupported keys: {sorted(unknown)}")
    return HarnessManifest(
        schema_version=_require_int(raw, "schema_version"),
        harness_id=_require_str(raw, "harness_id"),
        tools=_parse_components(raw, "tools"),
        prompt=_parse_component(_require_object(raw, "prompt"), "prompt"),
        extensions=_parse_components(raw, "extensions", default=[]),
    )


def _parse_components(
    raw: dict[str, Any],
    field: str,
    default: list[object] | None = None,
) -> tuple[ComponentSpec, ...]:
    value = raw.get(field, default)
    if not isinstance(value, list):
        raise TypeError(f"harness manifest field '{field}' must be an array")
    return tuple(_parse_component(item, field) for item in value)


def _parse_component(raw: object, field: str) -> ComponentSpec:
    if not isinstance(raw, dict):
        raise TypeError(f"harness manifest {field} entry must be an object")
    allowed = {"instance_id", "entrypoint", "config", "evolution_policy", "enabled"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"harness manifest {field} entry has unsupported keys: {sorted(unknown)}")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise TypeError("component enabled must be a boolean")
    try:
        policy = EvolutionPolicy(_require_str(raw, "evolution_policy"))
    except ValueError as exc:
        raise ValueError("component evolution_policy must be fixed or mutable") from exc
    return ComponentSpec(
        instance_id=_require_str(raw, "instance_id"),
        entrypoint=_require_str(raw, "entrypoint"),
        config=_require_object(raw, "config"),
        evolution_policy=policy,
        enabled=enabled,
    )


def _require_object(raw: dict[str, Any], field: str) -> dict[str, Any]:
    value = raw.get(field)
    if not isinstance(value, dict):
        raise TypeError(f"harness manifest field '{field}' must be an object")
    return dict(value)


def _require_str(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str):
        raise TypeError(f"harness manifest field '{field}' must be a string")
    return value


def _require_int(raw: dict[str, Any], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"harness manifest field '{field}' must be an integer")
    return value
