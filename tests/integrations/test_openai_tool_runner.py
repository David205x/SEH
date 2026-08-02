"""Provider-native tool Runner integration boundary tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from search_harness.framework.tools import (
    ToolDefinition,
    ToolParameter,
    ToolResult,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleToolRunner,
)


class _ReplayCompletions:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = list(messages)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.messages:
            raise AssertionError("tool runner made an unexpected request")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=self.messages.pop(0))],
            usage={
                "prompt_tokens": 4,
                "completion_tokens": 2,
                "total_tokens": 6,
            },
        )


class _ReplayClient:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.completions = _ReplayCompletions(messages)
        self.chat = SimpleNamespace(completions=self.completions)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _EchoTool:
    name = "echo"
    definition = ToolDefinition(
        name=name,
        description="Echo one value.",
        parameters=(
            ToolParameter(
                name="value",
                annotation=str,
                description="Value to echo.",
                required=True,
            ),
        ),
    )

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return ToolResult(
            name=self.name,
            content=str(arguments["value"]),
            metadata={"echoed": True},
        )


def _tool_call(name: str, call_id: str, arguments: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


class OpenAICompatibleToolRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_runs_tools_and_uses_caller_terminal_language(self) -> None:
        client = _ReplayClient(
            [
                {"role": "assistant", "content": "working"},
                _tool_call("echo", "echo_1", '{"value":"hello"}'),
                _tool_call("finish", "finish_1", '{"answer":"done"}'),
            ]
        )
        config = OpenAICompatibleConfig(
            base_url="https://provider.invalid/v1/chat/completions",
            model_id="provider-test",
            max_tokens=64,
            temperature=0.2,
            seed=9,
        )

        result = await OpenAICompatibleToolRunner(
            config=config,
            client=client,
        ).run(
            messages=[{"role": "user", "content": "begin"}],
            tools=(_EchoTool(),),
            terminal_tool_name="finish",
            terminal_tool_description="Finish this generic operation.",
            terminal_output_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
            missing_terminal_message="Submit a terminal result now.",
            submit_terminal=lambda arguments: (
                arguments,
                "accepted",
                {"terminal": True},
            ),
            max_turns=4,
            run_label="generic operation",
        )

        self.assertEqual(result.output, {"answer": "done"})
        self.assertEqual(
            [call.name for call in result.tool_calls],
            ["echo", "finish"],
        )
        self.assertEqual(result.usage["requests"], 3)
        self.assertEqual(result.usage["total_tokens"], 18)
        self.assertEqual(
            result.transcript[2],
            {"role": "user", "content": "Submit a terminal result now."},
        )
        terminal_schema = client.completions.requests[0]["tools"][-1]
        self.assertEqual(
            terminal_schema["function"]["description"],
            "Finish this generic operation.",
        )
        self.assertFalse(client.closed)


if __name__ == "__main__":
    unittest.main()
