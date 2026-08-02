"""Shared data structures for the core agent loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .model import ChatMessage, ModelInput
from ..tools import ToolCall, ToolInteraction, ToolResult
from ..trajectory import TrajectoryEvent


TraceEvent = TrajectoryEvent


class ParsedOutputKind(str, Enum):
    """Branches available to the core loop after parsing model output."""

    TOOL_CALL = "tool_call"
    FINAL_ANSWER = "final_answer"
    INVALID = "invalid"


class RunStatus(str, Enum):
    """Terminal and non-terminal run states used for trace and evaluation."""

    RUNNING = "running"
    COMPLETED = "completed"
    INVALID_OUTPUT = "invalid_output"
    MAX_STEPS_REACHED = "max_steps_reached"
    TOOL_ERROR = "tool_error"


class FinalDecisionAction(str, Enum):
    """The core-controlled outcome of a parsed final answer."""

    ACCEPT = "accept"
    DEFER = "defer"


@dataclass(frozen=True)
class HookModelRequest:
    """One bounded model generation requested by a hook invocation."""

    profile: str
    purpose: str
    model_input: ModelInput

    def __post_init__(self) -> None:
        profile = self.profile.strip().casefold()
        purpose = self.purpose.strip()
        if not profile:
            raise ValueError("hook model profile must not be empty")
        if not purpose:
            raise ValueError("hook model purpose must not be empty")
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "purpose", purpose)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "purpose": self.purpose,
            "model_input": self.model_input.to_dict(),
        }


@dataclass(frozen=True)
class HookModelResponse:
    """Text and provider metadata returned to one model-driven hook."""

    raw_output: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_output", str(self.raw_output))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def json_object(self) -> dict[str, Any]:
        """Parse a JSON object response with a precise hook-facing error."""

        try:
            value = json.loads(self.raw_output.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"hook model output is not valid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("hook model JSON output must be an object")
        return value

    def to_dict(self) -> dict[str, Any]:
        return {"raw_output": self.raw_output, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class ParsedOutput:
    """Parser result consumed by the loop."""

    kind: ParsedOutputKind
    tool_call: ToolCall | None = None
    final_answer: str | None = None
    inband_thinking: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.kind is ParsedOutputKind.TOOL_CALL and self.tool_call is None:
            raise ValueError("tool_call output requires a ToolCall")
        if self.kind is ParsedOutputKind.FINAL_ANSWER and self.final_answer is None:
            raise ValueError("final_answer output requires an answer")
        if self.kind is ParsedOutputKind.INVALID and not self.error:
            raise ValueError("invalid output requires an error message")

    @classmethod
    def for_tool_call(
        cls,
        tool_call: ToolCall,
        inband_thinking: str | None = None,
    ) -> "ParsedOutput":
        return cls(
            kind=ParsedOutputKind.TOOL_CALL,
            tool_call=tool_call,
            inband_thinking=inband_thinking,
        )

    @classmethod
    def for_final_answer(
        cls,
        answer: str,
        inband_thinking: str | None = None,
    ) -> "ParsedOutput":
        return cls(
            kind=ParsedOutputKind.FINAL_ANSWER,
            final_answer=answer,
            inband_thinking=inband_thinking,
        )

    @classmethod
    def invalid(
        cls,
        error: str,
        inband_thinking: str | None = None,
    ) -> "ParsedOutput":
        return cls(
            kind=ParsedOutputKind.INVALID,
            error=error,
            inband_thinking=inband_thinking,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.tool_call is not None:
            payload["tool_call"] = self.tool_call.to_dict()
        if self.final_answer is not None:
            payload["final_answer"] = self.final_answer
        if self.inband_thinking is not None:
            payload["inband_thinking"] = self.inband_thinking
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class FinalDecision:
    """A Hook-controlled decision to accept or defer one final answer."""

    action: FinalDecisionAction
    answer: str | None = None
    feedback: str | None = None

    def __post_init__(self) -> None:
        if self.action is FinalDecisionAction.ACCEPT:
            if not isinstance(self.answer, str):
                raise ValueError("accepted final decision requires an answer")
            if self.feedback is not None:
                raise ValueError("accepted final decision cannot contain feedback")
            return
        if self.action is FinalDecisionAction.DEFER:
            if not isinstance(self.feedback, str) or not self.feedback.strip():
                raise ValueError("deferred final decision requires feedback")
            if self.answer is not None:
                raise ValueError("deferred final decision cannot contain an answer")
            object.__setattr__(self, "feedback", self.feedback.strip())
            return
        raise ValueError(f"unsupported final decision action: {self.action}")

    @classmethod
    def accept(cls, answer: str) -> "FinalDecision":
        """Accept the candidate answer, optionally after Hook rewriting."""

        return cls(action=FinalDecisionAction.ACCEPT, answer=str(answer))

    @classmethod
    def defer(cls, feedback: str) -> "FinalDecision":
        """Defer completion and provide the Student's next-turn feedback."""

        return cls(action=FinalDecisionAction.DEFER, feedback=feedback)

    def to_dict(self) -> dict[str, str]:
        payload = {"action": self.action.value}
        if self.answer is not None:
            payload["answer"] = self.answer
        if self.feedback is not None:
            payload["feedback"] = self.feedback
        return payload


