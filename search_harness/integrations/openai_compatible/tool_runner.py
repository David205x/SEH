"""Role-neutral OpenAI-compatible native tool-calling Runner."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from search_harness.framework.tools import DefinedTool

from .model import OpenAICompatibleConfig


class OpenAICompatibleClient(Protocol):
    """Minimum asynchronous Chat Completions client boundary."""

    chat: Any

    async def close(self) -> None:
        """Close resources owned by the client."""


class OpenAICompatibleSyncClient(Protocol):
    """Minimum synchronous Chat Completions client boundary."""

    chat: Any

    def close(self) -> None:
        """Close resources owned by the client."""


@dataclass(frozen=True)
class NativeToolCall:
    """One auditable provider-native tool call."""

    name: str
    call_id: str
    arguments: dict[str, Any]
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class NativeToolRunResult:
    """Terminal output and transport evidence from one native tool run."""

    output: Any
    tool_calls: tuple[NativeToolCall, ...]
    usage: dict[str, Any]
    transcript: list[dict[str, Any]]


@dataclass(frozen=True)
class NativeToolRunFailure:
    """Auditable partial state retained when a bounded run is exhausted."""

    tool_calls: tuple[NativeToolCall, ...]
    usage: dict[str, Any]
    transcript: list[dict[str, Any]]
    finish_reasons: tuple[str | None, ...]
    turn_count: int


class NativeToolRunExhausted(RuntimeError):
    """Raised with complete partial evidence after max_turns is exhausted."""

    def __init__(self, message: str, failure: NativeToolRunFailure) -> None:
        super().__init__(message)
        self.failure = failure


@dataclass(frozen=True)
class PendingNativeToolCall:
    """One provider tool call awaiting local validation and execution."""

    name: str
    call_id: str
    arguments_text: str
    arguments: dict[str, Any]
    parse_error: str | None


@dataclass(frozen=True)
class NativeToolTurn:
    """One native assistant response before it is committed to a session."""

    request_messages: list[dict[str, Any]]
    assistant_message: dict[str, Any]
    tool_calls: tuple[PendingNativeToolCall, ...]
    usage: dict[str, Any]


class OpenAICompatibleToolSession:
    """Persistent synchronous native tool-calling conversation."""

    def __init__(
        self,
        *,
        config: OpenAICompatibleConfig,
        messages: list[dict[str, Any]],
        client: OpenAICompatibleSyncClient | None = None,
    ) -> None:
        self.config = config
        self._transcript = deepcopy(messages)
        self._client = client or OpenAI(
            api_key=config.api_key or "local",
            base_url=_api_base_url(config.base_url),
            timeout=config.timeout,
        )
        self._owns_client = client is None
        self._usage_calls: list[dict[str, Any]] = []
        self._tool_calls: list[NativeToolCall] = []

    def complete(self, *, tools: tuple[DefinedTool, ...]) -> NativeToolTurn:
        """Request one assistant turn using the currently active ToolSet."""

        request_messages = deepcopy(self._transcript)
        response = self._client.chat.completions.create(
            model=self.config.model_id,
            messages=request_messages,
            tools=[_defined_tool_schema(tool) for tool in tools],
            tool_choice="auto",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            extra_body=_request_extra_body(self.config),
            **_request_reasoning_options(self.config),
        )
        usage_value = (
            response.get("usage")
            if isinstance(response, dict)
            else getattr(response, "usage", None)
        )
        usage = _model_dump(usage_value)
        self._usage_calls.append(usage)
        message = _first_response_message(response)
        assistant_message = _assistant_message_payload(message)
        pending_calls: list[PendingNativeToolCall] = []
        for call in _message_tool_calls(message):
            name, call_id, arguments_text = _tool_call_fields(call)
            arguments, parse_error = _parse_tool_arguments(arguments_text)
            pending_calls.append(
                PendingNativeToolCall(
                    name=name,
                    call_id=call_id,
                    arguments_text=arguments_text,
                    arguments=arguments,
                    parse_error=parse_error,
                )
            )
        return NativeToolTurn(
            request_messages=request_messages,
            assistant_message=assistant_message,
            tool_calls=tuple(pending_calls),
            usage=usage,
        )

    def commit_assistant(self, turn: NativeToolTurn) -> None:
        """Commit a response whose native tool calls will receive results."""

        self._transcript.append(deepcopy(turn.assistant_message))

    def append_user_message(self, content: str) -> None:
        """Append protocol feedback without retaining an unusable response."""

        self._transcript.append({"role": "user", "content": content})

    def append_tool_result(
        self,
        *,
        call: PendingNativeToolCall,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        """Append one tool result and retain its auditable call record."""

        self._transcript.append(
            _tool_message(call_id=call.call_id, content=content)
        )
        self._tool_calls.append(
            NativeToolCall(
                name=call.name,
                call_id=call.call_id,
                arguments=(
                    dict(call.arguments)
                    if call.parse_error is None
                    else {"raw_arguments": call.arguments_text}
                ),
                content=content,
                metadata=dict(metadata),
            )
        )

    @property
    def transcript(self) -> list[dict[str, Any]]:
        """Return a detached structured transcript snapshot."""

        return deepcopy(self._transcript)

    @property
    def tool_calls(self) -> tuple[NativeToolCall, ...]:
        """Return committed native tool calls in execution order."""

        return tuple(self._tool_calls)

    @property
    def usage(self) -> dict[str, Any]:
        """Return aggregate usage for all requests in this session."""

        return _aggregate_usage(self._usage_calls)

    def close(self) -> None:
        """Close a client owned by this session."""

        if self._owns_client:
            self._client.close()


TerminalSubmitter = Callable[
    [dict[str, Any]],
    tuple[Any | None, str, dict[str, Any]],
]


class OpenAICompatibleToolRunner:
    """Execute one bounded asynchronous native function-calling loop."""

    def __init__(
        self,
        *,
        config: OpenAICompatibleConfig,
        client: OpenAICompatibleClient | None = None,
    ) -> None:
        self.config = config
        self.client = client

    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: tuple[DefinedTool, ...],
        terminal_tool_name: str,
        terminal_tool_description: str,
        terminal_output_schema: dict[str, Any],
        missing_terminal_message: str,
        submit_terminal: TerminalSubmitter,
        max_turns: int,
        run_label: str,
    ) -> NativeToolRunResult:
        """Run tools until one valid terminal submission is returned."""

        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        transcript = deepcopy(messages)
        runtime_tools = {tool.name: tool for tool in tools}
        tool_specs = [_defined_tool_schema(tool) for tool in tools]
        tool_specs.append(
            _terminal_tool_schema(
                name=terminal_tool_name,
                description=terminal_tool_description,
                output_schema=terminal_output_schema,
            )
        )
        client = self.client or AsyncOpenAI(
            api_key=self.config.api_key or "local",
            base_url=_api_base_url(self.config.base_url),
            timeout=self.config.timeout,
        )
        owns_client = self.client is None
        tool_calls: list[NativeToolCall] = []
        request_usage: list[dict[str, Any]] = []
        finish_reasons: list[str | None] = []
        previous_validation_signature: tuple[str, ...] | None = None
        output: Any | None = None
        try:
            for _turn in range(1, max_turns + 1):
                response = await client.chat.completions.create(
                    model=self.config.model_id,
                    messages=deepcopy(transcript),
                    tools=tool_specs,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    extra_body=_request_extra_body(self.config),
                    **_request_reasoning_options(self.config),
                )
                request_usage.append(_model_dump(response.usage))
                finish_reasons.append(_first_finish_reason(response))
                message = _first_response_message(response)
                transcript.append(_assistant_message_payload(message))
                native_calls = _message_tool_calls(message)
                if not native_calls:
                    transcript.append(
                        {
                            "role": "user",
                            "content": missing_terminal_message,
                        }
                    )
                    continue

                submitted_output: Any | None = None
                for call in native_calls:
                    name, call_id, arguments_text = _tool_call_fields(call)
                    arguments, parse_error = _parse_tool_arguments(
                        arguments_text
                    )
                    if parse_error is not None:
                        tool_calls.append(
                            NativeToolCall(
                                name=name,
                                call_id=call_id,
                                arguments={"raw_arguments": arguments_text},
                                content=parse_error,
                                metadata={"error_type": "invalid_json"},
                            )
                        )
                        transcript.append(
                            _tool_message(
                                call_id=call_id,
                                content=parse_error,
                            )
                        )
                        continue

                    if name == terminal_tool_name and len(native_calls) > 1:
                        content = (
                            "The terminal submit tool must be called alone. "
                            "Complete any other tools first, then submit in the "
                            "next response."
                        )
                        metadata = {"error_type": "batched_terminal_tool"}
                        candidate_output = None
                    elif name == terminal_tool_name:
                        candidate_output, content, metadata = (
                            submit_terminal(arguments)
                        )
                        signature = _validation_signature(metadata)
                        if (
                            signature is not None
                            and signature == previous_validation_signature
                        ):
                            content = (
                                "The same fields still fail validation. Preserve "
                                "the decision and all valid fields; repair only "
                                "the listed fields, then submit the complete "
                                f"object again.\n{content}"
                            )
                        previous_validation_signature = signature
                    else:
                        candidate_output = None
                        content, metadata = _run_defined_tool(
                            name=name,
                            arguments=arguments,
                            tools=runtime_tools,
                        )
                    tool_calls.append(
                        NativeToolCall(
                            name=name,
                            call_id=call_id,
                            arguments=arguments,
                            content=content,
                            metadata=metadata,
                        )
                    )
                    transcript.append(
                        _tool_message(call_id=call_id, content=content)
                    )
                    if candidate_output is not None:
                        submitted_output = candidate_output
                if submitted_output is not None:
                    output = submitted_output
                    break
        finally:
            if owns_client:
                await client.close()

        if output is None:
            raise NativeToolRunExhausted(
                (
                    f"{run_label} exhausted {max_turns} turns without valid "
                    "structured output"
                ),
                NativeToolRunFailure(
                    tool_calls=tuple(tool_calls),
                    usage=_aggregate_usage(request_usage),
                    transcript=transcript,
                    finish_reasons=tuple(finish_reasons),
                    turn_count=len(request_usage),
                ),
            )
        return NativeToolRunResult(
            output=output,
            tool_calls=tuple(tool_calls),
            usage=_aggregate_usage(request_usage),
            transcript=transcript,
        )


def _defined_tool_schema(tool: DefinedTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.definition.description,
            "parameters": tool.definition.to_json_schema(),
        },
    }


def _terminal_tool_schema(
    *,
    name: str,
    description: str,
    output_schema: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": output_schema,
        },
    }


def _run_defined_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    tools: dict[str, DefinedTool],
) -> tuple[str, dict[str, Any]]:
    tool = tools.get(name)
    if tool is None:
        return (
            f"Unknown tool '{name}'. Use one of: {sorted(tools)}",
            {"error_type": "unknown_tool"},
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
        return (
            f"Tool execution failed: {type(exc).__name__}: {exc}",
            {
                "error_type": "tool_execution_error",
                "exception_type": type(exc).__name__,
            },
        )
    return result.content, dict(result.metadata)


def _first_response_message(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("response has no choices")
    first_choice = choices[0]
    message = (
        first_choice.get("message")
        if isinstance(first_choice, dict)
        else getattr(first_choice, "message", None)
    )
    if message is None:
        raise ValueError("response choice has no message")
    return message


def _first_finish_reason(response: Any) -> str | None:
    choices = (
        response.get("choices")
        if isinstance(response, dict)
        else getattr(response, "choices", None)
    )
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    value = (
        first.get("finish_reason")
        if isinstance(first, dict)
        else getattr(first, "finish_reason", None)
    )
    return value if isinstance(value, str) else None


def _validation_signature(
    metadata: dict[str, Any],
) -> tuple[str, ...] | None:
    raw = metadata.get("validation_error_fields")
    if not isinstance(raw, list) or not all(
        isinstance(item, str) for item in raw
    ):
        return None
    return tuple(raw)


def _message_tool_calls(message: Any) -> list[Any]:
    calls = getattr(message, "tool_calls", None)
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls")
    if calls is None:
        return []
    if not isinstance(calls, list):
        raise TypeError("assistant tool_calls must be a list")
    return calls


def _tool_call_fields(call: Any) -> tuple[str, str, str]:
    if isinstance(call, dict):
        function = call.get("function")
        call_id = call.get("id")
    else:
        function = getattr(call, "function", None)
        call_id = getattr(call, "id", None)
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
    if not isinstance(name, str) or not name:
        raise ValueError("tool call has no function name")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError(f"tool call '{name}' has no call id")
    if not isinstance(arguments, str):
        raise TypeError(f"tool call '{name}' arguments must be JSON text")
    return name, call_id, arguments


def _parse_tool_arguments(
    raw_arguments: str,
) -> tuple[dict[str, Any], str | None]:
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        return {}, (
            "Tool arguments are invalid JSON. Correct them and call the tool "
            f"again: {exc.msg}"
        )
    if not isinstance(arguments, dict):
        return {}, "Tool arguments must be a JSON object."
    return arguments, None


def _assistant_message_payload(message: Any) -> dict[str, Any]:
    payload = _model_dump(message)
    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        payload.update(
            {
                key: value
                for key, value in extra.items()
                if value is not None and key not in payload
            }
        )
    if not payload:
        payload = {
            "role": "assistant",
            "content": getattr(message, "content", None),
        }
        calls = getattr(message, "tool_calls", None)
        if calls is not None:
            payload["tool_calls"] = [_model_dump(call) for call in calls]
    payload["role"] = "assistant"
    return payload


def _tool_message(*, call_id: str, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": content,
    }


def _model_dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json", exclude_none=True)
        if isinstance(payload, dict):
            return payload
    return {}


def _aggregate_usage(items: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = sum(
        _integer(item.get("prompt_tokens", item.get("input_tokens", 0)))
        for item in items
    )
    output_tokens = sum(
        _integer(
            item.get("completion_tokens", item.get("output_tokens", 0))
        )
        for item in items
    )
    total_tokens = sum(
        _integer(item.get("total_tokens", 0)) for item in items
    )
    return {
        "requests": len(items),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "calls": items,
    }


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _api_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    suffix = "/chat/completions"
    if normalized.endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized


def _request_extra_body(config: OpenAICompatibleConfig) -> dict[str, Any] | None:
    extra_body: dict[str, Any] = {}
    if config.seed is not None:
        extra_body["seed"] = config.seed
    if config.thinking_mode is not None:
        extra_body["thinking"] = {"type": config.thinking_mode}
    return extra_body or None


def _request_reasoning_options(
    config: OpenAICompatibleConfig,
) -> dict[str, str]:
    """Map the logical Ollama disable switch to its OpenAI-compatible field."""

    if config.ollama_think is False:
        return {"reasoning_effort": "none"}
    return {}
