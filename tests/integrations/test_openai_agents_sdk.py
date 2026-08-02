"""Role-neutral OpenAI Agents SDK Runner tests."""

from __future__ import annotations

import json
import unittest
from typing import Any, AsyncIterator

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall
from pydantic import BaseModel

from search_harness.integrations.openai_agents_sdk import AgentsSdkRunner


class _Output(BaseModel):
    answer: str


class _TerminalReplayModel(Model):
    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return ModelResponse(
            output=[
                ResponseFunctionToolCall(
                    arguments=json.dumps({"answer": "done"}),
                    call_id="terminal_1",
                    name="finish",
                    type="function_call",
                    status="completed",
                )
            ],
            usage=Usage(),
            response_id=None,
        )

    async def stream_response(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        if False:
            yield None


class AgentsSdkRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_runs_without_teacher_role_types(self) -> None:
        validated: list[str] = []
        result = await AgentsSdkRunner(
            max_turns=2,
            output_mode="tool",
            model=_TerminalReplayModel(),
            model_provenance={"provider": "replay"},
        ).run(
            agent_name="generic_agent",
            instructions="Return one structured answer.",
            run_input="begin",
            context={"scope": "generic"},
            tools=(),
            output_type=_Output,
            validate_output=lambda output: validated.append(output.answer),
            terminal_tool_name="finish",
            terminal_tool_description="Submit the generic result.",
            terminal_confirmation="Generic result submitted.",
            missing_terminal_error="No generic result was submitted",
            workflow_name="generic:test",
        )

        self.assertEqual(result.output, _Output(answer="done"))
        self.assertEqual(result.model, {"provider": "replay"})
        self.assertEqual(validated, ["done", "done"])
        self.assertEqual([call.name for call in result.tool_calls], ["finish"])


if __name__ == "__main__":
    unittest.main()
