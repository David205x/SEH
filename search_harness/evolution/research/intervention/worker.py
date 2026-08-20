"""Teacher-model Worker that chooses one terminal action per Hook activation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Annotated, Any

from search_harness.framework import (
    ToolCall,
    ToolExecutor,
    ToolResult,
)
from search_harness.framework.tools import (
    CallableTool,
    ToolArg,
    ToolSet,
    tool,
)
from search_harness.integrations.openai_compatible import (
    NativeToolCall,
    OpenAICompatibleConfig,
    OpenAICompatibleSyncClient,
    OpenAICompatibleToolSession,
    PendingNativeToolCall,
)

from .types import InterventionAction


_TRIAL_STATE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_MAX_TRIAL_STATE_KEYS = 16
_MAX_TRIAL_STATE_CHARACTERS = 4096


class InterventionWorker:
    """Persist teacher context across Hook activations in one Student branch."""

    def __init__(
        self,
        *,
        config: OpenAICompatibleConfig,
        intent: str,
        hook_guidance: dict[str, str],
        max_steps_per_activation: int = 8,
        system_prompt_template: str | None = None,
        client: OpenAICompatibleSyncClient | None = None,
        activation_tool_set_factory: (
            Callable[[object], ToolSet] | None
        ) = None,
        extended_tools: bool = False,
    ) -> None:
        if not intent.strip():
            raise ValueError("intervention intent must not be empty")
        if not hook_guidance:
            raise ValueError("intervention hook_guidance must not be empty")
        if max_steps_per_activation < 1:
            raise ValueError("Worker max_steps_per_activation must be positive")
        self.intent = intent.strip()
        self.hook_guidance = dict(hook_guidance)
        self.max_steps_per_activation = max_steps_per_activation
        self.trace: list[dict[str, Any]] = []
        self._activation_count = 0
        self._trial_state: dict[str, Any] = {}
        self._extended_tools = extended_tools
        self._system_prompt = _render_system_prompt(
            template=system_prompt_template,
        )
        self._activation_tool_set_factory = activation_tool_set_factory
        self._session = OpenAICompatibleToolSession(
            config=config,
            client=client,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": (
                        "Intervention intent:\n"
                        f"{self.intent}\n\n"
                        "Configured Hook guidance:\n"
                        f"{json.dumps(self.hook_guidance, ensure_ascii=False, indent=2)}"
                    ),
                },
            ],
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
        activation = _ActivationState(snapshot, self._trial_state)
        tool_set = (
            self._activation_tool_set_factory(activation)
            if self._activation_tool_set_factory is not None
            else _ActivationTools(
                activation,
                extended_tools=self._extended_tools,
            ).tool_set
        )
        if not isinstance(tool_set, ToolSet):
            raise TypeError("activation tool-set factory must return ToolSet")
        runtime = ToolExecutor(tool_set.tools)
        step = snapshot.get("current_step")
        active_observation = _active_observation(
            snapshot,
            trial_state=self._trial_state if self._extended_tools else None,
        )
        self._session.append_user_message(
            (
                f"Hook activation {self._activation_count}: phase={phase}, "
                f"student_step={step}, phase_activation="
                f"{phase_activation}/{max_activations}.\n"
                "Read-only active observation:\n"
                f"{json.dumps(active_observation, ensure_ascii=False)}\n"
                f"Phase guidance: {guidance}\n"
                "Act only on the current phase guidance. Treat guidance for other "
                "phases as context for continuity, not authorization to act early.\n"
                "The API tool list contains the exact tools available for this "
                "activation.\n"
                "Treat the active observation as authoritative lifecycle state. "
                "Do not try to rediscover an active stage value in the editable "
                "Student message blocks. Evaluate any semantic condition from the "
                "candidate and inspected Student-visible evidence; the runtime has "
                "not decided that semantic condition for you.\n"
                "Inspect the bound Student context as needed, then call exactly one "
                "terminal action tool. The terminal tool ends this Hook activation."
                " Every assistant response may contain exactly one native tool "
                "call in total. Never batch or parallelize inspection, state, and "
                "terminal calls. If state and a terminal action are both required, "
                "call update_trial_state alone, wait for its Tool Result, and call "
                "the terminal action in a later response."
            )
        )
        self.trace.append(
            {
                "event_type": "worker_activation",
                "activation": self._activation_count,
                "phase": phase,
                "student_step": step,
                "phase_activation": phase_activation,
                "max_activations": max_activations,
                "guidance": guidance,
                "trial_state_before": dict(self._trial_state),
            }
        )

        for worker_step in range(1, self.max_steps_per_activation + 1):
            turn = self._session.complete(tools=tool_set.tools)
            raw_output = _assistant_content(turn.assistant_message)
            metadata = {
                "usage": dict(turn.usage),
                "tool_calls": [
                    {
                        "name": call.name,
                        "call_id": call.call_id,
                        "arguments": (
                            call.arguments
                            if call.parse_error is None
                            else call.arguments_text
                        ),
                    }
                    for call in turn.tool_calls
                ],
            }
            for key in ("reasoning_content", "reasoning", "thinking"):
                value = turn.assistant_message.get(key)
                if isinstance(value, str) and value:
                    metadata[key] = value
            self.trace.append(
                {
                    "event_type": "worker_model_output",
                    "activation": self._activation_count,
                    "worker_step": worker_step,
                    "model_input": {
                        "messages": turn.request_messages,
                        "tools": [
                            {
                                "name": definition.name,
                                "description": definition.description,
                                "parameters": definition.to_json_schema(),
                            }
                            for definition in tool_set.definitions
                        ],
                    },
                    "raw_output": raw_output,
                    "metadata": metadata,
                }
            )
            if not turn.tool_calls:
                self._session.append_user_message(
                    "No native tool call was returned. Call exactly one tool from "
                    "the current API tool list."
                )
                continue

            self._session.commit_assistant(turn)
            if len(turn.tool_calls) != 1:
                content = (
                    "Call exactly one tool per response during an Intervention Hook "
                    "activation. Retry with one tool call."
                )
                for call in turn.tool_calls:
                    self._record_tool_result(
                        call=call,
                        content=content,
                        metadata={"error_type": "multiple_tool_calls"},
                        worker_step=worker_step,
                    )
                continue

            call = turn.tool_calls[0]
            if call.parse_error is not None:
                self._record_tool_result(
                    call=call,
                    content=call.parse_error,
                    metadata={"error_type": "invalid_json"},
                    worker_step=worker_step,
                )
                continue
            if call.name not in {tool.name for tool in tool_set.tools}:
                content = (
                    f"Unknown tool '{call.name}'. Use one of: "
                    f"{sorted(tool.name for tool in tool_set.tools)}"
                )
                self._record_tool_result(
                    call=call,
                    content=content,
                    metadata={"error_type": "unknown_tool"},
                    worker_step=worker_step,
                )
                continue

            result = runtime.execute(
                ToolCall(name=call.name, arguments=call.arguments)
            )
            self._record_tool_result(
                call=call,
                content=result.content,
                metadata=dict(result.metadata),
                worker_step=worker_step,
                result=result,
            )
            if activation.action is not None:
                self.trace.append(
                    {
                        "event_type": "worker_action",
                        "activation": self._activation_count,
                        "action": activation.action.to_dict(),
                        "trial_state_after": dict(self._trial_state),
                    }
                )
                return activation.action

        raise RuntimeError(
            f"Intervention Worker did not choose an action within "
            f"{self.max_steps_per_activation} steps"
        )

    def _record_tool_result(
        self,
        *,
        call: PendingNativeToolCall,
        content: str,
        metadata: dict[str, Any],
        worker_step: int,
        result: ToolResult | None = None,
    ) -> None:
        self._session.append_tool_result(
            call=call,
            content=content,
            metadata=metadata,
        )
        tool_result = result or ToolResult(
            name=call.name,
            content=content,
            metadata=metadata,
        )
        self.trace.append(
            {
                "event_type": "worker_tool_result",
                "activation": self._activation_count,
                "worker_step": worker_step,
                "tool_call": {
                    "name": call.name,
                    "arguments": (
                        call.arguments
                        if call.parse_error is None
                        else {"raw_arguments": call.arguments_text}
                    ),
                    "call_id": call.call_id,
                },
                "tool_result": tool_result.to_dict(),
            }
        )

    @property
    def transcript(self) -> list[dict[str, Any]]:
        """Return the complete native Worker transcript."""

        return self._session.transcript

    @property
    def tool_calls(self) -> tuple[NativeToolCall, ...]:
        """Return auditable native tool calls from all activations."""

        return self._session.tool_calls

    @property
    def usage(self) -> dict[str, Any]:
        """Return aggregate Teacher usage for this Worker session."""

        return self._session.usage

    @property
    def trial_state(self) -> dict[str, Any]:
        """Return the explicit branch-local state retained across activations."""

        return dict(self._trial_state)

    def close(self) -> None:
        """Close transport resources owned by this Worker."""

        self._session.close()


class _ActivationState:
    def __init__(
        self,
        snapshot: dict[str, Any],
        trial_state: dict[str, Any] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.trial_state = trial_state if trial_state is not None else {}
        self.action: InterventionAction | None = None

    def finish(self, action: InterventionAction) -> ToolResult:
        if self.action is not None:
            raise RuntimeError("Hook activation already has a terminal action")
        self.action = action
        return ToolResult(
            name=action.kind,
            content=f"ACTION_ACCEPTED: {action.kind}",
            metadata={"terminal": True, "action": action.to_dict()},
        )


class _ActivationTools:
    def __init__(
        self,
        activation: _ActivationState,
        *,
        extended_tools: bool = False,
    ) -> None:
        self._activation = activation
        tools = [
            CallableTool.from_callable(self.inspect_editable_context),
            CallableTool.from_callable(self.inspect_context_block),
        ]
        if extended_tools:
            tools.append(CallableTool.from_callable(self.update_trial_state))
            if _editable_stage_target(activation.snapshot) is not None:
                tools.extend(
                    [
                        CallableTool.from_callable(self.inspect_active_stage),
                        CallableTool.from_callable(self.apply_active_stage_patch),
                    ]
                )
        if _context_patch_is_available(activation.snapshot):
            tools.append(CallableTool.from_callable(self.apply_context_patch))
        if _stage_is_active(activation.snapshot, "final_decision"):
            tools.extend(
                [
                    CallableTool.from_callable(self.defer_final_answer),
                    CallableTool.from_callable(self.accept_final_answer),
                ]
            )
        tools.append(CallableTool.from_callable(self.continue_without_change))
        self.tool_set = ToolSet(tools)

    @tool(name="update_trial_state")
    def update_trial_state(
        self,
        values: Annotated[
            dict[str, object],
            ToolArg(
                "Branch-local JSON values to create or replace. State is visible "
                "at later Hook activations in this Trial only."
            ),
        ],
    ) -> ToolResult:
        """Update bounded Trial state without ending the current activation."""

        error = _trial_state_update_error(
            current=self._activation.trial_state,
            values=values,
        )
        if error is not None:
            return ToolResult(
                name="update_trial_state",
                content=f"TOOL_INPUT_ERROR: {error}",
                metadata={"error": error},
            )
        self._activation.trial_state.update(values)
        return ToolResult(
            name="update_trial_state",
            content=(
                "TRIAL_STATE_UPDATED: "
                + ", ".join(sorted(values))
            ),
            metadata={"updated_keys": sorted(values)},
        )

    @tool(name="inspect_active_stage")
    def inspect_active_stage(self) -> ToolResult:
        """Read the current phase's editable semantic stage projection."""

        target = _editable_stage_target(self._activation.snapshot)
        if target is None:
            return ToolResult(
                name="inspect_active_stage",
                content="TOOL_INPUT_ERROR: no editable stage target is active",
                metadata={"error": "no editable stage target is active"},
            )
        key, projection = target
        return ToolResult(
            name="inspect_active_stage",
            content=(
                f"Editable stage: stage.{key}\n"
                + json.dumps(projection, ensure_ascii=False)
            ),
        )

    @tool(name="apply_active_stage_patch")
    def apply_active_stage_patch(
        self,
        patch: Annotated[
            dict[str, object],
            ToolArg(
                "Semantic patch for the active stage. post_model: {content}; "
                "post_parse: {kind, tool_call|final_answer|error}; pre_tool: "
                "{name?, arguments?}; post_tool: {content}. Program metadata "
                "is preserved."
            ),
        ],
        reason: Annotated[
            str,
            ToolArg("Why this stage transformation tests the hypothesis."),
        ] = "",
    ) -> ToolResult:
        """Patch one active semantic stage value and finish the activation."""

        replacement, error = _active_stage_replacement(
            snapshot=self._activation.snapshot,
            patch=patch,
        )
        if error is not None or replacement is None:
            message = error or "active stage patch could not be constructed"
            return ToolResult(
                name="apply_active_stage_patch",
                content=f"TOOL_INPUT_ERROR: {message}",
                metadata={"error": message},
            )
        key, value = replacement
        return self._activation.finish(
            InterventionAction(
                kind="replace_stage_value",
                payload={"key": key, "value": value},
                reason=reason.strip(),
            )
        )

    @tool(name="inspect_editable_context")
    def inspect_editable_context(self) -> ToolResult:
        """List editable Student context blocks as a compact ordered table."""

        value = self._activation.snapshot.get("editable_context")
        blocks = value if isinstance(value, list) else []
        lines = [
            f"Editable Student context: {len(blocks)} blocks",
            "| id | kind | role | chars | preview |",
            "|---:|---|---|---:|---|",
        ]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            lines.append(
                "| {block_id} | {kind} | {role} | {characters} | "
                "{summary} |".format(
                    block_id=block.get("block_id", "unavailable"),
                    kind=_table_cell(block.get("kind")),
                    role=_table_cell(block.get("role")),
                    characters=block.get("characters", "unavailable"),
                    summary=_table_cell(block.get("summary")),
                )
            )
        return ToolResult(
            name="inspect_editable_context",
            content="\n".join(lines),
        )

    @tool(name="inspect_context_block")
    def inspect_context_block(
        self,
        block_id: Annotated[
            int,
            ToolArg(
                "Numeric block ID from inspect_editable_context.",
                minimum=1,
            ),
        ],
    ) -> ToolResult:
        """Read one exact Student-visible block without JSON string escaping."""

        blocks = self._activation.snapshot.get("_editable_context_blocks")
        if not isinstance(blocks, list):
            blocks = []
        block = next(
            (
                item
                for item in blocks
                if isinstance(item, dict) and item.get("block_id") == block_id
            ),
            None,
        )
        if block is None:
            return ToolResult(
                name="inspect_context_block",
                content=(
                    "TOOL_INPUT_ERROR\n"
                    "code: unknown_block_id\n"
                    f"block_id: {block_id}"
                ),
                metadata={
                    "error": f"unknown block_id {block_id}",
                    "error_type": "input_validation",
                },
            )
        content = block.get("content")
        exact = content if isinstance(content, str) else str(content or "")
        return ToolResult(
            name="inspect_context_block",
            content=(
                f"Block {block_id} | kind={block.get('kind', 'unavailable')} | "
                f"role={block.get('role', 'unavailable')} | "
                f"characters={len(exact)}\n"
                "--- BEGIN EXACT CONTENT ---\n"
                f"{exact}\n"
                "--- END EXACT CONTENT ---"
            ),
        )

    @tool(name="apply_context_patch")
    def apply_context_patch(
        self,
        operations: Annotated[
            list[dict[str, object]],
            ToolArg(
                "Ordered atomic patch operations. Replace: {operation:'replace', "
                "block_id:<int>, content:<string>}. Delete: {operation:'delete', "
                "block_id:<int>}. Insert: {operation:'insert', anchor_block_id:<int>, "
                "position:'before'|'after', role:'system'|'user'|'assistant'|'tool', "
                "content:<string>}. IDs come from inspect_editable_context."
            ),
        ],
        reason: Annotated[
            str,
            ToolArg("Why this context transformation tests the hypothesis."),
        ] = "",
    ) -> ToolResult:
        """Atomically insert, replace or delete context blocks and finish."""

        error = _context_patch_error(
            operations=operations,
            snapshot=self._activation.snapshot,
        )
        if error is not None:
            return ToolResult(
                name="apply_context_patch",
                content=f"TOOL_INPUT_ERROR: {error}",
                metadata={"error": error},
            )
        return self._activation.finish(
            InterventionAction(
                kind="apply_context_patch",
                payload={"operations": operations},
                reason=reason.strip(),
            )
        )

    @tool(name="defer_final_answer")
    def defer_final_answer(
        self,
        feedback: Annotated[
            str,
            ToolArg("Instruction shown to the Student before another generation."),
        ],
        reason: Annotated[str, ToolArg("Why this stage replacement is useful.")] = "",
    ) -> ToolResult:
        """Reject the current final candidate and request another Student generation."""

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
        answer: Annotated[str, ToolArg("Final answer accepted for the Student branch.")],
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
        """Leave Student context unchanged and end the current Hook activation."""

        return self._activation.finish(
            InterventionAction(kind="continue_without_change", reason=reason)
        )


