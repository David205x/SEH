"""OpenAI Agents SDK 驱动的 standalone Teacher 角色运行器。"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from search_harness._internal import read_runtime_config, teacher_role_budget
from search_harness.integrations.openai_agents_sdk import AgentsSdkRunner
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
)

from .contracts import TeacherPayload
from ..resources.base import TeacherResourceConfig
from .role_execution import (
    build_role_artifact,
    prepare_role_run,
    validate_role_output,
)
from .provenance import input_view_digest, model_input_view


class AgentsSdkRoleRunner:
    """使用 OpenAI Agents SDK 执行一个 Teacher 角色。"""

    def __init__(
        self,
        *,
        env_file: Path | None = None,
        max_turns: int = 15,
        output_mode: str = "tool",
    ) -> None:
        if max_turns < 1:
            raise ValueError("Teacher max_turns must be positive")
        if output_mode not in {"tool", "native"}:
            raise ValueError("Teacher output_mode must be tool or native")
        self.env_file = env_file
        self.max_turns = max_turns
        self.output_mode = output_mode

    async def run(
        self,
        *,
        template_root: Path,
        role_input: dict[str, Any],
        resource_config: TeacherResourceConfig,
        role_id: str,
        role_version: int = 1,
        model: Any | None = None,
        model_provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行一次角色调用并返回可直接持久化的完整 artifact。"""

        if model is not None and model_provenance is None:
            raise ValueError(
                "injected Teacher model requires explicit model_provenance"
            )
        prepared = prepare_role_run(
            template_root=template_root,
            role_input=role_input,
            resource_config=resource_config,
            role_id=role_id,
            role_version=role_version,
        )
        resources = prepared.resources
        spec = prepared.spec
        output_tool_name: str | None = None
        if self.output_mode == "tool":
            output_tool_name = f"submit_{spec.role.output_contract_id}"
        terminal_tool_description = (
            "Submit the final validated role result. Call this only after "
            "all necessary evidence and tools have been inspected."
        )
        submission_type = spec.output.model_submission_type(
            spec.role.output_type
        )
        output_schema = submission_type.model_json_schema()
        terminal_tool = (
            {
                "type": "function",
                "function": {
                    "name": output_tool_name,
                    "description": terminal_tool_description,
                    "parameters": output_schema,
                },
            }
            if output_tool_name is not None
            else None
        )
        model_input = model_input_view(
            messages=[
                {"role": "system", "content": spec.prompt.instructions},
                {"role": "user", "content": prepared.rendered_input},
            ],
            tools=spec.tools.tools,
            terminal_tool=terminal_tool,
            structured_output_schema=(
                output_schema if self.output_mode == "native" else None
            ),
        )
        input_digest = input_view_digest([model_input])
        config = (
            OpenAICompatibleConfig.from_env(
                env_file=self.env_file,
                prefix="TEACHER",
            )
            if model is None
            else None
        )
        default_max_tokens = config.max_tokens if config is not None else 1024
        budget = teacher_role_budget(
            (
                read_runtime_config(env_file=self.env_file)
                if model is None
                else {}
            ),
            spec.role.role_id,
            default_max_tokens=default_max_tokens,
            default_max_turns=self.max_turns,
            default_thinking_mode=(
                config.configured_thinking_mode
                if config is not None
                else None
            ),
        )
        if config is not None:
            config = replace(config, max_tokens=budget.max_tokens)
            config = config.with_configured_thinking_mode(
                budget.thinking_mode
            )
        sdk_result = await AgentsSdkRunner(
            max_turns=budget.max_turns,
            output_mode=self.output_mode,
            config=config,
            model=model,
            model_provenance=model_provenance,
        ).run(
            agent_name=spec.manifest.harness_id,
            instructions=spec.prompt.instructions,
            run_input=prepared.rendered_input,
            context=resources,
            tools=spec.tools.tools,
            output_type=submission_type,
            validate_output=lambda submission: validate_role_output(
                spec.output.materialize(
                    submission,
                    final_type=spec.role.output_type,
                ),
                resources,
            ),
            terminal_tool_name=output_tool_name,
            terminal_tool_description=terminal_tool_description,
            terminal_confirmation="Structured Teacher output submitted.",
            missing_terminal_error=(
                "Teacher did not submit a terminal structured output"
            ),
            workflow_name=f"teacher:{spec.role.role_id}",
        )
        submission = sdk_result.output
        if not isinstance(submission, TeacherPayload):
            raise TypeError("Agents SDK returned an invalid role output")
        output = spec.output.materialize(
            submission,
            final_type=spec.role.output_type,
        )
        validate_role_output(output, resources)
        return build_role_artifact(
            prepared,
            runtime="agents_sdk",
            model=sdk_result.model,
            input_view_digest=input_digest,
            output=output,
            tool_calls=[asdict(call) for call in sdk_result.tool_calls],
            usage=sdk_result.usage,
            transcript=sdk_result.transcript,
            runtime_fields={
                "output_mode": self.output_mode,
                "role_budget": {
                    "max_tokens": budget.max_tokens,
                    "max_turns": budget.max_turns,
                },
            },
        )
