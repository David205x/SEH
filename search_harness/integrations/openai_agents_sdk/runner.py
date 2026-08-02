"""Role-neutral OpenAI Agents SDK Runner adapter."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable

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

from search_harness.framework.tools import DefinedTool
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
)


OutputValidator = Callable[[BaseModel], None]


@dataclass(frozen=True)
class AgentsSdkToolCall:
    """One auditable tool call executed through the Agents SDK."""

    name: str
    arguments: dict[str, Any]
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AgentsSdkRunResult:
    """Output and transport evidence from one Agents SDK run."""

    output: BaseModel
    model: dict[str, Any]
    tool_calls: tuple[AgentsSdkToolCall, ...]
    usage: Any
    transcript: Any


class AgentsSdkRunner:
    """Execute one bounded Agent through the OpenAI Agents SDK."""

    def __init__(
        self,
        *,
        max_turns: int,
        output_mode: str,
        config: OpenAICompatibleConfig | None = None,
        model: Model | None = None,
        model_provenance: dict[str, Any] | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        if output_mode not in {"tool", "native"}:
            raise ValueError("output_mode must be tool or native")
        if model is None and config is None:
            raise ValueError("config is required when model is not injected")
        self.max_turns = max_turns
        self.output_mode = output_mode
        self.config = config
        self.model = model
        self.model_provenance = model_provenance

    async def run(
        self,
        *,
        agent_name: str,
        instructions: str,
        run_input: str,
        context: Any,
        tools: tuple[DefinedTool, ...],
        output_type: type[BaseModel],
        validate_output: OutputValidator,
        terminal_tool_name: str | None,
        terminal_tool_description: str,
        terminal_confirmation: str,
        missing_terminal_error: str,
        workflow_name: str,
    ) -> AgentsSdkRunResult:
        """Assemble and run one SDK Agent from transport-neutral inputs."""

        tool_calls: list[AgentsSdkToolCall] = []
        sdk_tools = [
            _adapt_tool(tool, collector=tool_calls) for tool in tools
        ]
        output_holder: list[BaseModel] = []
        if self.output_mode == "tool":
            if terminal_tool_name is None:
                raise ValueError("tool output mode requires terminal_tool_name")
            sdk_tools.append(
                _build_output_tool(
                    name=terminal_tool_name,
                    description=terminal_tool_description,
                    output_type=output_type,
                    output_holder=output_holder,
                    tool_calls=tool_calls,
                    validate_output=validate_output,
                )
            )

        model, settings, provenance, client = self._model_binding()
        agent = _build_sdk_agent(
            name=agent_name,
            instructions=instructions,
            model=model,
            settings=settings,
            tools=sdk_tools,
            output_mode=self.output_mode,
            output_type=output_type,
            output_holder=output_holder,
            terminal_confirmation=terminal_confirmation,
        )
        try:
            result = await Runner.run(
                agent,
                run_input,
                context=context,
                max_turns=self.max_turns,
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name=workflow_name,
                ),
            )
        finally:
            if client is not None:
                await client.close()

        if self.output_mode == "tool":
            if not output_holder:
                raise ValueError(missing_terminal_error)
            output = output_holder[0]
        else:
            output = result.final_output_as(
                output_type,
                raise_if_incorrect_type=True,
            )
        validate_output(output)
        return AgentsSdkRunResult(
            output=output,
            model=provenance,
            tool_calls=tuple(tool_calls),
            usage=_json_compatible(result.context_wrapper.usage),
            transcript=_json_compatible(result.to_input_list()),
        )

    def _model_binding(
        self,
    ) -> tuple[Model, ModelSettings, dict[str, Any], AsyncOpenAI | None]:
        if self.model is not None:
            return (
                self.model,
                ModelSettings(
                    parallel_tool_calls=False,
                    include_usage=True,
                ),
                self.model_provenance or {"provider": "injected"},
                None,
            )
        config = self.config
        if config is None:
            raise RuntimeError("missing OpenAI-compatible configuration")
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
        return model, _model_settings(config), config.provenance(), client


def _build_sdk_agent(
    *,
    name: str,
    instructions: str,
    model: Model,
    settings: ModelSettings,
    tools: list[FunctionTool],
    output_mode: str,
    output_type: type[BaseModel],
    output_holder: list[BaseModel],
    terminal_confirmation: str,
) -> Agent[Any]:
    if output_mode == "native":
        native_output_type: type[BaseModel] | None = output_type
        tool_use_behavior: str | ToolsToFinalOutputFunction = "run_llm_again"
    else:
        native_output_type = None
        tool_use_behavior = _output_submission_behavior(
            output_holder,
            terminal_confirmation=terminal_confirmation,
        )
    return Agent[Any](
        name=name,
        instructions=instructions,
        tools=tools,
        model=model,
        model_settings=settings,
        output_type=native_output_type,
        tool_use_behavior=tool_use_behavior,
    )


def _adapt_tool(
    tool: DefinedTool,
    *,
    collector: list[AgentsSdkToolCall],
) -> FunctionTool:
    async def invoke(_context: Any, raw_arguments: str) -> str:
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"SDK tool '{tool.name}' arguments are invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(arguments, dict):
            raise TypeError(
                f"SDK tool '{tool.name}' arguments must be an object"
            )
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
            content = f"Tool execution failed: {type(exc).__name__}: {exc}"
            collector.append(
                AgentsSdkToolCall(
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
        collector.append(
            AgentsSdkToolCall(
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
    description: str,
    output_type: type[BaseModel],
    output_holder: list[BaseModel],
    tool_calls: list[AgentsSdkToolCall],
    validate_output: OutputValidator,
) -> FunctionTool:
    async def submit(_context: Any, raw_arguments: str) -> str:
        try:
            output = output_type.model_validate_json(raw_arguments)
            validate_output(output)
        except (KeyError, ValidationError, ValueError) as exc:
            content = (
                "Structured output validation failed. Correct the listed "
                f"fields and call {name} again:\n{exc}"
            )
            tool_calls.append(
                AgentsSdkToolCall(
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
        output_holder.append(output)
        content = json.dumps(output.model_dump(mode="json"), ensure_ascii=False)
        tool_calls.append(
            AgentsSdkToolCall(
                name=name,
                arguments=output.model_dump(mode="json"),
                content=content,
                metadata={"terminal": True},
            )
        )
        return content

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=output_type.model_json_schema(),
        on_invoke_tool=submit,
        strict_json_schema=True,
    )


def _output_submission_behavior(
    output_holder: list[BaseModel],
    *,
    terminal_confirmation: str,
) -> ToolsToFinalOutputFunction:
    async def decide(
        _context: Any,
        _tool_results: list[Any],
    ) -> ToolsToFinalOutputResult:
        if not output_holder:
            return ToolsToFinalOutputResult(is_final_output=False)
        return ToolsToFinalOutputResult(
            is_final_output=True,
            final_output=terminal_confirmation,
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
            str(key): _json_compatible(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_compatible(model_dump(mode="json"))
    return str(value)
