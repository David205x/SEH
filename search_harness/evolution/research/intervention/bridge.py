"""Ephemeral Hook bridge between a forked Student and one Intervention Worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    FinalDecision,
    FinalDecisionAction,
    HookContext,
    HookPhase,
    ModelInput,
    ParsedOutput,
    ParsedOutputKind,
    ToolCall,
    ToolResult,
)

from .types import InterventionAction, ReconstructedPrefix
from .worker import InterventionWorker


_STAGE_KEYS = {
    HookPhase.POST_PROMPT: ("model_input",),
    HookPhase.POST_MODEL: ("raw_model_output",),
    HookPhase.POST_PARSE: ("parser_input", "parsed_output"),
    HookPhase.PRE_TOOL: ("tool_call",),
    HookPhase.POST_TOOL: ("tool_call", "tool_result"),
    HookPhase.PRE_FINAL: ("final_decision",),
    HookPhase.ON_ERROR: ("error",),
}


@dataclass
class InterventionContext:
    """Branch-local context edits shared by the prefix and live Hook bridge."""

    prefix: ReconstructedPrefix
    model_input: ModelInput = field(init=False)
    changes: list[dict[str, Any]] = field(default_factory=list)
    _pending_messages: list[ChatMessage] = field(default_factory=list)
    _persistent_messages: list[ChatMessage] = field(default_factory=list)
    _pending_model_input_rewrite: InterventionAction | None = None

    def __post_init__(self) -> None:
        self.model_input = self.prefix.model_input

    def apply_initial(self, action: InterventionAction) -> None:
        """Apply the Worker action selected at the retained source boundary."""

        before = self.model_input.to_dict()
        if action.kind == "append_context_message":
            message = _message_from_action(action)
            self.model_input = ModelInput(messages=(*self.model_input.messages, message))
        elif action.kind == "replace_model_input":
            self.model_input = _rewrite_model_input(self.model_input, action)
        elif action.kind == "replace_stage_value":
            self._apply_initial_stage(action)
        elif action.kind != "continue_without_change":
            raise ValueError(f"unsupported Intervention action: {action.kind}")
        self.changes.append(
            {
                "scope": "source_boundary",
                "phase": self.prefix.selector.phase,
                "action": action.to_dict(),
                "model_input_before": before,
                "model_input_after": self.model_input.to_dict(),
            }
        )

    def prepare_model_input(self, context: HookContext) -> None:
        """Apply queued and branch-persistent messages at ``post_prompt``."""

        current = context.state.get("stage.model_input")
        if not isinstance(current, ModelInput):
            raise TypeError("stage.model_input must be ModelInput")
        if self._pending_model_input_rewrite is not None:
            current = _rewrite_model_input(
                current,
                self._pending_model_input_rewrite,
            )
            self._pending_model_input_rewrite = None
        additions = [*self._persistent_messages, *self._pending_messages]
        self._pending_messages.clear()
        if additions:
            current = ModelInput(messages=(*current.messages, *additions))
        context.state.set("stage.model_input", current)

    def apply_live(self, context: HookContext, action: InterventionAction) -> None:
        """Apply one Worker action to an active branch Hook transaction."""

        if action.kind == "continue_without_change":
            return
        if action.kind == "append_context_message":
            message = _message_from_action(action)
            persistence = action.payload.get("persistence")
            if context.phase == HookPhase.POST_PROMPT:
                current = context.state.get("stage.model_input")
                if not isinstance(current, ModelInput):
                    raise TypeError("stage.model_input must be ModelInput")
                context.state.set(
                    "stage.model_input",
                    ModelInput(messages=(*current.messages, message)),
                )
                if persistence == "branch":
                    self._persistent_messages.append(message)
            elif persistence == "branch":
                self._persistent_messages.append(message)
            else:
                self._pending_messages.append(message)
            return
        if action.kind == "replace_model_input":
            if context.phase == HookPhase.POST_PROMPT:
                current = context.state.get("stage.model_input")
                if not isinstance(current, ModelInput):
                    raise TypeError("stage.model_input must be ModelInput")
                context.state.set(
                    "stage.model_input",
                    _rewrite_model_input(current, action),
                )
            else:
                self._pending_model_input_rewrite = action
            return
        if action.kind == "replace_stage_value":
            key = str(action.payload.get("key", "")).removeprefix("stage.")
            state_key = f"stage.{key}"
            current = context.state.get(state_key)
            replacement = _restore_stage_value(current, action.payload.get("value"))
            context.state.set(state_key, replacement)
            return
        raise ValueError(f"unsupported Intervention action: {action.kind}")

    def _apply_initial_stage(self, action: InterventionAction) -> None:
        key = str(action.payload.get("key", "")).removeprefix("stage.")
        value = action.payload.get("value")
        current = self.prefix.stage_values.get(key)
        if current is None:
            raise KeyError(
                f"source boundary has no active stage value: stage.{key}"
            )
        replacement = _restore_stage_value(current, value)
        if key == "model_input":
            self.model_input = replacement
        elif key == "raw_model_output":
            self.model_input = _replace_last_role(
                self.model_input, "assistant", str(replacement)
            )
        elif key == "tool_result":
            if not isinstance(replacement, ToolResult):
                raise TypeError("restored tool_result has invalid type")
            self.model_input = _replace_last_role(
                self.model_input, "user", replacement.content
            )
        elif key == "final_decision":
            if (
                isinstance(replacement, FinalDecision)
                and replacement.action is FinalDecisionAction.DEFER
            ):
                self.model_input = ModelInput(
                    messages=(
                        *self.model_input.messages,
                        ChatMessage(role="user", content=replacement.feedback or ""),
                    )
                )


class InterventionHookBridge(BaseHook):
    """Pause selected lifecycle phases and delegate one action to the Worker."""

    def __init__(
        self,
        *,
        worker: InterventionWorker,
        intervention_context: InterventionContext,
        hook_guidance: dict[str, str],
        activation_budgets: dict[str, int] | None = None,
        initial_activation_counts: dict[str, int] | None = None,
    ) -> None:
        self._worker = worker
        self._intervention_context = intervention_context
        self._guidance = dict(hook_guidance)
        self._activation_budgets = (
            dict(activation_budgets)
            if activation_budgets is not None
            else {phase: 1 for phase in self._guidance}
        )
        self._activation_counts = {
            phase: 0 for phase in self._guidance
        }
        self._activation_counts.update(initial_activation_counts or {})
        if set(self._activation_budgets) != set(self._guidance):
            raise ValueError(
                "Intervention activation budgets must match guidance phases"
            )
        if set(self._activation_counts) != set(self._guidance):
            raise ValueError(
                "Intervention activation counts must match guidance phases"
            )
        if any(value < 1 for value in self._activation_budgets.values()):
            raise ValueError(
                "Intervention activation budgets must be positive"
            )
        if any(
            count < 0 or count > self._activation_budgets[phase]
            for phase, count in self._activation_counts.items()
        ):
            raise ValueError("invalid initial Intervention activation count")
        writable = {
            f"stage.{key}"
            for phase in self._guidance
            for key in _STAGE_KEYS.get(phase, ())
        }
        writable.add("stage.model_input")
        phases = frozenset({*self._guidance, HookPhase.POST_PROMPT})
        super().__init__(
            hook_id="intervention_worker_bridge",
            phases=phases,
            writable_stage_keys=frozenset(writable),
        )

    def handle(self, context: HookContext) -> None:
        if context.phase == HookPhase.POST_PROMPT:
            self._intervention_context.prepare_model_input(context)
        guidance = self._guidance.get(context.phase)
        if guidance is None:
            return
        activation_count = self._activation_counts[context.phase]
        activation_budget = self._activation_budgets[context.phase]
        if activation_count >= activation_budget:
            return
        phase_activation = activation_count + 1
        self._activation_counts[context.phase] = phase_activation
        snapshot = self._snapshot(context)
        action = self._worker.activate(
            phase=context.phase,
            guidance=guidance,
            snapshot=snapshot,
            phase_activation=phase_activation,
            max_activations=activation_budget,
        )
        self._intervention_context.apply_live(context, action)
        self._intervention_context.changes.append(
            {
                "scope": "branch",
                "phase": context.phase,
                "step": snapshot["current_step"],
                "phase_activation": phase_activation,
                "max_activations": activation_budget,
                "action": action.to_dict(),
            }
        )

    @property
    def activation_counts(self) -> dict[str, int]:
        """Return phase-local activation counts for trial auditing."""

        return dict(self._activation_counts)

    def _snapshot(self, context: HookContext) -> dict[str, Any]:
        stage = {}
        for key in _STAGE_KEYS.get(context.phase, ()):
            value = context.state.get(f"stage.{key}", None)
            if value is not None:
                stage[key] = _jsonable(value)
        core = context.state.get("core")
        return {
            "source": {
                "selector": {
                    "rollout_file": str(self._intervention_context.prefix.selector.rollout_file),
                    "example_id": self._intervention_context.prefix.selector.example_id,
                    "replicate_id": self._intervention_context.prefix.selector.replicate_id,
                    "step": self._intervention_context.prefix.selector.step,
                    "phase": self._intervention_context.prefix.selector.phase,
                },
                "model_input": self._intervention_context.prefix.model_input.to_dict(),
                "retained_trace": list(self._intervention_context.prefix.retained_trace),
            },
            "current_phase": context.phase,
            "current_step": core.get("step") if isinstance(core, dict) else None,
            "current_core": core,
            "current_trajectory": [
                event.to_dict() for event in context.trajectory
            ],
            "active_stage": stage,
            "prior_intervention_changes": list(self._intervention_context.changes),
        }


def initial_worker_snapshot(prefix: ReconstructedPrefix) -> dict[str, Any]:
    """Return the source-boundary context used for the Worker's first activation."""

    return {
        "source": {
            "selector": {
                "rollout_file": str(prefix.selector.rollout_file),
                "example_id": prefix.selector.example_id,
                "replicate_id": prefix.selector.replicate_id,
                "step": prefix.selector.step,
                "phase": prefix.selector.phase,
            },
            "model_input": prefix.model_input.to_dict(),
            "retained_trace": list(prefix.retained_trace),
        },
        "current_phase": prefix.selector.phase,
        "current_step": prefix.selector.step,
        "current_core": _boundary_core_snapshot(prefix),
        "current_trace": list(prefix.retained_trace),
        "active_stage": {
            key: _jsonable(value) for key, value in prefix.stage_values.items()
        },
        "prior_intervention_changes": [],
    }


