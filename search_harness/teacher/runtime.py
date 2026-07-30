"""OpenAI Agents SDK 驱动的 standalone Teacher 角色运行器。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import (
    Agent,
    FunctionTool,
    Model,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
    ToolsToFinalOutputResult,
)
from agents.agent import ToolsToFinalOutputFunction
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from search_harness.framework.tooling import DefinedTool
from search_harness.models import OpenAICompatibleConfig

from .contracts import (
    CandidateReview,
    CompilerResult,
    EvidenceReview,
    FailureDirection,
    InterventionHypothesis,
    InterventionWorkerResult,
    MechanismDistillation,
    TeacherPayload,
    TrialReview,
)
from .loader import load_teacher_agent_spec
from .resources import TeacherResourceConfig, TeacherResources
from .spec import TeacherAgentSpec


@dataclass(frozen=True)
class TeacherToolCall:
    """一次经过当前 ToolDefinition 验证的 SDK 工具调用。"""

    name: str
    arguments: dict[str, Any]
    content: str
    metadata: dict[str, Any]


@dataclass
class TeacherToolSession:
    """收集本次角色运行产生的工具调用。"""

    calls: list[TeacherToolCall]

    def __init__(self) -> None:
        self.calls = []


@dataclass
class TeacherOutputSession:
    """保存 Pydantic 终态提交工具解析出的结果。"""

    output: TeacherPayload | None = None


class AgentsSdkTeacherRuntime:
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
        model: Model | None = None,
        model_provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行一次角色调用并返回可直接持久化的完整 artifact。"""

        resources = TeacherResources.from_config(resource_config)
        spec = load_teacher_agent_spec(
            template_root,
            runtime_context=resources,
        )
        validated_input = spec.role.input_type.model_validate(role_input)
        resources.bind_role_input(validated_input)
        user_input = spec.prompt.render_input(
            validated_input,
            resources.model_context(spec.role.role_id),
        )
        tool_session = TeacherToolSession()
        sdk_tools = [
            _adapt_tool(tool, session=tool_session)
            for tool in spec.tools.tools
        ]
        output_session = TeacherOutputSession()
        output_tool_name: str | None = None
        if self.output_mode == "tool":
            output_tool_name = f"submit_{spec.role.output_contract_id}"
            sdk_tools.append(
                _build_output_tool(
                    name=output_tool_name,
                    output_type=spec.role.output_type,
                    output_session=output_session,
                    tool_session=tool_session,
                    resources=resources,
                )
            )

        client: AsyncOpenAI | None = None
        if model is None:
            config = OpenAICompatibleConfig.from_env(
                env_file=self.env_file,
                prefix="TEACHER",
            )
            client = AsyncOpenAI(
                api_key=config.api_key or "local",
                base_url=_sdk_base_url(config.base_url),
                timeout=config.timeout,
            )
            model = OpenAIChatCompletionsModel(
                model=config.model_id,
                openai_client=client,
                buffer_streamed_tool_calls=True,
            )
            settings = _model_settings(config)
            provenance = config.provenance()
        else:
            settings = ModelSettings(
                parallel_tool_calls=False,
                include_usage=True,
            )
            provenance = model_provenance or {"provider": "injected"}

        agent = _build_sdk_agent(
            spec,
            model=model,
            settings=settings,
            tools=sdk_tools,
            output_mode=self.output_mode,
            output_tool_name=output_tool_name,
            output_session=output_session,
        )
        try:
            result = await Runner.run(
                agent,
                user_input,
                context=resources,
                max_turns=self.max_turns,
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name=f"teacher:{spec.role.role_id}",
                ),
            )
        finally:
            if client is not None:
                await client.close()

        if self.output_mode == "tool":
            if output_session.output is None:
                raise ValueError("Teacher did not submit a terminal structured output")
            output = output_session.output
        else:
            output = result.final_output_as(
                spec.role.output_type,
                raise_if_incorrect_type=True,
            )
        _validate_role_result(output, resources)
        output_schema = spec.role.output_type.model_json_schema()
        return {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "template_root": str(template_root.resolve()),
            "harness_id": spec.manifest.harness_id,
            "role": {
                "id": spec.role.role_id,
                "version": spec.role.version,
            },
            "output_contract": {
                "id": spec.role.output_contract_id,
                "version": spec.role.output_contract_version,
                "schema_digest": _schema_digest(output_schema),
            },
            "runtime": "agents_sdk",
            "model": provenance,
            "output_mode": self.output_mode,
            "input": validated_input.model_dump(mode="json"),
            "resource_config": resource_config.model_dump(mode="json"),
            "output": output.model_dump(mode="json"),
            "validated_mechanisms": resources.mechanisms.validated_payloads(),
            "resource_artifacts": resources.artifacts(),
            "tool_calls": [asdict(call) for call in tool_session.calls],
            "usage": _json_compatible(result.context_wrapper.usage),
            "transcript": _json_compatible(result.to_input_list()),
        }


def _build_sdk_agent(
    spec: TeacherAgentSpec,
    *,
    model: Model,
    settings: ModelSettings,
    tools: list[FunctionTool],
    output_mode: str,
    output_tool_name: str | None,
    output_session: TeacherOutputSession,
) -> Agent[TeacherResources]:
    if output_mode == "native":
        output_type: type[TeacherPayload] | None = spec.role.output_type
        tool_use_behavior: str | ToolsToFinalOutputFunction = "run_llm_again"
    else:
        if output_tool_name is None:
            raise ValueError("tool output mode requires output_tool_name")
        output_type = None
        tool_use_behavior = _output_submission_behavior(output_session)
    return Agent[TeacherResources](
        name=spec.manifest.harness_id,
        instructions=spec.prompt.instructions,
        tools=tools,
        model=model,
        model_settings=settings,
        output_type=output_type,
        tool_use_behavior=tool_use_behavior,
    )


