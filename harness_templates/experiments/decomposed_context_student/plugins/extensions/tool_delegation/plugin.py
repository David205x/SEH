"""Delegate one controlled tool request through the main actor loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookPhase,
    HookModelRequest,
    ModelInput,
    StateRef,
    ToolCall,
)


_STATUS_KEY = "extension.tool_delegation.status"
_RESULT_KEY = "extension.tool_delegation.result"
_CALL_KEY = "extension.tool_delegation.requested_tool_call"

_INJECTION_MODES = frozenset({"user", "system_append", "replace_system"})
_QUERY_STRATEGIES = frozenset({"fixed", "question", "hook_model"})


class ToolDelegationHook(BaseHook):
    """Use the Actor's normal tool branch for one controlled request.

    The Hook never calls a tool itself.  It creates an ephemeral control frame,
    normalizes the Actor's tool call at the normal ``pre_tool`` boundary, then
    consumes the result through the following normal Actor generation.
    """

    def __init__(
        self,
        *,
        tool_name: str,
        arguments: dict[str, object],
        request_message: str,
        query_strategy: str = "fixed",
        injection_mode: str = "user",
        subtask_system_prompt: str = "",
        query_model_prompt: str = "",
        hook_id: str = "tool_delegation",
    ) -> None:
        if not tool_name.strip():
            raise ValueError("tool_name must not be empty")
        if not request_message.strip():
            raise ValueError("request_message must not be empty")
        if query_strategy not in _QUERY_STRATEGIES:
            raise ValueError(f"unsupported query_strategy: {query_strategy}")
        if injection_mode not in _INJECTION_MODES:
            raise ValueError(f"unsupported injection_mode: {injection_mode}")
        if injection_mode == "replace_system" and not subtask_system_prompt.strip():
            raise ValueError("replace_system requires subtask_system_prompt")
        if query_strategy == "hook_model" and not query_model_prompt.strip():
            raise ValueError("hook_model requires query_model_prompt")
        self._tool_name = tool_name
        self._arguments = dict(arguments)
        self._request_message = request_message.strip()
        self._query_strategy = query_strategy
        self._injection_mode = injection_mode
        self._subtask_system_prompt = subtask_system_prompt.strip()
        self._query_model_prompt = query_model_prompt.strip()
        super().__init__(
            hook_id=hook_id,
            phases=frozenset(
                {
                    HookPhase.POST_PROMPT,
                    HookPhase.PRE_TOOL,
                    HookPhase.POST_TOOL,
                }
            ),
            state_refs=(
                StateRef(
                    key=_STATUS_KEY,
                    owner=hook_id,
                    value_type=str,
                    writers=frozenset({hook_id}),
                    default="requested",
                ),
                StateRef(
                    key=_RESULT_KEY,
                    owner=hook_id,
                    value_type=str,
                    writers=frozenset({hook_id}),
                    default="",
                ),
                StateRef(
                    key=_CALL_KEY,
                    owner=hook_id,
                    value_type=dict,
                    writers=frozenset({hook_id}),
                    default={"name": tool_name, "arguments": dict(arguments)},
                ),
            ),
            writable_stage_keys=frozenset({"stage.model_input", "stage.tool_call"}),
            model_profiles=(frozenset({"student"}) if query_strategy == "hook_model" else frozenset()),
        )

    def handle(self, context: HookContext) -> None:
        status = context.state.get(_STATUS_KEY)
        if context.phase == HookPhase.POST_PROMPT:
            self._handle_post_prompt(context, status)
            return
        if context.phase == HookPhase.PRE_TOOL:
            self._handle_pre_tool(context, status)
            return
        if context.phase == HookPhase.POST_TOOL:
            self._handle_post_tool(context, status)
            return
        raise RuntimeError(f"unexpected delegation phase: {context.phase}")

    def _handle_post_prompt(self, context: HookContext, status: str) -> None:
        model_input = context.state.get("stage.model_input")
        if not isinstance(model_input, ModelInput):
            raise TypeError("stage.model_input must be a ModelInput")

        if status == "requested":
            tool_call = self._build_requested_call(context)
            control = (
                "Harness delegation request: call exactly one tool now. "
                f"Use {tool_call.name} with arguments {tool_call.arguments}. "
                f"Purpose: {self._request_message}"
            )
            context.state.set("stage.model_input", self._inject_control(model_input, control))
            context.state.set(_CALL_KEY, tool_call.to_dict())
            context.state.set(_STATUS_KEY, "awaiting_tool_result")
            return

        if status == "result_ready":
            result = context.state.get(_RESULT_KEY)
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [
                        *model_input.messages,
                        ChatMessage(
                            role="user",
                            content=(
                                "Delegated tool result is available. Resume the original task "
                                f"using this evidence: {result}"
                            ),
                        ),
                    ]
                ),
            )
            context.state.set(_STATUS_KEY, "completed")

    def _handle_pre_tool(self, context: HookContext, status: str) -> None:
        if status != "awaiting_tool_result":
            return
        # The core still executes the Actor's normal tool branch. This replacement
        # only makes the already-authorized delegation request deterministic.
        payload = context.state.get(_CALL_KEY)
        if not isinstance(payload, dict):
            raise TypeError("delegation requested_tool_call must be an object")
        name = payload.get("name")
        arguments = payload.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise TypeError("delegation requested_tool_call has invalid shape")
        context.state.set("stage.tool_call", ToolCall(name=name, arguments=arguments))

    def _handle_post_tool(self, context: HookContext, status: str) -> None:
        if status != "awaiting_tool_result":
            return
        tool_result = context.state.get("stage.tool_result")
        result_content = getattr(tool_result, "content", None)
        if not isinstance(result_content, str):
            raise TypeError("stage.tool_result must expose string content")
        context.state.set(_RESULT_KEY, result_content)
        context.state.set(_STATUS_KEY, "result_ready")

    def _build_requested_call(self, context: HookContext) -> ToolCall:
        arguments = dict(self._arguments)
        if self._query_strategy == "question":
            arguments["query"] = context.state.get("core.question")
        elif self._query_strategy == "hook_model":
            question = context.state.get("core.question")
            if not isinstance(question, str):
                raise TypeError("core.question must be a string")
            response = context.call_model(
                HookModelRequest(
                    profile="student",
                    purpose="generate_delegated_search_query",
                    model_input=ModelInput.from_messages(
                        [
                            ChatMessage(role="system", content=self._query_model_prompt),
                            ChatMessage(role="user", content=question),
                        ]
                    ),
                )
            )
            payload = _parse_query_payload(response.raw_output)
            arguments["query"] = payload
        return ToolCall(name=self._tool_name, arguments=arguments)

    def _inject_control(self, model_input: ModelInput, control: str) -> ModelInput:
        if self._injection_mode == "user":
            return ModelInput.from_messages(
                [*model_input.messages, ChatMessage(role="user", content=control)]
            )

        messages = list(model_input.messages)
        system_index = next(
            (index for index, message in enumerate(messages) if message.role == "system"),
            None,
        )
        if system_index is None:
            raise ValueError("delegation system injection requires one system message")
        system = messages[system_index]
        if self._injection_mode == "system_append":
            content = f"{system.content}\n\n{control}"
        else:
            content = f"{self._subtask_system_prompt}\n\n{control}"
        messages[system_index] = ChatMessage(role="system", content=content)
        return ModelInput.from_messages(messages)


def build(config: dict[str, Any], context: Any) -> ToolDelegationHook:
    """Build one deterministic delegation transaction from manifest config."""

    allowed = {
        "tool_name",
        "arguments",
        "request_message",
        "query_strategy",
        "injection_mode",
        "subtask_system_prompt_file",
        "query_model_prompt_file",
    }
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"tool_delegation has unsupported config keys: {sorted(unknown)}")
    tool_name = config.get("tool_name")
    arguments = config.get("arguments")
    request_message = config.get("request_message")
    query_strategy = config.get("query_strategy", "fixed")
    injection_mode = config.get("injection_mode", "user")
    if not isinstance(tool_name, str):
        raise TypeError("tool_delegation.tool_name must be a string")
    if not isinstance(arguments, dict):
        raise TypeError("tool_delegation.arguments must be an object")
    if not isinstance(request_message, str):
        raise TypeError("tool_delegation.request_message must be a string")
    if not isinstance(query_strategy, str):
        raise TypeError("tool_delegation.query_strategy must be a string")
    if not isinstance(injection_mode, str):
        raise TypeError("tool_delegation.injection_mode must be a string")
    return ToolDelegationHook(
        tool_name=tool_name,
        arguments=arguments,
        request_message=request_message,
        query_strategy=query_strategy,
        injection_mode=injection_mode,
        subtask_system_prompt=_load_optional_template(
            context, config.get("subtask_system_prompt_file")
        ),
        query_model_prompt=_load_optional_template(
            context, config.get("query_model_prompt_file")
        ),
    )


def _load_optional_template(context: Any, value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise TypeError("tool_delegation prompt file must be a non-empty string")
    root = getattr(context, "plugins_root", None)
    if not isinstance(root, Path):
        raise TypeError("tool_delegation requires PluginContext.plugins_root")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("tool_delegation prompt file must stay inside plugins root") from exc
    return path.read_text(encoding="utf-8")


def _parse_query_payload(raw_output: str) -> str:
    """Parse one Hook-model JSON object while tolerating surrounding explanation."""

    start = raw_output.find("{")
    if start < 0:
        raise ValueError("query model output must contain a JSON object")
    payload, _ = json.JSONDecoder().raw_decode(raw_output[start:])
    if not isinstance(payload, dict):
        raise ValueError("query model output must be a JSON object")
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query model output must contain a non-empty query string")
    return query.strip()