def _boundary_core_snapshot(prefix: ReconstructedPrefix) -> dict[str, Any]:
    """Project core state without exposing events after the selected boundary."""

    source_state = prefix.source_run.get("state")
    source_state = source_state if isinstance(source_state, dict) else {}
    return {
        "question": (
            prefix.example.get("question")
            or prefix.source_run.get("question")
        ),
        "max_steps": source_state.get("max_steps"),
        "step": prefix.selector.step,
        "status": "running",
        "final_answer": None,
        "error": None,
    }


def _message_from_action(action: InterventionAction) -> ChatMessage:
    return ChatMessage(
        role=str(action.payload.get("role", "")),
        content=str(action.payload.get("content", "")),
    )


def _model_input(value: Any) -> ModelInput:
    if not isinstance(value, list) or not value:
        raise TypeError("model input messages must be a non-empty list")
    messages = []
    for message in value:
        if not isinstance(message, dict):
            raise TypeError("model input message must be an object")
        messages.append(
            ChatMessage(
                role=str(message.get("role", "")),
                content=str(message.get("content", "")),
            )
        )
    return ModelInput.from_messages(messages)


def _rewrite_model_input(
    model_input: ModelInput,
    action: InterventionAction,
) -> ModelInput:
    system_instruction = str(action.payload.get("system_instruction", "")).strip()
    if not system_instruction:
        raise ValueError("replace_model_input requires a system instruction")
    messages = list(model_input.messages)
    replacement = ChatMessage(role="system", content=system_instruction)
    for index, message in enumerate(messages):
        if message.role == "system":
            messages[index] = replacement
            break
    else:
        messages.insert(0, replacement)
    user_instruction = str(action.payload.get("user_instruction", "")).strip()
    if user_instruction:
        messages.append(ChatMessage(role="user", content=user_instruction))
    return ModelInput.from_messages(messages)


