"""Evolution 应用拥有的 Harness Template 修改策略。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


POLICY_FILE_NAME = "evolution.json"
SCHEMA_VERSION = 1


class ComponentEvolutionPolicy(str, Enum):
    """一个 Harness Component 是否可由 Candidate Attempt 修改。"""

    FIXED = "fixed"
    MUTABLE = "mutable"


@dataclass(frozen=True)
class EvolutionPolicy:
    """一个 Harness Template 的组件级 Evolution Policy。"""

    harness_id: str
    components: Mapping[str, ComponentEvolutionPolicy]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported evolution schema_version: {self.schema_version}"
            )
        if not self.harness_id.strip():
            raise ValueError("evolution harness_id must not be empty")
        if any(not instance_id.strip() for instance_id in self.components):
            raise ValueError("evolution component instance_id must not be empty")
        object.__setattr__(
            self,
            "components",
            MappingProxyType(dict(self.components)),
        )


def load_evolution_policy(template_root: Path) -> EvolutionPolicy:
    """显式使用 UTF-8 读取并校验 ``evolution.json``。"""

    path = template_root / POLICY_FILE_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Evolution Policy does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Evolution Policy JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("Evolution Policy root must be an object")
    unknown = set(raw) - {"schema_version", "harness_id", "components"}
    if unknown:
        raise ValueError(
            f"Evolution Policy has unsupported fields: {sorted(unknown)}"
        )
    components = raw.get("components")
    if not isinstance(components, dict):
        raise TypeError("Evolution Policy field 'components' must be an object")
    parsed: dict[str, ComponentEvolutionPolicy] = {}
    for instance_id, value in components.items():
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise TypeError("Evolution Policy component key must be a non-empty string")
        if not isinstance(value, str):
            raise TypeError(
                f"Evolution Policy for '{instance_id}' must be a string"
            )
        try:
            parsed[instance_id] = ComponentEvolutionPolicy(value)
        except ValueError as exc:
            raise ValueError(
                f"Evolution Policy for '{instance_id}' must be fixed or mutable"
            ) from exc
    return EvolutionPolicy(
        schema_version=_require_positive_int(raw, "schema_version"),
        harness_id=_require_non_empty_string(raw, "harness_id"),
        components=parsed,
    )


def _require_non_empty_string(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Evolution Policy field '{field}' must be a non-empty string")
    return value.strip()


def _require_positive_int(raw: dict[str, Any], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TypeError(f"Evolution Policy field '{field}' must be a positive integer")
    return value
