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
    NativeToolRunExhausted,
    OpenAICompatibleConfig,
    OpenAICompatibleToolSession,
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


class _SyncReplayCompletions:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = list(messages)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.messages:
            raise AssertionError("tool session made an unexpected request")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=self.messages.pop(0))],
            usage={
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        )


class _SyncReplayClient:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.completions = _SyncReplayCompletions(messages)
        self.chat = SimpleNamespace(completions=self.completions)
        self.closed = False

    def close(self) -> None:
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
    async def test_sends_ollama_reasoning_effort_when_disabled(self) -> None:
        client = _ReplayClient(
            [_tool_call("finish", "finish_1", '{"answer":"done"}')]
        )
        config = OpenAICompatibleConfig(
            base_url="http://127.0.0.1:11434/v1",
            model_id="qwen3:8b",
            ollama_think=False,
        )

        await OpenAICompatibleToolRunner(
            config=config,
            client=client,
        ).run(
            messages=[{"role": "user", "content": "begin"}],
            tools=(),
            terminal_tool_name="finish",
            terminal_tool_description="Finish.",
            terminal_output_schema={"type": "object"},
            missing_terminal_message="Submit now.",
            submit_terminal=lambda arguments: (
                arguments,
                "accepted",
                {"terminal": True},
            ),
            max_turns=1,
            run_label="test operation",
        )

        self.assertEqual(
            client.completions.requests[0]["reasoning_effort"],
            "none",
        )

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

    async def test_exhaustion_retains_transcript_and_focuses_repeat_repair(
        self,
    ) -> None:
        client = _ReplayClient(
            [
                _tool_call("finish", "finish_1", '{"answer":"too long"}'),
                _tool_call("finish", "finish_2", '{"answer":"still long"}'),
            ]
        )
        config = OpenAICompatibleConfig(
            base_url="https://provider.invalid/v1",
            model_id="provider-test",
            max_tokens=64,
        )

        def reject(arguments: dict[str, Any]) -> tuple[None, str, dict[str, Any]]:
            return None, "- answer: maximum_length=4", {
                "terminal": False,
                "validation_error": True,
                "validation_error_fields": ["answer:string_too_long"],
            }

        with self.assertRaises(NativeToolRunExhausted) as raised:
            await OpenAICompatibleToolRunner(
                config=config,
                client=client,
            ).run(
                messages=[{"role": "user", "content": "begin"}],
                tools=(),
                terminal_tool_name="finish",
                terminal_tool_description="Finish.",
                terminal_output_schema={"type": "object"},
                missing_terminal_message="Submit now.",
                submit_terminal=reject,
                max_turns=2,
                run_label="test operation",
            )

        failure = raised.exception.failure
        self.assertEqual(failure.turn_count, 2)
        self.assertEqual(failure.usage["requests"], 2)
        self.assertEqual(len(failure.tool_calls), 2)
        self.assertIn(
            "The same fields still fail validation",
            failure.transcript[-1]["content"],
        )


class OpenAICompatibleToolSessionTest(unittest.TestCase):
    def test_sends_ollama_reasoning_effort_when_disabled(self) -> None:
        client = _SyncReplayClient([_tool_call("echo", "echo_1", '{}')])
        session = OpenAICompatibleToolSession(
            config=OpenAICompatibleConfig(
                base_url="http://127.0.0.1:11434/v1",
                model_id="qwen3:8b",
                ollama_think=False,
            ),
            messages=[{"role": "user", "content": "begin"}],
            client=client,
        )

        session.complete(tools=(_EchoTool(),))

        self.assertEqual(
            client.completions.requests[0]["reasoning_effort"],
            "none",
        )

    def test_persists_native_messages_across_dynamic_tool_turns(self) -> None:
        client = _SyncReplayClient(
            [
                {
                    **_tool_call("echo", "echo_1", '{"value":"hello"}'),
                    "reasoning_content": "inspect first",
                },
                _tool_call("echo", "echo_2", '{"value":"again"}'),
            ]
        )
        config = OpenAICompatibleConfig(
            base_url="https://provider.invalid/v1",
            model_id="provider-test",
            max_tokens=64,
            thinking_mode="disabled",
        )
        session = OpenAICompatibleToolSession(
            config=config,
            messages=[{"role": "user", "content": "begin"}],
            client=client,
        )

        first = session.complete(tools=(_EchoTool(),))
        session.commit_assistant(first)
        session.append_tool_result(
            call=first.tool_calls[0],
            content="hello",
            metadata={"echoed": True},
        )
        session.append_user_message("next activation")
        second = session.complete(tools=(_EchoTool(),))

        self.assertEqual(second.request_messages[-1]["content"], "next activation")
        self.assertEqual(
            second.request_messages[1]["reasoning_content"],
            "inspect first",
        )
        self.assertEqual(second.request_messages[2]["role"], "tool")
        self.assertEqual(session.usage["total_tokens"], 16)
        self.assertEqual(
            client.completions.requests[0]["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        session.close()
        self.assertFalse(client.closed)


if __name__ == "__main__":
    unittest.main()
