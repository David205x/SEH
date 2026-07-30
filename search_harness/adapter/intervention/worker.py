"""Teacher-model Worker that chooses one terminal action per Hook activation."""

from __future__ import annotations

import json
from typing import Annotated, Any

from search_harness.core import (
    ChatMessage,
    ModelClient,
    ModelInput,
    ModelResponseMetadataProvider,
    ParsedOutputKind,
    TaggedOutputParser,
    ToolResult,
    ToolRuntime,
)
from search_harness.framework.prompting.renderers import render_tagged_tool_section
from search_harness.framework.tooling import (
    CallableTool,
    ToolArg,
    ToolDefinition,
    ToolSet,
    tool,
)

from .types import InterventionAction


class InterventionWorker:
    """Persist teacher context across Hook activations in one Actor branch."""

    def __init__(
        self,
        *,
        model: ModelClient,
        intent: str,
        hook_guidance: dict[str, str],
        max_steps_per_activation: int = 8,
        system_prompt_template: str | None = None,
    ) -> None:
        if not intent.strip():
            raise ValueError("intervention intent must not be empty")
        if not hook_guidance:
            raise ValueError("intervention hook_guidance must not be empty")
        if max_steps_per_activation < 1:
            raise ValueError("Worker max_steps_per_activation must be positive")
        self.model = model
        self.intent = intent.strip()
        self.hook_guidance = dict(hook_guidance)
        self.max_steps_per_activation = max_steps_per_activation
        self.trace: list[dict[str, Any]] = []
        self._history: list[ChatMessage] = []
        self._parser = TaggedOutputParser()
        self._activation_count = 0
        self._system_prompt = _render_system_prompt(
            template=system_prompt_template,
        )
        self._history.append(
            ChatMessage(
                role="user",
                content=(
                    "Intervention intent:\n"
                    f"{self.intent}\n\n"
                    "Configured Hook guidance:\n"
                    f"{json.dumps(self.hook_guidance, ensure_ascii=False, indent=2)}"
                ),
            )
        )

    def activate(
        self,
        *,
        phase: str,
        guidance: str,
        snapshot: dict[str, Any],
        phase_activation: int = 1,
        max_activations: int = 1,
    ) -> InterventionAction:
        """Run the Worker until one action tool terminates this Hook activation."""

        if phase_activation < 1 or max_activations < phase_activation:
            raise ValueError("invalid phase activation budget")
        self._activation_count += 1
        activation = _ActivationState(snapshot)
        tool_set = _ActivationTools(activation).tool_set
        runtime = ToolRuntime(tool_set.tools)
        step = snapshot.get("current_step")
        tool_section = render_tagged_tool_section(tool_set.definitions)
        self._history.append(
            ChatMessage(
                role="user",
                content=(
                    f"Hook activation {self._activation_count}: phase={phase}, "
                    f"actor_step={step}, phase_activation="
                    f"{phase_activation}/{max_activations}.\n"
                    f"Phase guidance: {guidance}\n"
                    "Available tools for this activation:\n"
                    f"{tool_section}\n"
                    "Inspect the bound Actor context as needed, then call exactly one "
                    "terminal action tool. The terminal tool ends this Hook activation."
                ),
            )
        )
        self.trace.append(
            {
                "event_type": "worker_activation",
                "activation": self._activation_count,
                "phase": phase,
                "actor_step": step,
                "phase_activation": phase_activation,
                "max_activations": max_activations,
                "guidance": guidance,
            }
        )

        for worker_step in range(1, self.max_steps_per_activation + 1):
            model_input = self._model_input()
            raw_output = self.model.generate(model_input)
            metadata = _model_metadata(self.model)
            self.trace.append(
                {
                    "event_type": "worker_model_output",
                    "activation": self._activation_count,
                    "worker_step": worker_step,
                    "model_input": model_input.to_dict(),
                    "raw_output": raw_output,
                    "metadata": metadata,
                }
            )
            parsed = self._parser.parse(raw_output)
            self._history.append(ChatMessage(role="assistant", content=raw_output))

            if parsed.kind is ParsedOutputKind.TOOL_CALL:
                if parsed.tool_call is None:
                    raise RuntimeError("Worker parsed tool call is missing")
                result = runtime.call_one(parsed.tool_call)
                self._history.append(ChatMessage(role="user", content=result.content))
                self.trace.append(
                    {
                        "event_type": "worker_tool_result",
                        "activation": self._activation_count,
                        "worker_step": worker_step,
                        "tool_call": parsed.tool_call.to_dict(),
                        "tool_result": result.to_dict(),
                    }
                )
                if activation.action is not None:
                    self.trace.append(
                        {
                            "event_type": "worker_action",
                            "activation": self._activation_count,
                            "action": activation.action.to_dict(),
                        }
                    )
                    return activation.action
                continue

            if parsed.kind is ParsedOutputKind.FINAL_ANSWER:
                feedback = (
                    "A Hook activation cannot finish with final_answer. Call one terminal "
                    "action tool: append_context_message, replace_model_input, "
                    "defer_final_answer, accept_final_answer, or "
                    "continue_without_change."
                )
            else:
                feedback = (
                    f"Worker output could not be parsed: {parsed.error}. Return one "
                    "complete tool_call block."
                )
            self._history.append(ChatMessage(role="user", content=feedback))

        raise RuntimeError(
            f"Intervention Worker did not choose an action within "
            f"{self.max_steps_per_activation} steps"
        )

    def _model_input(self) -> ModelInput:
        return ModelInput.from_messages(
            [ChatMessage(role="system", content=self._system_prompt), *self._history]
        )


