"""Teacher template 装配后的 transport-neutral 对象。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from search_harness.framework.harness import HarnessManifest
from search_harness.framework.tools import ToolSet

from .contracts import TeacherPayload, TeacherRoleDefinition


ROLE_INPUT_PLACEHOLDER = "{{role_input}}"
RESOURCE_CONTEXT_PLACEHOLDER = "{{resource_context}}"
FEEDBACK_EVENT_PLACEHOLDER = "{{feedback_event}}"


@dataclass(frozen=True)
class TeacherPromptSpec:
    """Teacher 初始输入与按反馈来源选择的续接模板。"""

    instructions: str
    user_template: str
    continuation_templates: dict[str, str] = field(default_factory=dict)

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
        for source, template in self.continuation_templates.items():
            if not source.strip():
                raise ValueError("Teacher continuation source must not be empty")
            if template.count(FEEDBACK_EVENT_PLACEHOLDER) != 1:
                raise ValueError(
                    "Teacher continuation template must contain exactly one "
                    f"{FEEDBACK_EVENT_PLACEHOLDER}: {source}"
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

    def render_continuation(
        self,
        source: str,
        feedback_event: dict[str, Any],
    ) -> str:
        """按已声明的反馈来源渲染同一 Role Session 的续接输入。"""

        template = self.continuation_templates.get(source)
        if template is None:
            raise ValueError(f"unsupported role continuation source: {source}")
        return template.replace(
            FEEDBACK_EVENT_PLACEHOLDER,
            json.dumps(feedback_event, ensure_ascii=False, indent=2),
        ).strip()


@dataclass(frozen=True)
class TeacherOutputSpec:
    """把 Teacher Role 的稳定 Output Contract 暴露给 Runner。"""

    kind: str = "role_contract"
    submission_type: type[TeacherPayload] | None = None
    materializer: Callable[[TeacherPayload], TeacherPayload] | None = None

    def __post_init__(self) -> None:
        if self.kind != "role_contract":
            raise ValueError(f"unsupported Teacher output kind: {self.kind}")
        if (self.submission_type is None) != (self.materializer is None):
            raise ValueError(
                "Teacher output submission_type and materializer must be "
                "configured together"
            )

    def model_submission_type(
        self,
        final_type: type[TeacherPayload],
    ) -> type[TeacherPayload]:
        """Return the transport schema shown to the model."""

        return self.submission_type or final_type

    def materialize(
        self,
        submission: TeacherPayload,
        *,
        final_type: type[TeacherPayload],
    ) -> TeacherPayload:
        """Convert a transport submission into the public Role Output."""

        output = (
            self.materializer(submission)
            if self.materializer is not None
            else submission
        )
        if not isinstance(output, final_type):
            raise TypeError(
                "Teacher output materializer returned "
                f"{type(output).__name__}; expected {final_type.__name__}"
            )
        return output


@dataclass(frozen=True)
class TeacherAgentSpec:
    """由目录模板装配出的中立 Teacher Agent 定义。"""

    manifest: HarnessManifest
    role: TeacherRoleDefinition
    prompt: TeacherPromptSpec
    output: TeacherOutputSpec
    tools: ToolSet
