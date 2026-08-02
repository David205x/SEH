"""Inject one follow-up instruction after each completed search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookPhase,
    ModelInput,
    StateRef,
    ToolCall,
)


DEFAULT_TEMPLATE = "templates/guidance.md"
PENDING_QUERY = "extension.result_guidance.pending_query"


class ResultGuidanceHook(BaseHook):
    """Carry a post-tool event into the next post-prompt model input."""

    def __init__(
        self,
        *,
        message_template: str,
        hook_id: str = "result_guidance",
    ) -> None:
        if "{{query}}" not in message_template:
            raise ValueError("result guidance template must contain {{query}}")
        self._message_template = message_template.strip()
        super().__init__(
            hook_id=hook_id,
            phases=frozenset({HookPhase.POST_TOOL, HookPhase.POST_PROMPT}),
            state_refs=(
                StateRef(
                    key=PENDING_QUERY,
                    owner=hook_id,
                    value_type=str,
                    writers=frozenset({hook_id}),
                    default="",
                ),
            ),
            writable_stage_keys=frozenset({"stage.model_input"}),
        )

    def handle(self, context: HookContext) -> None:
        if context.phase == HookPhase.POST_TOOL:
            self._remember_completed_search(context)
            return
        if context.phase == HookPhase.POST_PROMPT:
            self._inject_follow_up(context)
            return
        raise RuntimeError(f"unexpected result guidance phase: {context.phase}")

    def _remember_completed_search(self, context: HookContext) -> None:
        tool_call = context.state.get("stage.tool_call")
        if not isinstance(tool_call, ToolCall):
            raise TypeError("stage.tool_call must be a ToolCall")
        if tool_call.name != "search":
            return
        query = tool_call.arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("search query must be a non-empty string")
        context.state.set(PENDING_QUERY, query.strip())

    def _inject_follow_up(self, context: HookContext) -> None:
        query = context.state.get(PENDING_QUERY)
        if not isinstance(query, str):
            raise TypeError("pending query must be a string")
        if not query:
            return

        model_input = context.state.get("stage.model_input")
        if not isinstance(model_input, ModelInput):
            raise TypeError("stage.model_input must be a ModelInput")
        message = self._message_template.replace("{{query}}", query)
        context.state.set(
            "stage.model_input",
            ModelInput(
                messages=(
                    *model_input.messages,
                    ChatMessage(role="user", content=message),
                )
            ),
        )
        context.state.set(PENDING_QUERY, "")


def build(config: dict[str, Any], context: Any) -> ResultGuidanceHook:
    """Build the two-phase guidance injector."""

    del context
    allowed = {"template"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(
            f"result_guidance has unsupported config keys: {sorted(unknown)}"
        )
    template = config.get("template", DEFAULT_TEMPLATE)
    if not isinstance(template, str):
        raise TypeError("result_guidance template must be a string")
    path = _resolve_local_path(template)
    return ResultGuidanceHook(
        message_template=path.read_text(encoding="utf-8"),
    )


def _resolve_local_path(relative_path: str) -> Path:
    root = Path(__file__).resolve().parent
    path = (root / relative_path).resolve()
    if root not in path.parents and path != root:
        raise ValueError(
            "result_guidance template must stay inside its plugin directory"
        )
    return path