class _ActivationState:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.action: InterventionAction | None = None

    def finish(self, action: InterventionAction) -> ToolResult:
        if self.action is not None:
            raise RuntimeError("Hook activation already has a terminal action")
        self.action = action
        return ToolResult(
            name=action.kind,
            content=f"ACTION_ACCEPTED: {json.dumps(action.to_dict(), ensure_ascii=False)}",
            metadata={"terminal": True, "action": action.to_dict()},
        )


class _ActivationTools:
    def __init__(self, activation: _ActivationState) -> None:
        self._activation = activation
        tools = [
            CallableTool.from_callable(self.inspect_actor_context),
            CallableTool.from_callable(self.append_context_message),
            CallableTool.from_callable(self.replace_model_input),
        ]
        if _stage_is_active(activation.snapshot, "final_decision"):
            tools.extend(
                [
                    CallableTool.from_callable(self.defer_final_answer),
                    CallableTool.from_callable(self.accept_final_answer),
                ]
            )
        tools.append(CallableTool.from_callable(self.continue_without_change))
        self.tool_set = ToolSet(tools)

    @tool(name="inspect_actor_context")
    def inspect_actor_context(self) -> ToolResult:
        """Read the complete source prefix, current Actor state, trace and stage values."""

        return ToolResult(
            name="inspect_actor_context",
            content=json.dumps(self._activation.snapshot, ensure_ascii=False),
        )

    @tool(name="append_context_message")
    def append_context_message(
        self,
        role: Annotated[
            str,
            ToolArg(
                "Role of the message added to Actor model input.",
                choices=("system", "user", "assistant", "tool"),
            ),
        ],
        content: Annotated[str, ToolArg("Complete message content to add.")],
        persistence: Annotated[
            str,
            ToolArg(
                "Apply once to the next generation or to every remaining generation.",
                choices=("next_generation", "branch"),
            ),
        ] = "next_generation",
    ) -> ToolResult:
        """Add a message to Actor context and end the current Hook activation."""

        return self._activation.finish(
            InterventionAction(
                kind="append_context_message",
                payload={
                    "role": role,
                    "content": content,
                    "persistence": persistence,
                },
            )
        )

    @tool(name="replace_model_input")
    def replace_model_input(
        self,
        system_instruction: Annotated[
            str,
            ToolArg(
                "Complete replacement system instruction. Existing non-system "
                "messages and tool evidence are preserved automatically."
            ),
        ],
        user_instruction: Annotated[
            str,
            ToolArg(
                "Optional user-role instruction appended after the preserved history."
            ),
        ] = "",
    ) -> ToolResult:
        """Rewrite Actor instructions without serializing its complete message list."""

        if not system_instruction.strip():
            return ToolResult(
                name="replace_model_input",
                content="TOOL_INPUT_ERROR: system_instruction must not be empty",
                metadata={"error": "system_instruction must not be empty"},
            )
        return self._activation.finish(
            InterventionAction(
                kind="replace_model_input",
                payload={
                    "system_instruction": system_instruction.strip(),
                    "user_instruction": user_instruction.strip(),
                },
            )
        )

    @tool(name="defer_final_answer")
    def defer_final_answer(
        self,
        feedback: Annotated[
            str,
            ToolArg("Instruction shown to the Actor before another generation."),
        ],
        reason: Annotated[str, ToolArg("Why this stage replacement is useful.")] = "",
    ) -> ToolResult:
        """Reject the current final candidate and request another Actor generation."""

        value = {"action": "defer", "feedback": feedback.strip()}
        validation_error = _stage_replacement_error(
            snapshot=self._activation.snapshot,
            key="final_decision",
            value=value,
        )
        if validation_error is not None:
            return ToolResult(
                name="defer_final_answer",
                content=f"TOOL_INPUT_ERROR: {validation_error}",
                metadata={"error": validation_error},
            )
        return self._activation.finish(
            InterventionAction(
                kind="replace_stage_value",
                payload={"key": "final_decision", "value": value},
                reason=reason,
            )
        )

    @tool(name="accept_final_answer")
    def accept_final_answer(
        self,
        answer: Annotated[str, ToolArg("Final answer accepted for the Actor branch.")],
        reason: Annotated[str, ToolArg("Why this answer can be accepted.")] = "",
    ) -> ToolResult:
        """Accept an explicit final answer at an active pre-final Hook."""

        value = {"action": "accept", "answer": answer.strip()}
        validation_error = _stage_replacement_error(
            snapshot=self._activation.snapshot, key="final_decision", value=value
        )
        if validation_error is not None:
            return ToolResult(
                name="accept_final_answer",
                content=f"TOOL_INPUT_ERROR: {validation_error}",
                metadata={"error": validation_error},
            )
        return self._activation.finish(
            InterventionAction(
                kind="replace_stage_value",
                payload={"key": "final_decision", "value": value},
                reason=reason,
            )
        )

    @tool(name="continue_without_change")
    def continue_without_change(
        self,
        reason: Annotated[str, ToolArg("Why no intervention is needed at this Hook.")],
    ) -> ToolResult:
        """Leave Actor context unchanged and end the current Hook activation."""

        return self._activation.finish(
            InterventionAction(kind="continue_without_change", reason=reason)
        )


