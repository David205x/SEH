from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated
from unittest import TestCase

from search_harness.framework import (
    Agent,
    ChatMessage,
    Harness,
    HookPipeline,
    LoopRunner,
    ModelInput,
    ModelResponse,
    ParsedOutputKind,
    RunResult,
    RunStatus,
    TaggedOutputParser,
    ToolExecutor,
    ToolResult,
)
from search_harness.framework.tools import CallableTool, ToolArg, ToolSet, tool


@dataclass
class SequentialModel:
    outputs: list[str]

    def __post_init__(self) -> None:
        self.model_inputs: list[ModelInput] = []

    def generate(self, model_input: ModelInput) -> ModelResponse:
        self.model_inputs.append(model_input)
        if not self.outputs:
            raise AssertionError("model received more prompts than expected")
        return ModelResponse(raw_output=self.outputs.pop(0))


@dataclass
class MetadataModel:
    output: str
    metadata: dict[str, str]

    def generate(self, model_input: ModelInput) -> ModelResponse:
        del model_input
        return ModelResponse(raw_output=self.output, metadata=self.metadata)


class TestPromptBuilder:
    def build(self, state) -> ModelInput:
        messages = [
            {"role": "system", "content": "test system"},
            {"role": "user", "content": state.question},
        ]
        messages.extend(message.to_dict() for message in state.conversation_messages)
        return ModelInput.from_messages([ChatMessage(**message) for message in messages])