@dataclass
class AgentState:
    """Mutable state for one agent rollout."""

    question: str
    max_steps: int
    step: int = 0
    status: RunStatus = RunStatus.RUNNING
    final_answer: str | None = None
    error: str | None = None
    model_inputs: list[ModelInput] = field(default_factory=list)
    model_outputs: list[str] = field(default_factory=list)
    parsed_outputs: list[ParsedOutput] = field(default_factory=list)
    tool_interactions: list[ToolInteraction] = field(default_factory=list)
    conversation_messages: list[ChatMessage] = field(default_factory=list)
    hook_state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")

    def append_model_input(self, model_input: ModelInput) -> None:
        self.model_inputs.append(model_input)

    def append_model_output(self, output: str) -> None:
        self.model_outputs.append(output)

    def append_parsed_output(self, parsed_output: ParsedOutput) -> None:
        self.parsed_outputs.append(parsed_output)

    def append_tool_interaction(
        self,
        tool_call: ToolCall,
        tool_result: ToolResult,
    ) -> None:
        self.tool_interactions.append(
            ToolInteraction(tool_call=tool_call, tool_result=tool_result)
        )

    def append_conversation_message(self, message: ChatMessage) -> None:
        """Append one assistant or feedback message used by later prompts."""

        if message.role not in {"assistant", "user", "tool"}:
            raise ValueError("conversation history only accepts follow-up messages")
        self.conversation_messages.append(message)

    def finish_completed(self, answer: str) -> None:
        self.status = RunStatus.COMPLETED
        self.final_answer = answer
        self.error = None

    def finish_error(self, status: RunStatus, error: str) -> None:
        if status in {RunStatus.RUNNING, RunStatus.COMPLETED}:
            raise ValueError("finish_error requires an error status")
        self.status = status
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "max_steps": self.max_steps,
            "step": self.step,
            "status": self.status.value,
            "final_answer": self.final_answer,
            "error": self.error,
            "model_inputs": [item.to_dict() for item in self.model_inputs],
            "model_outputs": list(self.model_outputs),
            "parsed_outputs": [item.to_dict() for item in self.parsed_outputs],
            "tool_interactions": [
                interaction.to_dict() for interaction in self.tool_interactions
            ],
            "conversation_messages": [
                message.to_dict() for message in self.conversation_messages
            ],
            "hook_state": dict(self.hook_state),
        }


@dataclass(frozen=True)
class RunResult:
    """Agent Run 完成后返回的结果与 Trajectory 引用。"""

    state: AgentState
    trace: tuple[TraceEvent, ...]

    @property
    def question(self) -> str:
        return self.state.question

    @property
    def answer(self) -> str | None:
        return self.state.final_answer

    @property
    def status(self) -> RunStatus:
        return self.state.status

    @property
    def error(self) -> str | None:
        return self.state.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "status": self.status.value,
            "error": self.error,
            "state": self.state.to_dict(),
            "trace": [event.to_dict() for event in self.trace],
        }


AgentRun = RunResult
