"""Plan retrieval subtasks, then reset the Actor context for each subtask."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.core import (
    BaseHook,
    ChatMessage,
    HookContext,
    HookModelRequest,
    HookPhase,
    ModelInput,
    ParsedOutput,
    StateRef,
    ToolCall,
)


_STATUS = "extension.decomposed_context_controller.status"
_PLAN = "extension.decomposed_context_controller.plan"
_INDEX = "extension.decomposed_context_controller.index"
_EVIDENCE = "extension.decomposed_context_controller.evidence"
_PLANNER_ERROR = "extension.decomposed_context_controller.planner_error"


class DecomposedContextControllerHook(BaseHook):
    """Use one Hook-model plan to control a finite Actor subtask state machine."""

    def __init__(
        self,
        *,
        planner_prompt: str,
        subtask_system_prompt: str,
        synthesis_system_prompt: str,
        max_subtasks: int,
        topk: int,
        max_evidence_chars: int,
        hook_id: str = "decomposed_context_controller",
    ) -> None:
        if max_subtasks < 1:
            raise ValueError("max_subtasks must be positive")
        if topk < 1:
            raise ValueError("topk must be positive")
        if max_evidence_chars < 1:
            raise ValueError("max_evidence_chars must be positive")
        self._planner_prompt = planner_prompt.strip()
        self._subtask_system_prompt = subtask_system_prompt.strip()
        self._synthesis_system_prompt = synthesis_system_prompt.strip()
        if not all((self._planner_prompt, self._subtask_system_prompt, self._synthesis_system_prompt)):
            raise ValueError("controller prompt templates must not be empty")
        self._max_subtasks = max_subtasks
        self._topk = topk
        self._max_evidence_chars = max_evidence_chars
        super().__init__(
            hook_id=hook_id,
            phases=frozenset(
                {
                    HookPhase.PRE_PROMPT,
                    HookPhase.POST_PROMPT,
                    HookPhase.POST_PARSE,
                    HookPhase.PRE_TOOL,
                    HookPhase.POST_TOOL,
                    HookPhase.PRE_FINAL,
                }
            ),
            state_refs=(
                StateRef(
                    key=_STATUS,
                    owner=hook_id,
                    value_type=str,
                    writers=frozenset({hook_id}),
                    default="unplanned",
                ),
                StateRef(
                    key=_PLAN,
                    owner=hook_id,
                    value_type=dict,
                    writers=frozenset({hook_id}),
                    default={"subtasks": []},
                ),
                StateRef(
                    key=_INDEX,
                    owner=hook_id,
                    value_type=int,
                    writers=frozenset({hook_id}),
                    default=0,
                ),
                StateRef(
                    key=_EVIDENCE,
                    owner=hook_id,
                    value_type=list,
                    writers=frozenset({hook_id}),
                    default=[],
                ),
                StateRef(
                    key=_PLANNER_ERROR,
                    owner=hook_id,
                    value_type=str,
                    writers=frozenset({hook_id}),
                    default="",
                ),
            ),
            writable_stage_keys=frozenset(
                {
                    "stage.model_input",
                    "stage.parsed_output",
                    "stage.tool_call",
                }
            ),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        status = context.state.get(_STATUS)
        if context.phase == HookPhase.PRE_PROMPT:
            if status == "unplanned":
                self._plan(context)
            return
        if context.phase == HookPhase.POST_PROMPT:
            self._reset_actor_context(context, status)
            return
        if context.phase == HookPhase.POST_PARSE:
            self._bridge_bare_tool_json(context, status)
            return
        if context.phase == HookPhase.PRE_TOOL:
            self._normalize_subtask_call(context, status)
            return
        if context.phase == HookPhase.POST_TOOL:
            self._advance_after_tool(context, status)
            return
        if context.phase == HookPhase.PRE_FINAL:
            if status == "awaiting_final":
                context.state.set(_STATUS, "completed")
            elif status == "awaiting_tool":
                # Keep this explicit in trace: the Actor escaped a forced subtask.
                context.state.set(_STATUS, "actor_final_before_subtask_tool")
            return
        raise RuntimeError(f"unexpected controller phase: {context.phase}")

    def _plan(self, context: HookContext) -> None:
        question = context.state.get("core.question")
        if not isinstance(question, str):
            raise TypeError("core.question must be a string")
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="plan_retrieval_subtasks",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=self._planner_prompt),
                        ChatMessage(role="user", content=question),
                    ]
                ),
            )
        )
        try:
            plan = _parse_plan(response.raw_output, self._max_subtasks)
        except ValueError as exc:
            plan = {
                "subtasks": [
                    {
                        "task": "Retrieve direct evidence for the original question.",
                        "query": question,
                    }
                ]
            }
            context.state.set(_PLANNER_ERROR, str(exc))
        context.state.set(_PLAN, plan)
        context.state.set(_INDEX, 0)
        context.state.set(_STATUS, "subtask_pending")

    def _bridge_bare_tool_json(self, context: HookContext, status: str) -> None:
        """Accept one bare OpenAI-style tool JSON only during a forced subtask."""

        if status != "awaiting_tool":
            return
        parsed = context.state.get("stage.parsed_output")
        if not isinstance(parsed, ParsedOutput) or parsed.kind.value != "invalid":
            return
        raw_output = context.state.get("stage.parser_input")
        if not isinstance(raw_output, str):
            return
        tool_call = _parse_bare_tool_call(raw_output)
        if tool_call is not None:
            context.state.set("stage.parsed_output", ParsedOutput.for_tool_call(tool_call))

    def _reset_actor_context(self, context: HookContext, status: str) -> None:
        if status in {"subtask_pending", "awaiting_tool"}:
            plan = context.state.get(_PLAN)
            index = context.state.get(_INDEX)
            subtask = _current_subtask(plan, index)
            question = context.state.get("core.question")
            prompt = self._render_subtask_input(question, subtask, index, plan)
            context.state.set("stage.model_input", prompt)
            context.state.set(_STATUS, "awaiting_tool")
            return
        if status in {"synthesis_pending", "awaiting_final"}:
            question = context.state.get("core.question")
            evidence = context.state.get(_EVIDENCE)
            context.state.set(
                "stage.model_input",
                self._render_synthesis_input(question, evidence),
            )
            context.state.set(_STATUS, "awaiting_final")

    def _normalize_subtask_call(self, context: HookContext, status: str) -> None:
        if status != "awaiting_tool":
            return
        plan = context.state.get(_PLAN)
        index = context.state.get(_INDEX)
        subtask = _current_subtask(plan, index)
        context.state.set(
            "stage.tool_call",
            ToolCall(name="search", arguments={"query": subtask["query"], "topk": self._topk}),
        )

    def _advance_after_tool(self, context: HookContext, status: str) -> None:
        if status != "awaiting_tool":
            return
        tool_result = context.state.get("stage.tool_result")
        content = getattr(tool_result, "content", None)
        if not isinstance(content, str):
            raise TypeError("stage.tool_result must expose string content")
        plan = context.state.get(_PLAN)
        index = context.state.get(_INDEX)
        subtask = _current_subtask(plan, index)
        evidence = context.state.get(_EVIDENCE)
        if not isinstance(evidence, list):
            raise TypeError("controller evidence must be a list")
        context.state.set(
            _EVIDENCE,
            [*evidence, {"task": subtask["task"], "query": subtask["query"], "result": content}],
        )
        next_index = index + 1
        context.state.set(_INDEX, next_index)
        subtasks = plan.get("subtasks") if isinstance(plan, dict) else None
        if isinstance(subtasks, list) and next_index < len(subtasks):
            context.state.set(_STATUS, "subtask_pending")
        else:
            context.state.set(_STATUS, "synthesis_pending")

    def _render_subtask_input(
        self,
        question: object,
        subtask: dict[str, str],
        index: int,
        plan: object,
    ) -> ModelInput:
        total = len(plan.get("subtasks", [])) if isinstance(plan, dict) else 0
        user_content = (
            f"Original question: {question}\n\n"
            f"Subtask {index + 1}/{total}: {subtask['task']}\n"
            f"Required search query: {subtask['query']}\n"
            f"Required topk: {self._topk}"
        )
        return ModelInput.from_messages(
            [
                ChatMessage(role="system", content=self._subtask_system_prompt),
                ChatMessage(role="user", content=user_content),
            ]
        )

    def _render_synthesis_input(self, question: object, evidence: object) -> ModelInput:
        if not isinstance(evidence, list):
            raise TypeError("controller evidence must be a list")
        rendered: list[str] = []
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                continue
            result = str(item.get("result", ""))[: self._max_evidence_chars]
            rendered.append(
                f"Evidence {index} for task {item.get('task', '')}:\n{result}"
            )
        return ModelInput.from_messages(
            [
                ChatMessage(role="system", content=self._synthesis_system_prompt),
                ChatMessage(
                    role="user",
                    content=f"Original question: {question}\n\n" + "\n\n".join(rendered),
                ),
            ]
        )


def build(config: dict[str, Any], context: Any) -> DecomposedContextControllerHook:
    """Build a controller from manifest configuration and UTF-8 prompt files."""

    allowed = {
        "planner_prompt_file",
        "subtask_system_prompt_file",
        "synthesis_system_prompt_file",
        "max_subtasks",
        "topk",
        "max_evidence_chars",
    }
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"controller has unsupported config keys: {sorted(unknown)}")
    return DecomposedContextControllerHook(
        planner_prompt=_load_template(context, config.get("planner_prompt_file")),
        subtask_system_prompt=_load_template(context, config.get("subtask_system_prompt_file")),
        synthesis_system_prompt=_load_template(context, config.get("synthesis_system_prompt_file")),
        max_subtasks=_positive_int(config.get("max_subtasks", 2), "max_subtasks"),
        topk=_positive_int(config.get("topk", 5), "topk"),
        max_evidence_chars=_positive_int(
            config.get("max_evidence_chars", 4000), "max_evidence_chars"
        ),
    )


def _load_template(context: Any, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("controller prompt file must be a non-empty string")
    root = getattr(context, "plugins_root", None)
    if not isinstance(root, Path):
        raise TypeError("controller requires PluginContext.plugins_root")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("controller prompt file must stay inside plugins root") from exc
    return path.read_text(encoding="utf-8")


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _parse_plan(raw_output: str, max_subtasks: int) -> dict[str, list[dict[str, str]]]:
    start = raw_output.find("{")
    if start < 0:
        raise ValueError("planner output must contain a JSON object")
    payload, _ = json.JSONDecoder().raw_decode(raw_output[start:])
    if not isinstance(payload, dict) or not isinstance(payload.get("subtasks"), list):
        raise ValueError("planner output must contain a subtasks list")
    subtasks: list[dict[str, str]] = []
    for item in payload["subtasks"][:max_subtasks]:
        if not isinstance(item, dict):
            continue
        task = item.get("task")
        query = item.get("query")
        if isinstance(task, str) and task.strip() and isinstance(query, str) and query.strip():
            subtasks.append({"task": task.strip(), "query": query.strip()})
    if not subtasks:
        raise ValueError("planner output contains no valid subtasks")
    return {"subtasks": subtasks}


def _current_subtask(plan: object, index: object) -> dict[str, str]:
    if not isinstance(plan, dict) or not isinstance(index, int):
        raise TypeError("controller plan state has invalid shape")
    subtasks = plan.get("subtasks")
    if not isinstance(subtasks, list) or not 0 <= index < len(subtasks):
        raise IndexError("controller subtask index is out of range")
    subtask = subtasks[index]
    if not isinstance(subtask, dict):
        raise TypeError("controller subtask must be an object")
    task = subtask.get("task")
    query = subtask.get("query")
    if not isinstance(task, str) or not isinstance(query, str):
        raise TypeError("controller subtask has invalid fields")
    return {"task": task, "query": query}


def _parse_bare_tool_call(raw_output: str) -> ToolCall | None:
    """Recognize a single bare ``{"name": ..., "arguments": ...}`` object."""

    try:
        payload = json.loads(raw_output.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    arguments = payload.get("arguments")
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return None
    return ToolCall(name=name, arguments=arguments)
