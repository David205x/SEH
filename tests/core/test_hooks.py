from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from unittest import TestCase

from search_harness.core import (
    AgentLoop,
    BaseHook,
    ChatMessage,
    FinalDecision,
    HookPipeline,
    HookModelRequest,
    HookModelResponse,
    HookPhase,
    ModelInput,
    StateAccessError,
    StateRef,
    TaggedOutputParser,
    ToolResult,
    ToolRuntime,
)
from search_harness.framework.tooling import CallableTool, ToolArg, ToolSet, tool
from search_harness.registry import ComponentSpec, EvolutionPolicy, PluginContext
from search_harness.registry.plugin_importer import load_factory


BASELINE_PLUGINS_ROOT = Path(__file__).parents[2] / "harness_templates" / "actor" / "baseline" / "plugins"
DELEGATION_EXPERIMENT_PLUGINS_ROOT = (
    Path(__file__).parents[2]
    / "harness_templates"
    / "experiments"
    / "delegation_question_system_append"
    / "plugins"
)
DECOMPOSED_EXPERIMENT_PLUGINS_ROOT = (
    Path(__file__).parents[2]
    / "harness_templates"
    / "experiments"
    / "decomposed_context_student"
    / "plugins"
)
CRITIC_PLUGINS_ROOT = (
    Path(__file__).parents[2] / "harness_templates" / "adapter" / "critic" / "baseline" / "plugins"
)


@dataclass
class StaticModel:
    output: str

    def generate(self, model_input: ModelInput) -> str:
        del model_input
        return self.output


@dataclass
class SequentialModel:
    outputs: list[str]

    def generate(self, model_input: ModelInput) -> str:
        del model_input
        return self.outputs.pop(0)


@dataclass
class RecordingSequentialModel:
    outputs: list[str]
    model_inputs: list[ModelInput]

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.model_inputs = []

    def generate(self, model_input: ModelInput) -> str:
        self.model_inputs.append(model_input)
        return self.outputs.pop(0)


class TestPromptBuilder:
    def build(self, state) -> ModelInput:
        return ModelInput.from_messages(
            [
                ChatMessage(role="system", content="test system"),
                ChatMessage(role="user", content=state.question),
            ]
        )


class RewriteOutputHook(BaseHook):
    def handle(self, context) -> None:
        self.seen_question = context.state.get("core.question")
        raw_output = context.state.get("stage.raw_model_output")
        context.state.set(
            "shared.format_health",
            {"rewritten": True, "source": raw_output},
        )
        context.state.set(
            "stage.raw_model_output",
            "<final_answer>rewritten answer</final_answer>",
        )


class ObserveRewriteHook(BaseHook):
    def handle(self, context) -> None:
        health = context.state.get("shared.format_health")
        rewritten = context.state.get("stage.raw_model_output")
        self.observed = (health, rewritten, context.state.get("core.model_outputs"))
        context.state.set(
            "stage.raw_model_output",
            rewritten.replace("rewritten answer", "rewritten result"),
        )


class IllegalCoreWriteHook(BaseHook):
    def handle(self, context) -> None:
        context.state.set("core.question", "modified")


class DeferFirstFinalHook(BaseHook):
    def handle(self, context) -> None:
        if context.state.get("extension.defer_first.deferred"):
            return
        context.state.set("extension.defer_first.deferred", True)
        context.state.set(
            "stage.final_decision",
            FinalDecision.defer("Continue gathering the required evidence."),
        )


class AcceptFinalHook(BaseHook):
    def handle(self, context) -> None:
        context.state.set("stage.final_decision", FinalDecision.accept("override"))


class RecordingHookModelBackend:
    def __init__(self) -> None:
        self.requests: list[HookModelRequest] = []

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(
            raw_output='{"continue_search": true}',
            metadata={"usage": {"total_tokens": 7}},
        )


class PlanningHookModelBackend:
    def __init__(self) -> None:
        self.requests: list[HookModelRequest] = []

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(
            raw_output=(
                '{"subtasks":[{"task":"find first evidence","query":"first query"},'
                '{"task":"find second evidence","query":"second query"}]}'
            ),
            metadata={"usage": {"total_tokens": 11}},
        )