def _render_system_prompt(
    *,
    template: str | None = None,
) -> str:
    tool_section = (
        "The API request supplies the exact tools available for each Hook "
        "activation. Use only that current native tool list."
    )
    if template is not None:
        if "{{tools}}" not in template:
            raise ValueError(
                "Intervention Worker system prompt template lacks {{tools}}"
            )
        return template.replace("{{tools}}", tool_section)
    return (
        "You are an Intervention Worker supervising one forked Student trajectory. "
        "You may inspect all bound trace evidence and modify only through the supplied "
        "tools. Every assistant response may contain exactly one native tool call. "
        "Never batch or parallelize tool calls. At each Hook activation, inspect what "
        "you need and call exactly one terminal action tool. A terminal action "
        "immediately returns control to the "
        "Student. Never use a golden "
        "answer or invent evidence. Tool-phase recommendations are advisory; any active "
        "stage may be replaced when the experiment intent requires it.\n\n"
        f"{tool_section}\n\n"
        "Use provider-native structured tool calling for every action."
    )


def _assistant_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _table_cell(value: object) -> str:
    return str(value if value is not None else "unavailable").replace(
        "|", "\\|"
    ).replace("\n", " ")


def _active_observation(
    snapshot: dict[str, Any],
    *,
    trial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project only phase-local state needed to interpret the current activation."""

    active_stage = snapshot.get("active_stage")
    active_stage = active_stage if isinstance(active_stage, dict) else {}
    projected_stage = {
        key: (
            value
            if key == "final_decision"
            else {"active": True}
        )
        for key, value in active_stage.items()
    }
    prior_changes = snapshot.get("prior_intervention_changes")
    prior_changes = prior_changes if isinstance(prior_changes, list) else []
    observation = {
        "phase": snapshot.get("current_phase"),
        "student_step": snapshot.get("current_step"),
        "active_stage": projected_stage,
        "lifecycle_facts": {
            "active_stage_keys": list(active_stage),
            "prior_intervention_count": len(prior_changes),
        },
    }
    if trial_state is not None:
        observation["trial_state"] = dict(trial_state)
    return observation


def _editable_stage_target(
    snapshot: dict[str, Any],
) -> tuple[str, Any] | None:
    """Return the one semantic stage surface editable at the current phase."""

    # A retained prefix reconstructs Student-visible context, not the suspended
    # parser/tool transaction that originally produced every stage value.  A
    # source post_tool value can still be represented faithfully in the
    # continuation context; raw output, parsed output, and a pending Tool Call
    # require a live branch Hook transaction instead.
    if snapshot.get("source_boundary") and snapshot.get("current_phase") in {
        "post_model",
        "post_parse",
        "pre_tool",
    }:
        return None

    phase_targets = {
        "post_model": "raw_model_output",
        "post_parse": "parsed_output",
        "pre_tool": "tool_call",
        "post_tool": "tool_result",
    }
    key = phase_targets.get(str(snapshot.get("current_phase")))
    active_stage = snapshot.get("active_stage")
    if key is None or not isinstance(active_stage, dict) or key not in active_stage:
        return None
    value = active_stage[key]
    if key == "raw_model_output":
        return key, {"content": value}
    if not isinstance(value, dict):
        return None
    if key == "tool_result":
        return key, {
            "name": value.get("name"),
            "content": value.get("content"),
        }
    if key == "parsed_output":
        return key, {
            name: value.get(name)
            for name in ("kind", "tool_call", "final_answer", "error")
            if value.get(name) is not None
        }
    return key, {
        "name": value.get("name"),
        "arguments": value.get("arguments"),
    }


def _active_stage_replacement(
    *,
    snapshot: dict[str, Any],
    patch: dict[str, object],
) -> tuple[tuple[str, Any] | None, str | None]:
    target = _editable_stage_target(snapshot)
    if target is None:
        return None, "no editable stage target is active"
    if not patch:
        return None, "patch must contain at least one field"
    key, projection = target
    if key == "raw_model_output":
        if set(patch) != {"content"} or not isinstance(patch.get("content"), str):
            return None, "post_model patch requires only string content"
        return (key, patch["content"]), None
    if key == "tool_result":
        if set(patch) != {"content"} or not isinstance(patch.get("content"), str):
            return None, "post_tool patch requires only string content"
        active = snapshot["active_stage"][key]
        value = dict(active)
        value["content"] = patch["content"]
        return (key, value), None
    if key == "tool_call":
        if not set(patch) <= {"name", "arguments"}:
            return None, "pre_tool patch supports only name and arguments"
        value = dict(projection)
        value.update(patch)
        if not isinstance(value.get("name"), str) or not value["name"].strip():
            return None, "tool_call patch requires a non-empty name"
        if not isinstance(value.get("arguments"), dict):
            return None, "tool_call patch arguments must be an object"
        return (key, value), None

    if not set(patch) <= {"kind", "tool_call", "final_answer", "error"}:
        return None, "post_parse patch contains unsupported fields"
    kind = patch.get("kind", projection.get("kind"))
    active = snapshot["active_stage"][key]
    value: dict[str, Any] = {"kind": kind}
    if isinstance(active, dict) and active.get("inband_thinking") is not None:
        value["inband_thinking"] = active["inband_thinking"]
    if kind == "tool_call":
        tool_call = patch.get("tool_call", projection.get("tool_call"))
        if (
            not isinstance(tool_call, dict)
            or not isinstance(tool_call.get("name"), str)
            or not isinstance(tool_call.get("arguments", {}), dict)
        ):
            return None, "tool_call parsed output requires name and object arguments"
        value["tool_call"] = tool_call
    elif kind == "final_answer":
        answer = patch.get("final_answer", projection.get("final_answer"))
        if not isinstance(answer, str):
            return None, "final_answer parsed output requires string final_answer"
        value["final_answer"] = answer
    elif kind == "invalid":
        error = patch.get("error", projection.get("error"))
        if not isinstance(error, str) or not error.strip():
            return None, "invalid parsed output requires non-empty error"
        value["error"] = error
    else:
        return None, "post_parse kind must be tool_call, final_answer, or invalid"
    return (key, value), None


def _trial_state_update_error(
    *,
    current: dict[str, Any],
    values: dict[str, object],
) -> str | None:
    if not values:
        return "values must contain at least one state entry"
    invalid_keys = [key for key in values if _TRIAL_STATE_KEY.fullmatch(key) is None]
    if invalid_keys:
        return f"invalid state key: {invalid_keys[0]}"
    candidate = {**current, **values}
    if len(candidate) > _MAX_TRIAL_STATE_KEYS:
        return f"Trial state may contain at most {_MAX_TRIAL_STATE_KEYS} keys"
    try:
        encoded = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        return f"Trial state values must be JSON-compatible: {exc}"
    if len(encoded) > _MAX_TRIAL_STATE_CHARACTERS:
        return (
            "Trial state exceeds "
            f"{_MAX_TRIAL_STATE_CHARACTERS} serialized characters"
        )
    return None


def _stage_is_active(snapshot: dict[str, Any], key: str) -> bool:
    active_stage = snapshot.get("active_stage")
    return isinstance(active_stage, dict) and key in active_stage


def _context_patch_is_available(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("source_boundary")) or snapshot.get("current_phase") in {
        "post_prompt",
        "post_tool",
    }


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


def _context_patch_error(
    *,
    operations: list[dict[str, object]],
    snapshot: dict[str, Any],
) -> str | None:
    if not operations:
        return "operations must contain at least one patch operation"
    if len(operations) > 8:
        return "operations must contain at most 8 patch operations"
    blocks = snapshot.get("_editable_context_blocks")
    valid_ids = {
        item.get("block_id")
        for item in blocks if isinstance(item, dict)
    } if isinstance(blocks, list) else set()
    touched: set[int] = set()
    for index, operation in enumerate(operations, start=1):
        if not isinstance(operation, dict):
            return f"operation {index} must be an object"
        kind = operation.get("operation")
        if kind not in {"insert", "replace", "delete"}:
            return f"operation {index} has unsupported operation type"
        id_key = "anchor_block_id" if kind == "insert" else "block_id"
        block_id = operation.get(id_key)
        if not isinstance(block_id, int) or isinstance(block_id, bool):
            return f"operation {index} requires integer {id_key}"
        if block_id not in valid_ids:
            return f"operation {index} references unknown block ID {block_id}"
        if kind != "insert":
            if block_id in touched:
                return f"block ID {block_id} is modified more than once"
            touched.add(block_id)
        if kind == "delete":
            if set(operation) != {"operation", "block_id"}:
                return f"delete operation {index} contains unsupported fields"
            continue
        content = operation.get("content")
        if not isinstance(content, str) or not content.strip():
            return f"operation {index} requires non-empty content"
        if kind == "replace":
            if set(operation) != {"operation", "block_id", "content"}:
                return f"replace operation {index} contains unsupported fields"
            continue
        if operation.get("position") not in {"before", "after"}:
            return f"insert operation {index} requires position before or after"
        if operation.get("role") not in {"system", "user", "assistant", "tool"}:
            return f"insert operation {index} has unsupported role"
        if set(operation) != {
            "operation", "anchor_block_id", "position", "role", "content"
        }:
            return f"insert operation {index} contains unsupported fields"
    if len(touched) == len(valid_ids) and all(
        operation.get("operation") == "delete" for operation in operations
    ):
        return "patch must leave at least one context block"
    return None
