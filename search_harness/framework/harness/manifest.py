"""Harness Template 的角色无关 Manifest。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_FILE_NAME = "harness.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ComponentDeclaration:
    """一个 Harness Component 实例的入口和配置声明。"""

    instance_id: str
    entrypoint: str
    config: dict[str, Any]
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("component instance_id must not be empty")
        if not self.entrypoint.strip():
            raise ValueError("component entrypoint must not be empty")
        module_path, separator, factory_name = self.entrypoint.partition(":")
        if separator != ":" or not module_path.endswith(".py") or not factory_name:
            raise ValueError("entrypoint must be relative_file.py:factory_name")
        relative_path = Path(module_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("entrypoint must stay inside the template root")
        if not isinstance(self.config, dict):
            raise TypeError("component config must be an object")


@dataclass(frozen=True)
class HarnessManifest:
    """一个 Harness Template 的完整 Component 索引。"""

    harness_id: str
    tools: tuple[ComponentDeclaration, ...]
    prompt: ComponentDeclaration
    output: ComponentDeclaration
    extensions: tuple[ComponentDeclaration, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported harness schema_version: {self.schema_version}"
            )
        if not self.harness_id.strip():
            raise ValueError("harness_id must not be empty")
        if not self.prompt.enabled:
            raise ValueError("prompt component cannot be disabled")
        if not self.output.enabled:
            raise ValueError("output component cannot be disabled")
        declarations = (
            *self.tools,
            self.prompt,
            self.output,
            *self.extensions,
        )
        instance_ids = [item.instance_id for item in declarations]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("harness manifest contains duplicate instance_id values")


def load_harness_manifest(template_root: Path) -> HarnessManifest:
    """显式使用 UTF-8 读取并校验一个 ``harness.json``。"""

    path = template_root / MANIFEST_FILE_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Harness Manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Harness Manifest JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("Harness Manifest root must be an object")

    allowed = {
        "schema_version",
        "harness_id",
        "tools",
        "prompt",
        "output",
        "extensions",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(
            f"Harness Manifest has unsupported fields: {sorted(unknown)}"
        )
    return HarnessManifest(
        schema_version=_require_int(raw, "schema_version"),
        harness_id=_require_str(raw, "harness_id"),
        tools=_parse_declarations(raw, "tools", default=[]),
        prompt=_parse_declaration(raw.get("prompt"), "prompt"),
        output=_parse_declaration(raw.get("output"), "output"),
        extensions=_parse_declarations(raw, "extensions", default=[]),
    )


def _parse_declarations(
    raw: dict[str, Any],
    field: str,
    *,
    default: list[object],
) -> tuple[ComponentDeclaration, ...]:
    value = raw.get(field, default)
    if not isinstance(value, list):
        raise TypeError(f"Harness Manifest field '{field}' must be an array")
    return tuple(_parse_declaration(item, field) for item in value)


def _parse_declaration(value: object, field: str) -> ComponentDeclaration:
    if not isinstance(value, dict):
        raise TypeError(f"Harness Manifest {field} entry must be an object")
    allowed = {"instance_id", "entrypoint", "config", "enabled"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(
            f"Harness Manifest {field} entry has unsupported fields: "
            f"{sorted(unknown)}"
        )
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise TypeError("component enabled must be a boolean")
    config = value.get("config")
    if not isinstance(config, dict):
        raise TypeError("component config must be an object")
    return ComponentDeclaration(
        instance_id=_require_str(value, "instance_id"),
        entrypoint=_require_str(value, "entrypoint"),
        config=dict(config),
        enabled=enabled,
    )


def _require_str(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Harness Manifest field '{field}' must be a non-empty string")
    return value.strip()


def _require_int(raw: dict[str, Any], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TypeError(f"Harness Manifest field '{field}' must be a positive integer")
    return value
