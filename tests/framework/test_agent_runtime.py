from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from unittest import TestCase

from search_harness.framework.agent.agent import Agent
from search_harness.framework.agent.model import ModelInput, ModelResponse
from search_harness.framework.agent.runner import LoopRunner
from search_harness.framework.harness.lifecycle import HookPipeline
from search_harness.framework.harness.runtime import Harness
from search_harness.framework.harness.tagged_output import TaggedOutputParser
from search_harness.framework.tools import (
    CallableTool,
    ToolArg,
    ToolExecutor,
    ToolResult,
    tool,
)


@dataclass
class SequenceModel:
    outputs: list[str]

    def generate(self, model_input: ModelInput) -> ModelResponse:
        del model_input
        return ModelResponse(raw_output=self.outputs.pop(0))


class TestPrompt:
    def build(self, state) -> ModelInput:
        from search_harness.framework.agent.model import ChatMessage

        return ModelInput.from_messages(
            [ChatMessage(role="user", content=state.question)]
        )


@tool(name="search")
def _search(
    query: Annotated[str, ToolArg("Evidence query.")],
) -> ToolResult:
    """Return deterministic evidence for a framework test."""

    return ToolResult(name="search", content=f"evidence for {query}")


class AgentRuntimeTest(TestCase):
    def test_loop_runner_executes_agent_composed_from_harness_and_model(self) -> None:
        """Verifies the canonical Agent/Harness/LoopRunner composition path."""

        tool_instance = CallableTool.from_callable(_search)
        harness = Harness(
            prompt=TestPrompt(),
            output=TaggedOutputParser(),
            tool_executor=ToolExecutor([tool_instance]),
            lifecycle=HookPipeline(),
        )
        agent = Agent(
            harness=harness,
            model=SequenceModel(
                outputs=[
                    (
                        '<tool_call>{"name":"search","arguments":'
                        '{"query":"x"}}</tool_call>'
                    ),
                    "<final_answer>answer</final_answer>",
                ]
            ),
        )

        result = LoopRunner(max_steps=3).run(agent, "question")

        self.assertEqual(result.answer, "answer")
        self.assertEqual(len(result.state.tool_interactions), 1)
        self.assertEqual(
            result.state.tool_interactions[0].tool_result.content,
            "evidence for x",
        )

    def test_harness_instances_isolate_run_and_extension_state(self) -> None:
        """Verifies one reusable Harness creates isolated run-scoped instances."""

        harness = Harness(
            prompt=TestPrompt(),
            output=TaggedOutputParser(),
            tool_executor=ToolExecutor([]),
            lifecycle=HookPipeline(),
        )

        first = harness.instantiate("first", max_steps=2)
        second = harness.instantiate("second", max_steps=2)
        first.state.hook_state["value"] = "first-only"

        self.assertIs(first.harness, harness)
        self.assertIs(second.harness, harness)
        self.assertEqual(first.state.question, "first")
        self.assertEqual(second.state.question, "second")
        self.assertNotIn("value", second.state.hook_state)
