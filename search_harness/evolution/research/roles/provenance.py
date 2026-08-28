"""Minimal Teacher Role scope and model-visible input provenance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from search_harness.framework.tools import DefinedTool

from .spec import TeacherPromptSpec


@dataclass(frozen=True)
class TeacherRoleScope:
    """Hard compatibility scope for future Teacher work experience."""

    role_id: str
    role_contract_version: int
    model_provider: str
    model_id: str

    def __post_init__(self) -> None:
        if not self.role_id.strip():
            raise ValueError("Teacher Role scope role_id must not be empty")
        if self.role_contract_version < 1:
            raise ValueError(
                "Teacher Role scope contract version must be positive"
            )
        if not self.model_provider.strip():
            raise ValueError(
                "Teacher Role scope model provider must not be empty"
            )
        if not self.model_id.strip():
            raise ValueError("Teacher Role scope model ID must not be empty")


def teacher_role_scope(
    *,
    role_id: str,
    role_contract_version: int,
    model: Mapping[str, Any],
) -> TeacherRoleScope:
    """Project the minimal hard scope from authoritative role/model fields."""

    provider = model.get("provider")
    model_id = model.get("model_id")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("Teacher model provenance lacks provider")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("Teacher model provenance lacks model_id")
    return TeacherRoleScope(
        role_id=role_id,
        role_contract_version=role_contract_version,
        model_provider=provider,
        model_id=model_id,
    )


def teacher_role_scope_from_artifact(
    artifact: Mapping[str, Any],
) -> TeacherRoleScope:
    """Read the hard scope without persisting a duplicate identity object."""

    role = artifact.get("role")
    model = artifact.get("model")
    if not isinstance(role, Mapping):
        raise TypeError("Teacher artifact role must be an object")
    if not isinstance(model, Mapping):
        raise TypeError("Teacher artifact model must be an object")
    role_id = role.get("id")
    version = role.get("version")
    if not isinstance(role_id, str) or not role_id.strip():
        raise TypeError("Teacher artifact role.id must be a string")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise TypeError("Teacher artifact role.version must be positive")
    return teacher_role_scope(
        role_id=role_id,
        role_contract_version=version,
        model=model,
    )


def base_prompt_digest(prompt: TeacherPromptSpec) -> str:
    """Fingerprint assembled base Prompt content, independent of file paths."""

    return content_digest(
        {
            "instructions": prompt.instructions,
            "user_template": prompt.user_template,
            "continuation_templates": prompt.continuation_templates,
        }
    )


def model_input_view(
    *,
    messages: Sequence[Mapping[str, Any]],
    tools: Iterable[DefinedTool],
    terminal_tool: Mapping[str, Any] | None = None,
    structured_output_schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a detached view of content actually exposed to the Model."""

    tool_views = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.definition.description,
                "parameters": tool.definition.to_json_schema(),
            },
        }
        for tool in tools
    ]
    if terminal_tool is not None:
        tool_views.append(deepcopy(dict(terminal_tool)))
    view: dict[str, Any] = {
        "messages": deepcopy([dict(message) for message in messages]),
        "tools": tool_views,
    }
    if structured_output_schema is not None:
        view["structured_output_schema"] = deepcopy(
            dict(structured_output_schema)
        )
    return view


def input_view_digest(model_inputs: Sequence[Mapping[str, Any]]) -> str:
    """Fingerprint ordered compact Model Inputs without changing requests."""

    if not model_inputs:
        raise ValueError("Teacher input-view digest requires a Model Input")
    return content_digest([dict(item) for item in model_inputs])


def content_digest(value: Any) -> str:
    """Return a deterministic SHA-256 content fingerprint, never an ID."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