class ModelDrivenDecisionHook(BaseHook):
    def handle(self, context) -> None:
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="judge_search_sufficiency",
                model_input=ModelInput.from_messages(
                    [ChatMessage(role="user", content=context.state.get("core.question"))]
                ),
            )
        )
        context.state.set(
            "extension.model_decision.continue_search",
            response.json_object()["continue_search"],
        )


class OneShotModelInputHook(BaseHook):
    def handle(self, context) -> None:
        if context.state.get("core.step") != 1:
            return
        model_input = context.state.get("stage.model_input")
        context.state.set(
            "stage.model_input",
            ModelInput.from_messages(
                [
                    *model_input.messages,
                    ChatMessage(role="user", content="ephemeral context"),
                ]
            ),
        )


class PersistToolContextHook(BaseHook):
    def handle(self, context) -> None:
        tool_result = context.state.get("stage.tool_result")
        context.state.set("shared.next_model_context", tool_result.content)


class InjectPersistedContextHook(BaseHook):
    def handle(self, context) -> None:
        note = context.state.get("shared.next_model_context")
        if not note:
            return
        model_input = context.state.get("stage.model_input")
        context.state.set(
            "stage.model_input",
            ModelInput.from_messages(
                [
                    *model_input.messages,
                    ChatMessage(role="user", content=f"persisted context: {note}"),
                ]
            ),
        )


