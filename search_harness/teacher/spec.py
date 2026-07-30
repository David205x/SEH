"""Teacher template 装配后的 transport-neutral 对象。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.framework.tooling import ToolSet

from .contracts import TeacherPayload, TeacherRoleDefinition
from .manifest import TeacherAgentManifest


ROLE_INPUT_PLACEHOLDER = "{{role_input}}"
RESOURCE_CONTEXT_PLACEHOLDER = "{{resource_context}}"


@dataclass(frozen=True)
class TeacherPromptSpec:
    """Teacher instructions 与单次运行输入模板。"""

    instructions: str
    user_template: str

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise ValueError("Teacher instructions must not be empty")
        if ROLE_INPUT_PLACEHOLDER not in self.user_template:
            raise ValueError(
                f"Teacher user template must contain {ROLE_INPUT_PLACEHOLDER}"
            )
        if RESOURCE_CONTEXT_PLACEHOLDER not in self.user_template:
            raise ValueError(
                "Teacher user template must contain "
                f"{RESOURCE_CONTEXT_PLACEHOLDER}"
            )

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        """将已验证的角色输入和程序上下文渲染为一次 run input。"""

        return (
            self.user_template.replace(
                ROLE_INPUT_PLACEHOLDER,
                json.dumps(
                    role_input.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            .replace(
                RESOURCE_CONTEXT_PLACEHOLDER,
                json.dumps(resource_context, ensure_ascii=False, indent=2),
            )
            .strip()
        )


@dataclass(frozen=True)
class TeacherPluginContext:
    """传给 Teacher prompt/tool factory 的稳定上下文。"""

    template_root: Path
    runtime_context: object


@dataclass(frozen=True)
class TeacherAgentSpec:
    """由目录模板装配出的中立 Teacher Agent 定义。"""

    manifest: TeacherAgentManifest
    role: TeacherRoleDefinition
    prompt: TeacherPromptSpec
    tools: ToolSet
