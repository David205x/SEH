"""Delegate one deterministic tool request through the main actor loop."""

from __future__ import annotations

from typing import Any

from search_harness.core import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookPhase,
    ModelInput,
    StateRef,
    ToolCall,
)


_STATUS_KEY = "extension.tool_delegation.status"
_RESULT_KEY = "extension.tool_delegation.result"


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
        hook_id: str = "tool_delegation",
    ) -> None:
        if not tool_name.strip():
            raise ValueError("tool_name must not be empty")
        if not request_message.strip():
            raise ValueError("request_message must not be empty")
        self._tool_call = ToolCall(name=tool_name, arguments=dict(arguments))
        self._request_message = request_message.strip()
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
            ),
            writable_stage_keys=frozenset({"stage.model_input", "stage.tool_call"}),
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
            control = (
                "Harness delegation request: call exactly one tool now. "
                f"Use {self._tool_call.name} with arguments {self._tool_call.arguments}. "
                f"Purpose: {self._request_message}"
            )
            context.state.set(
                "stage.model_input",
                ModelInput.from_messages(
                    [*model_input.messages, ChatMessage(role="user", content=control)]
                ),
            )
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
        context.state.set("stage.tool_call", self._tool_call)

    def _handle_post_tool(self, context: HookContext, status: str) -> None:
        if status != "awaiting_tool_result":
            return
        tool_result = context.state.get("stage.tool_result")
        result_content = getattr(tool_result, "content", None)
        if not isinstance(result_content, str):
            raise TypeError("stage.tool_result must expose string content")
        context.state.set(_RESULT_KEY, result_content)
        context.state.set(_STATUS_KEY, "result_ready")


def build(config: dict[str, Any], context: Any) -> ToolDelegationHook:
    """Build one deterministic delegation transaction from manifest config."""

    del context
    allowed = {"tool_name", "arguments", "request_message"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"tool_delegation has unsupported config keys: {sorted(unknown)}")
    tool_name = config.get("tool_name")
    arguments = config.get("arguments")
    request_message = config.get("request_message")
    if not isinstance(tool_name, str):
        raise TypeError("tool_delegation.tool_name must be a string")
    if not isinstance(arguments, dict):
        raise TypeError("tool_delegation.arguments must be an object")
    if not isinstance(request_message, str):
        raise TypeError("tool_delegation.request_message must be a string")
    return ToolDelegationHook(
        tool_name=tool_name,
        arguments=arguments,
        request_message=request_message,
    )
