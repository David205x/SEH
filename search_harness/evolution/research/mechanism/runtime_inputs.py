"""Mechanism Distiller 可选择的受控 Runtime Input Topics。"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from typing import Literal, get_args


RuntimeInputId = Literal[
    "task",
    "conversation",
    "tool",
    "model_io",
    "parsed_output",
    "final_decision",
    "trajectory",
    "persistent_state",
]
RUNTIME_INPUT_IDS = tuple(get_args(RuntimeInputId))


@dataclass(frozen=True)
class RuntimeInputTopic:
    """一个由 Packet Builder 展开为完整 API 文档的运行时能力主题。"""

    topic_id: RuntimeInputId
    description: str
    symbols: tuple[str, ...]
    preferred_usage: tuple[str, ...]
    avoid: tuple[str, ...]
    lifecycle_notes: tuple[str, ...] = ()


_TOPICS: dict[str, RuntimeInputTopic] = {
    "task": RuntimeInputTopic(
        topic_id="task",
        description="Original task text and stable rollout limits managed by the Agent Loop.",
        symbols=("core.question", "core.max_steps", "core.step"),
        preferred_usage=(
            "Read the original task from core.question.",
            "Use core.step and core.max_steps only for explicit bounded control rules.",
        ),
        avoid=("Do not reconstruct the original task from conversation messages.",),
    ),
    "conversation": RuntimeInputTopic(
        topic_id="conversation",
        description="Student-visible follow-up messages retained for later Model Inputs.",
        symbols=("core.conversation_messages", "ChatMessage", "ModelInput"),
        preferred_usage=(
            "Use core.conversation_messages when the mechanism explicitly needs Student-visible message history.",
        ),
        avoid=(
            "Do not infer semantic Tool Call/Result history from message roles; use the tool topic instead.",
        ),
        lifecycle_notes=(
            "Tool results may be represented as user-role follow-up messages by the Agent Loop.",
        ),
    ),
    "tool": RuntimeInputTopic(
        topic_id="tool",
        description="Current phase-local and previously completed Tool Call/Result values.",
        symbols=(
            "ToolCall",
            "ToolResult",
            "stage.tool_call",
            "stage.tool_result",
            "core.tool_interactions",
        ),
        preferred_usage=(
            "Use stage.tool_call at PRE_TOOL or POST_TOOL for the current call.",
            "Use stage.tool_result at POST_TOOL for the current result.",
            "Use core.tool_interactions for ordered completed Tool Call/Result history.",
        ),
        avoid=(
            "Do not identify Tool Results by conversation message role.",
            "Do not use open TrajectoryEvent payloads when core.tool_interactions is sufficient.",
        ),
        lifecycle_notes=(
            "At POST_TOOL, core.tool_interactions excludes the current stage.tool_call/stage.tool_result pair.",
            "At PRE_FINAL, core.tool_interactions contains all Tool interactions committed before the Hook invocation.",
        ),
    ),
    "model_io": RuntimeInputTopic(
        topic_id="model_io",
        description="Current phase-local and serialized prior model inputs and outputs.",
        symbols=(
            "ChatMessage",
            "ModelInput",
            "ModelInput.from_messages",
            "stage.model_input",
            "stage.raw_model_output",
            "core.model_inputs",
            "core.model_outputs",
        ),
        preferred_usage=(
            "Use stage.model_input at POST_PROMPT for the imminent generation.",
            "Use stage.raw_model_output at POST_MODEL for the current raw output.",
        ),
        avoid=("Do not write serialized core.model_inputs or core.model_outputs.",),
    ),
    "parsed_output": RuntimeInputTopic(
        topic_id="parsed_output",
        description="Parser input and the current or prior structured ParsedOutput values.",
        symbols=(
            "ParsedOutput",
            "ParsedOutputKind",
            "stage.parser_input",
            "stage.parsed_output",
            "core.parsed_outputs",
        ),
        preferred_usage=(
            "Use stage.parsed_output at POST_PARSE for the current parsed branch.",
        ),
        avoid=("Replacing stage.parser_input does not re-run parsing.",),
    ),
    "final_decision": RuntimeInputTopic(
        topic_id="final_decision",
        description="The PRE_FINAL candidate answer and the Hook-controlled accept/defer decision.",
        symbols=(
            "FinalDecision",
            "FinalDecisionAction",
            "FinalDecision.accept",
            "FinalDecision.defer",
            "stage.final_decision",
        ),
        preferred_usage=(
            "Read stage.final_decision at PRE_FINAL and replace it with FinalDecision.defer or FinalDecision.accept.",
        ),
        avoid=(
            "Do not access stage.final_decision outside PRE_FINAL.",
            "Do not change a decision back to accept after another Hook deferred it in the same phase.",
        ),
    ),
    "trajectory": RuntimeInputTopic(
        topic_id="trajectory",
        description="Read-only ordered events emitted before the current Hook invocation.",
        symbols=("HookContext.trajectory", "TrajectoryEvent"),
        preferred_usage=("Use trajectory for observability and event-order requirements.",),
        avoid=(
            "Do not assume undocumented keys in open event payloads.",
            "Prefer structured core or stage state for mechanism decisions.",
        ),
    ),
    "persistent_state": RuntimeInputTopic(
        topic_id="persistent_state",
        description="Declared rollout-local extension/shared state owned by Hooks.",
        symbols=("StateRef", "HookStateView.get", "HookStateView.set"),
        preferred_usage=(
            "Declare every writable persistent key with StateRef and explicit writers.",
            "Use extension.<hook_id>.* for state owned by one Hook.",
        ),
        avoid=(
            "Do not mutate values returned by HookStateView.get in place.",
            "Do not use core.hook_state instead of declared state keys.",
        ),
    ),
}


def get_runtime_input_topic(topic_id: str) -> RuntimeInputTopic:
    """按受控 ID 返回一个 Runtime Input Topic。"""

    normalized = topic_id.strip().casefold()
    try:
        return _TOPICS[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown Runtime Input Topic: {topic_id}") from exc


def list_runtime_input_topics() -> tuple[RuntimeInputTopic, ...]:
    """返回稳定顺序的全部 Runtime Input Topics。"""

    return tuple(_TOPICS[topic_id] for topic_id in RUNTIME_INPUT_IDS)


def suggest_runtime_input_topics(query: str) -> list[str]:
    """按 ID 与说明返回少量相近 Topic，用于 API 查询纠错。"""

    normalized = query.strip().casefold()
    direct = [
        topic.topic_id
        for topic in list_runtime_input_topics()
        if normalized and (
            normalized in topic.topic_id
            or normalized in topic.description.casefold()
            or any(normalized in item.casefold() for item in topic.preferred_usage)
        )
    ]
    if direct:
        return direct[:4]
    return get_close_matches(normalized, list(RUNTIME_INPUT_IDS), n=4, cutoff=0.35)


REFERENCE_MODEL_GATED_FINAL_HOOK = '''\
"""Reference only: one-shot model-gated PRE_FINAL deferral."""
from __future__ import annotations
import json
from typing import Any
from search_harness.framework import BaseHook, ChatMessage, FinalDecision, HookContext, HookModelRequest, HookPhase, ModelInput, StateRef

_DEFERRED = StateRef(key="extension.reference_final_gate.deferred", owner="reference_final_gate", value_type=bool, writers=frozenset({"reference_final_gate"}), default=False)
_SYSTEM = 'Decide whether another Agent step is required. Use only the supplied task, completed tool interactions, and proposed answer. Return exactly {"should_defer": true_or_false}.'
_FEEDBACK = "Gather the missing evidence with the available tools before answering."

class ReferenceFinalGateHook(BaseHook):
    """Demonstrate runtime inputs, one Hook-model call, fallback, and state transition."""
    def __init__(self) -> None:
        super().__init__(hook_id="reference_final_gate", phases=frozenset({HookPhase.PRE_FINAL}), state_refs=(_DEFERRED,), writable_stage_keys=frozenset({"stage.final_decision"}), model_profiles=frozenset({"student"}), max_model_calls_per_invocation=1)

    def handle(self, context: HookContext) -> None:
        self._handle_pre_final(context)

    def _handle_pre_final(self, context: HookContext) -> None:
        if context.state.get(_DEFERRED.key, False):
            return
        question = context.state.get("core.question")
        interactions = context.state.get("core.tool_interactions")
        decision = context.state.get("stage.final_decision")
        if not isinstance(question, str) or not isinstance(interactions, list) or not isinstance(decision, FinalDecision) or not isinstance(decision.answer, str):
            return
        payload = {"question": question, "completed_tool_interactions": interactions, "proposed_answer": decision.answer}
        response = context.call_model(HookModelRequest(profile="student", purpose="reference_final_gate", model_input=ModelInput.from_messages([ChatMessage(role="system", content=_SYSTEM), ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False))])))
        try:
            judgment = response.json_object()
        except ValueError:
            return
        if judgment.get("should_defer") is not True:
            return
        context.state.set("stage.final_decision", FinalDecision.defer(_FEEDBACK))
        context.state.set(_DEFERRED.key, True)

def build(config: dict[str, Any], context: Any) -> ReferenceFinalGateHook:
    if config:
        raise ValueError("reference_final_gate does not accept configuration")
    return ReferenceFinalGateHook()
'''