def _render_system_prompt(
    *,
    template: str | None = None,
) -> str:
    tool_section = (
        "The runtime lists the exact tools available for each Hook activation "
        "in the current activation message. Use only that current list."
    )
    if template is not None:
        if "{{tools}}" not in template:
            raise ValueError(
                "Intervention Worker system prompt template lacks {{tools}}"
            )
        return template.replace("{{tools}}", tool_section)
    return (
        "You are an Intervention Worker supervising one forked Actor trajectory. "
        "You may inspect all bound trace evidence and modify only through the supplied "
        "tools. At each Hook activation, inspect what you need and call exactly one "
        "terminal action tool. A terminal action immediately returns control to the "
        "Actor, so do not write anything after its tool_call block. Never use a golden "
        "answer or invent evidence. Tool-phase recommendations are advisory; any active "
        "stage may be replaced when the experiment intent requires it.\n\n"
        f"{tool_section}\n\n"
        "Write concise analysis before an action, then exactly one complete block:\n"
        '<tool_call>{"name": "<tool>", "arguments": {}}</tool_call>\n'
    )


def _stage_is_active(snapshot: dict[str, Any], key: str) -> bool:
    active_stage = snapshot.get("active_stage")
    return isinstance(active_stage, dict) and key in active_stage


def _model_metadata(model: ModelClient) -> dict[str, Any]:
    if isinstance(model, ModelResponseMetadataProvider):
        return model.get_last_generation_metadata()
    return {}


def _stage_replacement_error(
    *, snapshot: dict[str, Any], key: str, value: Any
) -> str | None:
    normalized_key = key.removeprefix("stage.")
    active_stage = snapshot.get("active_stage")
    if not isinstance(active_stage, dict) or normalized_key not in active_stage:
        return f"stage.{normalized_key} is not active at this Hook"
    current = active_stage[normalized_key]
    if isinstance(current, str):
        return None if isinstance(value, str) else "replacement must be a string"
    if not isinstance(current, dict) or not isinstance(value, dict):
        return None if isinstance(value, type(current)) else "replacement shape does not match"

    if normalized_key == "model_input":
        messages = value.get("messages")
        if not isinstance(messages, list) or not messages:
            return "model_input replacement requires a non-empty messages array"
    elif normalized_key == "tool_call":
        if not isinstance(value.get("name"), str) or not isinstance(
            value.get("arguments", {}), dict
        ):
            return "tool_call replacement requires name and object arguments"
    elif normalized_key == "tool_result":
        if not isinstance(value.get("name"), str) or not isinstance(
            value.get("content"), str
        ):
            return "tool_result replacement requires name and content"
        if not isinstance(value.get("metadata", {}), dict):
            return "tool_result metadata must be an object"
    elif normalized_key == "parsed_output":
        if value.get("kind") not in {"tool_call", "final_answer", "invalid"}:
            return "parsed_output replacement has an invalid kind"
    elif normalized_key == "final_decision":
        action = value.get("action")
        if action == "defer":
            feedback = value.get("feedback")
            if not isinstance(feedback, str) or not feedback.strip():
                return "deferred final_decision requires non-empty feedback"
        elif action == "accept":
            answer = value.get("answer")
            if not isinstance(answer, str):
                return "accepted final_decision requires an answer"
        else:
            return "final_decision action must be accept or defer"
    return None
