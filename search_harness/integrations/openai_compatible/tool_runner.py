"""Role-neutral OpenAI-compatible native tool-calling Runner."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel

from search_harness.framework.tools import DefinedTool

from .model import OpenAICompatibleConfig


class OpenAICompatibleClient(Protocol):
    """Minimum asynchronous Chat Completions client boundary."""

    chat: Any

    async def close(self) -> None:
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
                    extra_body=(
                        {"seed": self.config.seed}
                        if self.config.seed is not None
                        else None
                    ),
                )
                request_usage.append(_model_dump(response.usage))
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
            raise RuntimeError(
                f"{run_label} exhausted {max_turns} turns without valid "
                "structured output"
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
    if not isinstance(choices, list) or not choices:
        raise ValueError("response has no choices")
    message = getattr(choices[0], "message", None)
    if message is None:
        raise ValueError("response choice has no message")
    return message


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