def _restore_stage_value(current: Any, value: Any) -> Any:
    if isinstance(current, ModelInput):
        messages = value.get("messages") if isinstance(value, dict) else value
        return _model_input(messages)
    if isinstance(current, ToolCall):
        if not isinstance(value, dict) or not isinstance(value.get("arguments", {}), dict):
            raise TypeError("tool_call replacement must be an object")
        return ToolCall(name=str(value.get("name", "")), arguments=value.get("arguments", {}))
    if isinstance(current, ToolResult):
        if not isinstance(value, dict) or not isinstance(value.get("metadata", {}), dict):
            raise TypeError("tool_result replacement must be an object")
        return ToolResult(
            name=str(value.get("name", "")),
            content=str(value.get("content", "")),
            metadata=value.get("metadata", {}),
        )
    if isinstance(current, ParsedOutput):
        if not isinstance(value, dict):
            raise TypeError("parsed_output replacement must be an object")
        kind = ParsedOutputKind(str(value.get("kind")))
        thinking = value.get("inband_thinking")
        if kind is ParsedOutputKind.TOOL_CALL:
            tool = _restore_stage_value(ToolCall("placeholder"), value.get("tool_call"))
            return ParsedOutput.for_tool_call(tool, thinking)
        if kind is ParsedOutputKind.FINAL_ANSWER:
            return ParsedOutput.for_final_answer(str(value.get("final_answer", "")), thinking)
        return ParsedOutput.invalid(str(value.get("error") or "invalid output"), thinking)
    if isinstance(current, FinalDecision):
        if not isinstance(value, dict):
            raise TypeError("final_decision replacement must be an object")
        action = FinalDecisionAction(str(value.get("action")))
        if action is FinalDecisionAction.DEFER:
            return FinalDecision.defer(str(value.get("feedback", "")))
        return FinalDecision.accept(str(value.get("answer", current.answer or "")))
    if isinstance(current, str):
        if not isinstance(value, str):
            raise TypeError("string stage replacement must be a string")
        return value
    if not isinstance(value, type(current)):
        raise TypeError(
            f"stage replacement must remain {type(current).__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def _replace_last_role(model_input: ModelInput, role: str, content: str) -> ModelInput:
    messages = list(model_input.messages)
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == role:
            messages[index] = ChatMessage(role=role, content=content)
            return ModelInput.from_messages(messages)
    raise ValueError(f"prefix has no {role} message to replace")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