class AgentLoopTest(TestCase):
    def test_agent_loop_records_optional_native_model_metadata(self) -> None:
        """Verifies the agent loop records optional native model metadata contract."""
        run = _run_agent(
            model=MetadataModel(
                output="Visible preamble.\n<final_answer>ok</final_answer>",
                metadata={"reasoning_content": "native reasoning"},
            ),
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_executor=ToolExecutor([]),
            max_steps=1,
            question="Return a result.",
        )

        model_event = next(event for event in run.trace if event.event_type == "model_output")
        self.assertEqual(
            model_event.payload["metadata"],
            {"reasoning_content": "native reasoning"},
        )
        self.assertEqual(
            run.state.parsed_outputs[0].inband_thinking,
            "Visible preamble.",
        )

    def test_agent_loop_runs_tool_then_final_answer(self) -> None:
        """Verifies the agent loop runs tool then final answer contract."""
        model = SequentialModel(
            outputs=[
                'I should search for evidence.\n<tool_call>{"name": "search", "arguments": {"query": "hobbit", "topk": 3}}</tool_call>',
                "The evidence names Tolkien.\n<final_answer>The Hobbit was written by J. R. R. Tolkien.</final_answer>",
            ]
        )
        tool_set = _build_search_tools()
        run = _run_agent(
            model=model,
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_executor=ToolExecutor(tool_set.tools),
            max_steps=4,
            question="Who wrote The Hobbit?",
        )

        self.assertIs(run.status, RunStatus.COMPLETED)
        self.assertEqual(run.answer, "The Hobbit was written by J. R. R. Tolkien.")
        self.assertEqual(len(model.model_inputs), 2)
        self.assertEqual(
            model.model_inputs[0].to_dict()["messages"][1]["content"],
            "Who wrote The Hobbit?",
        )
        second_messages = model.model_inputs[1].to_dict()["messages"]
        self.assertEqual(
            [message["role"] for message in second_messages],
            ["system", "user", "assistant", "user"],
        )
        self.assertIn("evidence for hobbit", second_messages[-1]["content"])
        self.assertEqual(second_messages[-1]["content"], "evidence for hobbit")
        self.assertEqual(
            run.state.parsed_outputs[0].inband_thinking,
            "I should search for evidence.",
        )
        self.assertEqual(
            run.state.parsed_outputs[1].inband_thinking,
            "The evidence names Tolkien.",
        )
        self.assertEqual(
            [event.event_type for event in run.trace],
            [
                "model_input",
                "model_output",
                "parsed_output",
                "tool_call",
                "tool_result",
                "model_input",
                "model_output",
                "parsed_output",
                "final_answer_candidate",
                "final_answer",
            ],
        )

    def test_agent_loop_accepts_final_answer_without_pre_final_hooks(self) -> None:
        """Verifies the default final-decision acceptance contract without Hooks."""

        run = _run_agent(
            model=SequentialModel(outputs=["<final_answer>answer</final_answer>"]),
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_executor=ToolExecutor([]),
            max_steps=1,
            question="Return an answer.",
        )

        self.assertIs(run.status, RunStatus.COMPLETED)
        self.assertEqual(run.answer, "answer")
        self.assertFalse(any(event.event_type == "final_deferred" for event in run.trace))

    def test_agent_loop_retries_invalid_model_output_with_feedback(self) -> None:
        """Verifies the agent loop retries invalid model output with feedback contract."""
        model = SequentialModel(
            outputs=[
                "I think the answer is Tolkien.",
                "<final_answer>J. R. R. Tolkien</final_answer>",
            ]
        )
        run = _run_agent(
            model=model,
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_executor=ToolExecutor([]),
            max_steps=4,
            question="Who wrote The Hobbit?",
        )

        self.assertIs(run.status, RunStatus.COMPLETED)
        self.assertEqual(run.answer, "J. R. R. Tolkien")
        self.assertEqual(len(model.model_inputs), 2)
        retry_messages = model.model_inputs[1].messages
        self.assertEqual(
            [message.role for message in retry_messages],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(retry_messages[-2].content, "I think the answer is Tolkien.")
        self.assertIn("could not be parsed", retry_messages[-1].content)
        self.assertTrue(
            any(event.event_type == "invalid_output_feedback" for event in run.trace)
        )

    def test_parser_treats_content_outside_action_as_inband_thinking(self) -> None:
        """Verifies the parser treats content outside action as inband thinking contract."""
        parsed = TaggedOutputParser().parse(
            "Reason before.\n<final_answer>answer</final_answer>\nReason after."
        )

        self.assertEqual(parsed.final_answer, "answer")
        self.assertEqual(
            parsed.inband_thinking,
            "Reason before.\n\nReason after.",
        )

    def test_parser_allows_action_tags_inside_tool_json_strings(self) -> None:
        """验证工具参数可携带包含历史 action 标签的完整模型上下文。"""

        messages = [
            {
                "role": "assistant",
                "content": (
                    '<tool_call>{"name":"search","arguments":{}}</tool_call>'
                ),
            },
            {
                "role": "assistant",
                "content": "<final_answer>an earlier answer</final_answer>",
            },
        ]
        raw_output = (
            '<tool_call>{"name":"replace_model_input","arguments":'
            f'{{"messages_json":{json.dumps(json.dumps(messages))}}}'
            "}</tool_call>"
        )

        parsed = TaggedOutputParser().parse(raw_output)

        self.assertIs(parsed.kind, ParsedOutputKind.TOOL_CALL)
        self.assertEqual(parsed.tool_call.name, "replace_model_input")
        self.assertEqual(
            json.loads(parsed.tool_call.arguments["messages_json"]),
            messages,
        )

    def test_agent_loop_stops_when_max_steps_reached(self) -> None:
        """Verifies the agent loop stops when max steps reached contract."""
        model = SequentialModel(
            outputs=[
                '<tool_call>{"name": "search", "arguments": {"query": "a", "topk": 3}}</tool_call>',
                '<tool_call>{"name": "search", "arguments": {"query": "b", "topk": 3}}</tool_call>',
            ]
        )
        tool_set = _build_search_tools()
        run = _run_agent(
            model=model,
            prompt_builder=TestPromptBuilder(),
            parser=TaggedOutputParser(),
            tool_executor=ToolExecutor(tool_set.tools),
            max_steps=2,
            question="Need repeated search?",
        )

        self.assertIs(run.status, RunStatus.MAX_STEPS_REACHED)
        self.assertIsNone(run.answer)
        self.assertEqual(run.error, "agent reached max_steps=2")
        self.assertEqual(run.trace[-1].event_type, "max_steps_reached")


@tool(name="search")
def _search(
    query: Annotated[str, ToolArg("A concise evidence query.")],
    topk: Annotated[int, ToolArg("Number of passages.", minimum=1)] = 3,
) -> ToolResult:
    """Search a test corpus for evidence."""

    del topk
    return ToolResult(name="search", content=f"evidence for {query}")


def _build_search_tools() -> ToolSet:
    return ToolSet([CallableTool.from_callable(_search)])


def _run_agent(
    *,
    model: object,
    prompt_builder: object,
    parser: object,
    tool_executor: ToolExecutor,
    max_steps: int,
    question: str,
) -> RunResult:
    harness = Harness(
        prompt=prompt_builder,
        output=parser,
        tool_executor=tool_executor,
        lifecycle=HookPipeline(),
    )
    return LoopRunner(max_steps=max_steps).run(
        Agent(harness=harness, model=model),
        question,
    )
