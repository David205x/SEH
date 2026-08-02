"""角色无关的同步 Agent Loop。"""

from __future__ import annotations

from .agent import Agent
from .model import ModelResponse

from .errors import MaxStepsReachedError, ToolRuntimeError
from ..harness.runtime import HarnessInstance
from ..harness.state import HookStateStore
from ..harness.lifecycle import HookPhase
from ..trajectory import InMemoryTrajectoryRecorder
from .types import (
    AgentState,
    ChatMessage,
    FinalDecision,
    FinalDecisionAction,
    ParsedOutput,
    ParsedOutputKind,
    RunResult,
    RunStatus,
)

class AgentLoop:
    """驱动一个已实例化 Harness 的内部控制机制。"""

    def __init__(
        self,
        *,
        agent: Agent,
        instance: HarnessInstance,
    ) -> None:
        if instance.harness is not agent.harness:
            raise ValueError("Harness Instance must belong to the Agent Harness")
        self.model = agent.model
        self.prompt_builder = agent.harness.prompt
        self.parser = agent.harness.output
        self.tool_runtime = agent.harness.tool_executor
        self.hooks = agent.harness.lifecycle
        self.instance = instance

    def run(self) -> RunResult:
        state = self.instance.state
        trajectory = self.instance.trajectory
        hook_store = self.instance.lifecycle_state

        while state.status is RunStatus.RUNNING and state.step < state.max_steps:
            state.step += 1
            self.hooks.run_phase(
                HookPhase.PRE_PROMPT,
                state=state,
                store=hook_store,
                trajectory=trajectory,
            )

            model_input = self.prompt_builder.build(state)
            model_input = self.hooks.run_phase(
                HookPhase.POST_PROMPT,
                state=state,
                store=hook_store,
                trajectory=trajectory,
                stage_values={"model_input": model_input},
            )["model_input"]
            state.append_model_input(model_input)
            trajectory.record("model_input", state.step, model_input.to_dict())

            response = self.model.generate(model_input)
            if not isinstance(response, ModelResponse):
                raise TypeError("model.generate must return ModelResponse")
            raw_output = response.raw_output
            state.append_model_output(raw_output)
            model_output_payload = {"raw_output": raw_output}
            if response.usage:
                model_output_payload["usage"] = dict(response.usage)
            if response.metadata:
                model_output_payload["metadata"] = dict(response.metadata)
            trajectory.record("model_output", state.step, model_output_payload)

            parsed_output = self._parse_output(state, trajectory, hook_store, raw_output)
            state.append_parsed_output(parsed_output)
            trajectory.record("parsed_output", state.step, parsed_output.to_dict())

            if parsed_output.kind is ParsedOutputKind.TOOL_CALL:
                self._handle_tool_call(state, trajectory, hook_store, parsed_output)
                continue

            if parsed_output.kind is ParsedOutputKind.FINAL_ANSWER:
                if self._handle_final_answer(state, trajectory, hook_store, parsed_output):
                    break
                continue

            self._handle_invalid_output(state, trajectory, hook_store, parsed_output)
            continue

        if state.status is RunStatus.RUNNING:
            self._handle_max_steps(state, trajectory, hook_store)

        return RunResult(state=state, trace=trajectory.events)

    def _parse_output(
        self,
        state: AgentState,
        trajectory: InMemoryTrajectoryRecorder,
        hook_store: HookStateStore,
        raw_output: str,
    ) -> ParsedOutput:
        hooked_output = self.hooks.run_phase(
            HookPhase.POST_MODEL,
            state=state,
            store=hook_store,
            trajectory=trajectory,
            stage_values={"raw_model_output": raw_output},
        )["raw_model_output"]
        if not isinstance(hooked_output, str):
            raise TypeError("HookPipeline.post_model must return str")

        parsed_output = self.parser.parse(hooked_output)
        parsed_output = self.hooks.run_phase(
            HookPhase.POST_PARSE,
            state=state,
            store=hook_store,
            trajectory=trajectory,
            stage_values={
                "parser_input": hooked_output,
                "parsed_output": parsed_output,
            },
        )["parsed_output"]
        if not isinstance(parsed_output, ParsedOutput):
            raise TypeError("HookPipeline.post_parse must return ParsedOutput")
        return parsed_output

    def _handle_tool_call(
        self,
        state: AgentState,
        trajectory: InMemoryTrajectoryRecorder,
        hook_store: HookStateStore,
        parsed_output: ParsedOutput,
    ) -> None:
        if parsed_output.tool_call is None:
            raise ValueError("tool_call branch requires parsed tool_call")

        tool_call = self.hooks.run_phase(
            HookPhase.PRE_TOOL,
            state=state,
            store=hook_store,
            trajectory=trajectory,
            stage_values={"tool_call": parsed_output.tool_call},
        )["tool_call"]
        trajectory.record("tool_call", state.step, tool_call.to_dict())
        try:
            tool_result = self.tool_runtime.execute(tool_call)
        except ToolRuntimeError as exc:
            state.finish_error(RunStatus.TOOL_ERROR, str(exc))
            trajectory.record("tool_error", state.step, {"error": str(exc)})
            self._run_error_hooks(state, trajectory, hook_store, exc)
            return

        tool_result = self.hooks.run_phase(
            HookPhase.POST_TOOL,
            state=state,
            store=hook_store,
            trajectory=trajectory,
            stage_values={"tool_call": tool_call, "tool_result": tool_result},
        )["tool_result"]
        state.append_tool_interaction(tool_call, tool_result)
        state.append_conversation_message(
            ChatMessage(role="assistant", content=state.model_outputs[-1])
        )
        state.append_conversation_message(
            ChatMessage(role="user", content=tool_result.content)
        )
        trajectory.record("tool_result", state.step, tool_result.to_dict())

    def _handle_final_answer(
        self,
        state: AgentState,
        trajectory: InMemoryTrajectoryRecorder,
        hook_store: HookStateStore,
        parsed_output: ParsedOutput,
    ) -> bool:
        if parsed_output.final_answer is None:
            raise ValueError("final_answer branch requires parsed answer")

        candidate = parsed_output.final_answer
        trajectory.record("final_answer_candidate", state.step, {"answer": candidate})
        decision = self.hooks.run_phase(
            HookPhase.PRE_FINAL,
            state=state,
            store=hook_store,
            trajectory=trajectory,
            stage_values={"final_decision": FinalDecision.accept(candidate)},
        )["final_decision"]
        if not isinstance(decision, FinalDecision):
            raise TypeError("HookPipeline.pre_final must return FinalDecision")
        if decision.action is FinalDecisionAction.DEFER:
            state.append_conversation_message(
                ChatMessage(role="assistant", content=state.model_outputs[-1])
            )
            state.append_conversation_message(
                ChatMessage(role="user", content=decision.feedback or "")
            )
            trajectory.record("final_deferred", state.step, decision.to_dict())
            return False

        answer = decision.answer
        if answer is None:
            raise RuntimeError("accepted final decision has no answer")
        state.finish_completed(answer)
        trajectory.record("final_answer", state.step, {"answer": answer})
        return True

    def _handle_invalid_output(
        self,
        state: AgentState,
        trajectory: InMemoryTrajectoryRecorder,
        hook_store: HookStateStore,
        parsed_output: ParsedOutput,
    ) -> None:
        error = parsed_output.error or "model output did not match expected schema"
        trajectory.record("invalid_output", state.step, {"error": error})
        feedback = (
            f"Your previous response could not be parsed: {error}. "
            "Continue by returning exactly one complete <tool_call>...</tool_call> "
            "or <final_answer>...</final_answer> block."
        )
        state.append_conversation_message(
            ChatMessage(role="assistant", content=state.model_outputs[-1])
        )
        state.append_conversation_message(ChatMessage(role="user", content=feedback))
        trajectory.record("invalid_output_feedback", state.step, {"message": feedback})

    def _handle_max_steps(
        self,
        state: AgentState,
        trajectory: InMemoryTrajectoryRecorder,
        hook_store: HookStateStore,
    ) -> None:
        error = f"agent reached max_steps={state.max_steps}"
        state.finish_error(RunStatus.MAX_STEPS_REACHED, error)
        trajectory.record("max_steps_reached", state.step, {"max_steps": state.max_steps})
        self._run_error_hooks(state, trajectory, hook_store, MaxStepsReachedError(error))

    def _run_error_hooks(
        self,
        state: AgentState,
        trajectory: InMemoryTrajectoryRecorder,
        hook_store: HookStateStore,
        error: Exception,
    ) -> None:
        self.hooks.run_phase(
            HookPhase.ON_ERROR,
            state=state,
            store=hook_store,
            trajectory=trajectory,
            stage_values={"error": error},
        )