class HookPipelineTest(TestCase):
    def test_hook_rejects_stage_write_unavailable_in_all_subscribed_phases(self) -> None:
        """验证 Hook 声明的 stage 写权限至少属于一个订阅 phase。"""

        with self.assertRaisesRegex(ValueError, "stage write access unavailable"):
            IllegalCoreWriteHook(
                hook_id="invalid_stage_writer",
                phases=frozenset({HookPhase.POST_TOOL}),
                writable_stage_keys=frozenset({"stage.model_input"}),
            )

    def test_final_decision_defers_then_resumes_the_actor(self) -> None:
        """Verifies a deferred final decision appends feedback and resumes the loop."""

        defer_hook = DeferFirstFinalHook(
            hook_id="defer_first",
            phases=frozenset({HookPhase.PRE_FINAL}),
            state_refs=(
                StateRef(
                    key="extension.defer_first.deferred",
                    owner="defer_first",
                    value_type=bool,
                    writers=frozenset({"defer_first"}),
                    default=False,
                ),
            ),
            writable_stage_keys=frozenset({"stage.final_decision"}),
        )
        model = RecordingSequentialModel(
            outputs=[
                "<final_answer>premature</final_answer>",
                "<final_answer>completed</final_answer>",
            ]
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=_ConversationPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime([]),
            max_steps=2,
            hooks=HookPipeline([defer_hook]),
        )

        run = loop.run("Complete the workflow.")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(len(model.model_inputs), 2)
        self.assertEqual(
            model.model_inputs[1].messages[-2].content,
            "<final_answer>premature</final_answer>",
        )
        self.assertEqual(
            model.model_inputs[1].messages[-1].content,
            "Continue gathering the required evidence.",
        )
        deferred = next(event for event in run.trace if event.event_type == "final_deferred")
        self.assertEqual(deferred.payload["feedback"], "Continue gathering the required evidence.")

    def test_later_hook_cannot_reverse_a_deferred_final_decision(self) -> None:
        """Verifies final-decision deferral is monotonic within one Hook phase."""

        defer_hook = DeferFirstFinalHook(
            hook_id="defer_first",
            phases=frozenset({HookPhase.PRE_FINAL}),
            state_refs=(
                StateRef(
                    key="extension.defer_first.deferred",
                    owner="defer_first",
                    value_type=bool,
                    writers=frozenset({"defer_first"}),
                    default=False,
                ),
            ),
            writable_stage_keys=frozenset({"stage.final_decision"}),
        )
        accept_hook = AcceptFinalHook(
            hook_id="accept_later",
            phases=frozenset({HookPhase.PRE_FINAL}),
            writable_stage_keys=frozenset({"stage.final_decision"}),
        )
        loop = _build_loop(
            hooks=HookPipeline([defer_hook, accept_hook]),
            output="<final_answer>premature</final_answer>",
        )

        with self.assertRaisesRegex(StateAccessError, "deferred final decision"):
            loop.run("Complete the workflow.")

    def test_model_driven_hook_records_generation_and_state_change(self) -> None:
        """Verifies the model driven hook records generation and state change contract."""
        backend = RecordingHookModelBackend()
        hook = ModelDrivenDecisionHook(
            hook_id="model_decision",
            phases=frozenset({HookPhase.PRE_PROMPT}),
            state_refs=(
                StateRef(
                    key="extension.model_decision.continue_search",
                    owner="model_decision",
                    value_type=bool,
                    writers=frozenset({"model_decision"}),
                    default=False,
                ),
            ),
            model_profiles=frozenset({"student"}),
        )
        loop = _build_loop(
            hooks=HookPipeline([hook], model_backend=backend),
            output="<final_answer>done</final_answer>",
        )

        run = loop.run("Should search continue?")

        self.assertEqual(len(backend.requests), 1)
        self.assertTrue(
            run.state.hook_state["extension.model_decision.continue_search"]
        )
        model_event = next(
            event for event in run.trace if event.event_type == "hook_model_output"
        )
        self.assertEqual(model_event.payload["hook_id"], "model_decision")
        self.assertEqual(model_event.payload["profile"], "student")
        self.assertEqual(model_event.payload["metadata"]["usage"]["total_tokens"], 7)
        applied_event = next(
            event
            for event in run.trace
            if event.event_type == "hook_applied"
            and event.payload["hook_id"] == "model_decision"
        )
        self.assertEqual(
            applied_event.payload["changes"][0]["key"],
            "extension.model_decision.continue_search",
        )

    def test_result_summary_prompt_hook_injects_one_user_message_after_tool(self) -> None:
        """Verifies the result summary prompt hook injects one user message after tool contract."""
        summary_hook = _build_result_summary_prompt_hook()
        model = RecordingSequentialModel(
            outputs=[
                '<tool_call>{"name": "echo", "arguments": {"text": "evidence"}}</tool_call>',
                "<final_answer>completed</final_answer>",
            ]
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(ToolSet([CallableTool.from_callable(_echo)]).tools),
            max_steps=3,
            hooks=HookPipeline([summary_hook]),
        )

        run = loop.run("Summarize the tool result.")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(len(model.model_inputs), 2)
        injected_message = model.model_inputs[1].messages[-1]
        self.assertEqual(injected_message.role, "user")
        self.assertTrue(injected_message.content)
        self.assertEqual(
            run.state.hook_state["extension.result_summary_prompt.pending"],
            False,
        )
        hook_changes = [
            event.payload["changes"]
            for event in run.trace
            if event.event_type == "hook_applied"
            and event.payload["hook_id"] == "result_summary_prompt"
        ]
        self.assertEqual(hook_changes[1][0]["after"], True)
        self.assertEqual(hook_changes[2][0]["key"], "stage.model_input")
        self.assertEqual(hook_changes[2][1]["after"], False)

    def test_model_input_rewrite_is_ephemeral_without_reinjection(self) -> None:
        """Verifies the model input rewrite is ephemeral without reinjection contract."""
        model = RecordingSequentialModel(
            outputs=[
                '<tool_call>{"name": "echo", "arguments": {"text": "evidence"}}</tool_call>',
                "<final_answer>completed</final_answer>",
            ]
        )
        hook = OneShotModelInputHook(
            hook_id="one_shot_model_input",
            phases=frozenset({HookPhase.POST_PROMPT}),
            writable_stage_keys=frozenset({"stage.model_input"}),
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=_ConversationPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(ToolSet([CallableTool.from_callable(_echo)]).tools),
            max_steps=3,
            hooks=HookPipeline([hook]),
        )

        run = loop.run("Check ModelInput lifetime.")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(model.model_inputs[0].messages[-1].content, "ephemeral context")
        self.assertNotIn(
            "ephemeral context",
            [message.content for message in model.model_inputs[1].messages],
        )

    def test_hooks_bridge_context_across_rounds_through_shared_state(self) -> None:
        """Verifies the hooks bridge context across rounds through shared state contract."""
        model = RecordingSequentialModel(
            outputs=[
                '<tool_call>{"name": "echo", "arguments": {"text": "evidence"}}</tool_call>',
                "<final_answer>completed</final_answer>",
            ]
        )
        context_ref = StateRef(
            key="shared.next_model_context",
            owner="persist_tool_context",
            value_type=str,
            writers=frozenset({"persist_tool_context"}),
            default="",
        )
        persist_hook = PersistToolContextHook(
            hook_id="persist_tool_context",
            phases=frozenset({HookPhase.POST_TOOL}),
            state_refs=(context_ref,),
        )
        inject_hook = InjectPersistedContextHook(
            hook_id="inject_persisted_context",
            phases=frozenset({HookPhase.POST_PROMPT}),
            state_refs=(context_ref,),
            writable_stage_keys=frozenset({"stage.model_input"}),
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=_ConversationPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(ToolSet([CallableTool.from_callable(_echo)]).tools),
            max_steps=3,
            hooks=HookPipeline([persist_hook, inject_hook]),
        )

        run = loop.run("Check cross-hook context relay.")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(
            model.model_inputs[1].messages[-1].content,
            "persisted context: evidence",
        )
        self.assertEqual(run.state.hook_state[context_ref.key], "evidence")

    def test_tool_delegation_uses_main_loop_then_resumes_context(self) -> None:
        """Verifies the tool delegation uses main loop then resumes context contract."""
        delegation_hook = _build_tool_delegation_hook()
        model = RecordingSequentialModel(
            outputs=[
                '<tool_call>{"name": "echo", "arguments": {"text": "actor value"}}</tool_call>',
                "<final_answer>completed</final_answer>",
            ]
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=_ConversationPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(ToolSet([CallableTool.from_callable(_echo)]).tools),
            max_steps=3,
            hooks=HookPipeline([delegation_hook]),
        )

        run = loop.run("Use delegated evidence.")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(
            run.state.tool_interactions[0].tool_call.arguments,
            {"text": "delegated evidence"},
        )
        self.assertIn("Harness delegation request", model.model_inputs[0].messages[-1].content)
        self.assertIn("Delegated tool result is available", model.model_inputs[1].messages[-1].content)
        self.assertNotIn(
            "Harness delegation request",
            model.model_inputs[1].messages[-1].content,
        )
        self.assertEqual(
            run.state.hook_state["extension.tool_delegation.status"],
            "completed",
        )

    def test_tool_delegation_can_derive_a_serializable_query_from_question(self) -> None:
        """Verifies the tool delegation can derive a serializable query from question contract."""
        delegation_hook = _build_tool_delegation_hook(
            {
                "tool_name": "search",
                "arguments": {"topk": 5},
                "request_message": "Retrieve evidence for the question.",
                "query_strategy": "question",
                "injection_mode": "system_append",
            }
        )
        model = RecordingSequentialModel(
            outputs=[
                '<tool_call>{"name": "search", "arguments": {"query": "actor query", "topk": 1}}</tool_call>',
                "<final_answer>completed</final_answer>",
            ]
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(ToolSet([CallableTool.from_callable(_search)]).tools),
            max_steps=3,
            hooks=HookPipeline([delegation_hook]),
        )

        run = loop.run("What evidence is needed?")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(
            run.state.tool_interactions[0].tool_call.arguments,
            {"topk": 5, "query": "What evidence is needed?"},
        )
        self.assertIn(
            "Harness delegation request",
            model.model_inputs[0].messages[0].content,
        )
        self.assertEqual(
            run.state.hook_state["extension.tool_delegation.requested_tool_call"],
            {
                "name": "search",
                "arguments": {"topk": 5, "query": "What evidence is needed?"},
            },
        )
        json.dumps(run.to_dict())

    def test_decomposed_context_controller_resets_each_subtask_context(self) -> None:
        """Verifies the decomposed context controller resets each subtask context contract."""
        controller = _build_decomposed_context_controller_hook()
        backend = PlanningHookModelBackend()
        model = RecordingSequentialModel(
            outputs=[
                '{"name": "search", "arguments": {"query": "actor first", "topk": 1}}',
                '<tool_call>{"name": "search", "arguments": {"query": "actor second", "topk": 1}}</tool_call>',
                "<final_answer>synthesized answer</final_answer>",
            ]
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=_ConversationPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(ToolSet([CallableTool.from_callable(_search)]).tools),
            max_steps=5,
            hooks=HookPipeline([controller], model_backend=backend),
        )

        run = loop.run("Original multi-hop question")

        self.assertEqual(run.answer, "synthesized answer")
        self.assertEqual(len(backend.requests), 1)
        self.assertEqual(
            [item.tool_call.arguments["query"] for item in run.state.tool_interactions],
            ["first query", "second query"],
        )
        self.assertIn("Subtask 1/2", model.model_inputs[0].messages[-1].content)
        self.assertIn("Subtask 2/2", model.model_inputs[1].messages[-1].content)
        self.assertIn(
            "final answer stage",
            model.model_inputs[2].messages[0].content,
        )
        self.assertEqual(
            run.state.hook_state["extension.decomposed_context_controller.status"],
            "completed",
        )
        self.assertEqual(
            len(run.state.hook_state["extension.decomposed_context_controller.evidence"]),
            2,
        )
        bridge_event = next(
            event
            for event in run.trace
            if event.event_type == "hook_applied"
            and event.payload["hook_id"] == "decomposed_context_controller"
            and event.payload["phase"] == "post_parse"
            and event.payload["changes"]
        )
        self.assertEqual(bridge_event.payload["changes"][0]["key"], "stage.parsed_output")

    def test_hooks_share_full_state_and_trace_complete_changes(self) -> None:
        """Verifies the hooks share full state and trace complete changes contract."""
        health_ref = StateRef(
            key="shared.format_health",
            owner="rewrite_output",
            value_type=dict,
            writers=frozenset({"rewrite_output"}),
            default={"rewritten": False},
        )
        rewrite_hook = RewriteOutputHook(
            hook_id="rewrite_output",
            phases=frozenset({HookPhase.POST_MODEL}),
            state_refs=(health_ref,),
            writable_stage_keys=frozenset({"stage.raw_model_output"}),
        )
        observer_hook = ObserveRewriteHook(
            hook_id="observe_rewrite",
            phases=frozenset({HookPhase.POST_MODEL}),
            writable_stage_keys=frozenset({"stage.raw_model_output"}),
        )
        loop = _build_loop(
            hooks=HookPipeline([rewrite_hook, observer_hook]),
            output="<final_answer>raw answer</final_answer>",
        )

        run = loop.run("What is the answer?")

        self.assertEqual(run.answer, "rewritten result")
        self.assertEqual(rewrite_hook.seen_question, "What is the answer?")
        self.assertEqual(
            observer_hook.observed,
            (
                {
                    "rewritten": True,
                    "source": "<final_answer>raw answer</final_answer>",
                },
                "<final_answer>rewritten answer</final_answer>",
                ["<final_answer>raw answer</final_answer>"],
            ),
        )
        self.assertEqual(
            run.state.hook_state["shared.format_health"],
            {
                "rewritten": True,
                "source": "<final_answer>raw answer</final_answer>",
            },
        )

        model_event = next(event for event in run.trace if event.event_type == "model_output")
        self.assertEqual(
            model_event.payload["raw_output"],
            "<final_answer>raw answer</final_answer>",
        )
        rewrite_event = next(
            event
            for event in run.trace
            if event.event_type == "hook_applied"
            and event.payload["hook_id"] == "rewrite_output"
            and event.payload["phase"] == "post_model"
        )
        self.assertEqual(
            rewrite_event.payload["changes"],
            [
                {
                    "key": "shared.format_health",
                    "before": {"rewritten": False},
                    "after": {
                        "rewritten": True,
                        "source": "<final_answer>raw answer</final_answer>",
                    },
                },
                {
                    "key": "stage.raw_model_output",
                    "before": "<final_answer>raw answer</final_answer>",
                    "after": "<final_answer>rewritten answer</final_answer>",
                },
            ],
        )

    def test_hook_cannot_modify_loop_owned_core_state(self) -> None:
        """Verifies the hook cannot modify loop owned core state contract."""
        loop = _build_loop(
            hooks=HookPipeline(
                [
                    IllegalCoreWriteHook(
                        hook_id="illegal",
                        phases=frozenset({HookPhase.PRE_PROMPT}),
                    )
                ]
            ),
            output="<final_answer>ignored</final_answer>",
        )

        with self.assertRaisesRegex(StateAccessError, "loop-owned key core.question"):
            loop.run("Original question")

    def test_lifecycle_audit_hook_covers_all_normal_phases(self) -> None:
        """Verifies the lifecycle audit hook covers all normal phases contract."""
        audit_hook = _build_lifecycle_audit_hook()
        tool_set = ToolSet([CallableTool.from_callable(_echo)])
        loop = AgentLoop(
            model=SequentialModel(
                outputs=[
                    '<tool_call>{"name": "echo", "arguments": {"text": "evidence"}}</tool_call>',
                    "<final_answer>completed</final_answer>",
                ]
            ),
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(tool_set.tools),
            max_steps=3,
            hooks=HookPipeline([audit_hook]),
        )

        run = loop.run("Exercise each normal hook phase.")

        self.assertEqual(run.answer, "completed")
        self.assertEqual(
            [
                event.payload["phase"]
                for event in run.trace
                if event.event_type == "hook_applied"
            ],
            [
                "pre_prompt",
                "post_prompt",
                "post_model",
                "post_parse",
                "pre_tool",
                "post_tool",
                "pre_prompt",
                "post_prompt",
                "post_model",
                "post_parse",
                "pre_final",
            ],
        )
        self.assertEqual(run.state.hook_state, {})

    def test_lifecycle_audit_hook_receives_error_phase(self) -> None:
        """Verifies the lifecycle audit hook receives error phase contract."""
        audit_hook = _build_lifecycle_audit_hook()
        loop = _build_loop(
            hooks=HookPipeline([audit_hook]),
            output="unstructured output",
        )

        run = loop.run("Exercise the error hook phase.")

        self.assertEqual(run.state.hook_state, {})
        self.assertTrue(
            any(
                event.event_type == "hook_applied"
                and event.payload["phase"] == "on_error"
                for event in run.trace
            )
        )

    def test_format_feedback_hook_reports_incomplete_tool_block(self) -> None:
        """Verifies the format feedback hook reports incomplete tool block contract."""
        hook = _build_format_error_feedback_hook()
        model = RecordingSequentialModel(
            outputs=[
                '<tool_call>{"name": "echo", "arguments": {"text": "x"}}',
                "<final_answer>recovered</final_answer>",
            ]
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=_ConversationPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime([]),
            max_steps=2,
            hooks=HookPipeline([hook]),
        )

        run = loop.run("Recover from malformed output.")

        self.assertEqual(run.answer, "recovered")
        feedback = model.model_inputs[1].messages[-1].content
        self.assertIn("<tool_call> is missing </tool_call>", feedback)
        hook_event = next(
            event
            for event in run.trace
            if event.event_type == "hook_applied"
            and event.payload["hook_id"] == "format_error_feedback"
        )
        self.assertEqual(hook_event.payload["phase"], "post_parse")
        self.assertEqual(
            hook_event.payload["changes"][0]["key"],
            "stage.parsed_output",
        )