def _adapt_tool(
    tool: DefinedTool,
    *,
    session: TeacherToolSession,
) -> FunctionTool:
    async def invoke(_context: Any, raw_arguments: str) -> str:
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"SDK tool '{tool.name}' arguments are invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(arguments, dict):
            raise TypeError(f"SDK tool '{tool.name}' arguments must be an object")
        try:
            result = tool.run(arguments)
        except (
            FileNotFoundError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            content = (
                f"Tool execution failed: {type(exc).__name__}: {exc}"
            )
            session.calls.append(
                TeacherToolCall(
                    name=tool.name,
                    arguments=dict(arguments),
                    content=content,
                    metadata={
                        "error_type": "tool_execution_error",
                        "exception_type": type(exc).__name__,
                    },
                )
            )
            return content
        session.calls.append(
            TeacherToolCall(
                name=tool.name,
                arguments=dict(arguments),
                content=result.content,
                metadata=dict(result.metadata),
            )
        )
        return result.content

    return FunctionTool(
        name=tool.name,
        description=tool.definition.description,
        params_json_schema=tool.definition.to_json_schema(),
        on_invoke_tool=invoke,
        strict_json_schema=True,
    )


def _build_output_tool(
    *,
    name: str,
    output_type: type[TeacherPayload],
    output_session: TeacherOutputSession,
    tool_session: TeacherToolSession,
    resources: TeacherResources,
) -> FunctionTool:
    async def submit(_context: Any, raw_arguments: str) -> str:
        try:
            output = output_type.model_validate_json(raw_arguments)
            _validate_role_result(output, resources)
        except (KeyError, ValidationError, ValueError) as exc:
            content = (
                "Structured output validation failed. Correct the listed "
                f"fields and call {name} again:\n{exc}"
            )
            tool_session.calls.append(
                TeacherToolCall(
                    name=name,
                    arguments=_json_object_or_raw(raw_arguments),
                    content=content,
                    metadata={
                        "terminal": False,
                        "validation_error": True,
                    },
                )
            )
            return content
        output_session.output = output
        content = json.dumps(
            output.model_dump(mode="json"),
            ensure_ascii=False,
        )
        tool_session.calls.append(
            TeacherToolCall(
                name=name,
                arguments=output.model_dump(mode="json"),
                content=content,
                metadata={"terminal": True},
            )
        )
        return content

    return FunctionTool(
        name=name,
        description=(
            "Submit the final validated role result. Call this only after all "
            "necessary evidence and tools have been inspected."
        ),
        params_json_schema=output_type.model_json_schema(),
        on_invoke_tool=submit,
        strict_json_schema=True,
    )


def _output_submission_behavior(
    output_session: TeacherOutputSession,
) -> ToolsToFinalOutputFunction:
    async def decide(
        _context: Any,
        _tool_results: list[Any],
    ) -> ToolsToFinalOutputResult:
        if output_session.output is None:
            return ToolsToFinalOutputResult(is_final_output=False)
        return ToolsToFinalOutputResult(
            is_final_output=True,
            final_output="Structured Teacher output submitted.",
        )

    return decide


def _json_object_or_raw(raw_arguments: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {"raw_arguments": raw_arguments}
    if isinstance(payload, dict):
        return payload
    return {"raw_arguments": raw_arguments}


def _model_settings(config: OpenAICompatibleConfig) -> ModelSettings:
    extra_body: dict[str, Any] | None = None
    if config.seed is not None:
        extra_body = {"seed": config.seed}
    return ModelSettings(
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        parallel_tool_calls=False,
        include_usage=True,
        extra_body=extra_body,
    )


def _sdk_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    suffix = "/chat/completions"
    if normalized.endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized


def _validate_role_result(
    output: TeacherPayload,
    resources: TeacherResources,
) -> None:
    if isinstance(output, FailureDirection):
        if resources.evaluation is None:
            raise ValueError("Failure Analyst resources are unavailable")
        resources.evaluation.validate_evidence_refs(output.evidence_refs)
    if isinstance(output, InterventionHypothesis):
        resources.validate_hypothesis_research()
    if isinstance(output, EvidenceReview):
        resources.validate_evidence_review(output)
    if isinstance(output, TrialReview):
        if resources.trials is None:
            raise ValueError("Trial Reviewer resources are unavailable")
        resources.trials.validate_trial_review(output)
    if isinstance(output, MechanismDistillation) and output.decision == "distilled":
        if output.mechanism_ref is None:
            raise ValueError("distilled result lacks mechanism_ref")
        resources.mechanisms.resolve(output.mechanism_ref)
    if isinstance(output, InterventionWorkerResult):
        raise ValueError(
            "Intervention Worker must run through "
            "InterventionRoleRuntime so one transcript can span Hook phases"
        )
    if isinstance(output, CompilerResult) and output.decision == "submitted":
        if resources.compiler is None:
            raise ValueError("Compiler resources are unavailable")
        if output.candidate_ref is None:
            raise ValueError("submitted Compiler result lacks candidate_ref")
        resources.compiler.resolve(output.candidate_ref)
    if isinstance(output, CandidateReview):
        if resources.candidate_review is None:
            raise ValueError("Candidate Reviewer resources are unavailable")
        resources.candidate_review.validate_review()


def _schema_digest(schema: dict[str, Any]) -> str:
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_compatible(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return {
            key: _json_compatible(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {
            str(key): _json_compatible(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_compatible(value.model_dump(mode="json"))
    return str(value)