def _build_loop(hooks: HookPipeline, output: str) -> AgentLoop:
    return AgentLoop(
        model=StaticModel(output=output),
        prompt_builder=TestPromptBuilder(),
        parser=TaggedOutputParser(),
        tool_runtime=ToolRuntime([]),
        max_steps=2,
        hooks=hooks,
    )


class _ConversationPromptBuilder:
    def build(self, state) -> ModelInput:
        return ModelInput.from_messages(
            [
                ChatMessage(role="system", content="test system"),
                ChatMessage(role="user", content=state.question),
                *state.conversation_messages,
            ]
        )


@tool(name="echo")
def _echo(text: Annotated[str, ToolArg("Text returned to the agent.")]) -> ToolResult:
    """Return a deterministic test observation."""

    return ToolResult(name="echo", content=text)


@tool(name="search")
def _search(
    query: Annotated[str, ToolArg("Query returned to the agent.")],
    topk: Annotated[int, ToolArg("Result count.")] = 5,
) -> ToolResult:
    """Return the query and count as a deterministic test observation."""

    return ToolResult(name="search", content=f"{query} ({topk})")


def _build_lifecycle_audit_hook() -> BaseHook:
    spec = ComponentSpec(
        instance_id="lifecycle_audit",
        entrypoint="extensions/lifecycle_audit/plugin.py:build",
        config={},
        evolution_policy=EvolutionPolicy.MUTABLE,
    )
    factory = load_factory(DELEGATION_EXPERIMENT_PLUGINS_ROOT, spec)
    return factory(
        spec.config,
        PluginContext(plugins_root=DELEGATION_EXPERIMENT_PLUGINS_ROOT),
    )


def _build_result_summary_prompt_hook() -> BaseHook:
    spec = ComponentSpec(
        instance_id="result_summary_prompt",
        entrypoint="extensions/result_summary_prompt/plugin.py:build",
        config={},
        evolution_policy=EvolutionPolicy.MUTABLE,
    )
    factory = load_factory(DELEGATION_EXPERIMENT_PLUGINS_ROOT, spec)
    return factory(
        {}, PluginContext(plugins_root=DELEGATION_EXPERIMENT_PLUGINS_ROOT)
    )


def _build_format_error_feedback_hook() -> BaseHook:
    spec = ComponentSpec(
        instance_id="format_error_feedback",
        entrypoint="extensions/format_error_feedback/plugin.py:build",
        config={},
        evolution_policy=EvolutionPolicy.FIXED,
    )
    factory = load_factory(CRITIC_PLUGINS_ROOT, spec)
    return factory({}, PluginContext(plugins_root=CRITIC_PLUGINS_ROOT))


def _build_tool_delegation_hook(config: dict[str, object] | None = None) -> BaseHook:
    spec = ComponentSpec(
        instance_id="tool_delegation",
        entrypoint="extensions/tool_delegation/plugin.py:build",
        config=config or {
            "tool_name": "echo",
            "arguments": {"text": "delegated evidence"},
            "request_message": "Retrieve the requested evidence.",
        },
        evolution_policy=EvolutionPolicy.MUTABLE,
    )
    factory = load_factory(DELEGATION_EXPERIMENT_PLUGINS_ROOT, spec)
    return factory(
        spec.config,
        PluginContext(plugins_root=DELEGATION_EXPERIMENT_PLUGINS_ROOT),
    )


def _build_decomposed_context_controller_hook() -> BaseHook:
    spec = ComponentSpec(
        instance_id="decomposed_context_controller",
        entrypoint="extensions/decomposed_context_controller/plugin.py:build",
        config={
            "planner_prompt_file": "extensions/decomposed_context_controller/templates/planner.md",
            "subtask_system_prompt_file": "extensions/decomposed_context_controller/templates/subtask_system.md",
            "synthesis_system_prompt_file": "extensions/decomposed_context_controller/templates/synthesis_system.md",
            "max_subtasks": 2,
            "topk": 5,
            "max_evidence_chars": 100,
        },
        evolution_policy=EvolutionPolicy.MUTABLE,
    )
    factory = load_factory(DECOMPOSED_EXPERIMENT_PLUGINS_ROOT, spec)
    return factory(
        spec.config,
        PluginContext(plugins_root=DECOMPOSED_EXPERIMENT_PLUGINS_ROOT),
    )
