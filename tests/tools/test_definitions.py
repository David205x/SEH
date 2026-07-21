from __future__ import annotations

from typing import Annotated
from unittest import TestCase

from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolSet, tool


@tool(name="echo")
def _echo(
    text: Annotated[str, ToolArg("Text to return unchanged.")],
    count: Annotated[int, ToolArg("Repeat count.", minimum=1)] = 1,
) -> ToolResult:
    """Return text a requested number of times."""

    return ToolResult(name="echo", content=text * count)


class ToolDefinitionTest(TestCase):
    def test_callable_tool_binds_defaults_and_validates_arguments(self) -> None:
        """Verifies the callable tool binds defaults and validates arguments contract."""
        tool_instance = CallableTool.from_callable(_echo)

        result = tool_instance.run({"text": "ha"})

        self.assertEqual(result.content, "ha")
        self.assertEqual(
            tool_instance.definition.to_json_schema()["required"], ["text"]
        )

    def test_callable_tool_returns_a_model_visible_input_error(self) -> None:
        """Verifies the callable tool returns a model visible input error contract."""
        tool_instance = CallableTool.from_callable(_echo)

        result = tool_instance.run({"text": "ha", "count": 0})

        self.assertEqual(
            result.content,
            "TOOL_INPUT_ERROR: tool 'echo' argument 'count' must be >= 1",
        )
        self.assertEqual(result.metadata["error_type"], "input_validation")

    def test_tool_set_rejects_duplicate_names(self) -> None:
        """Verifies the tool set rejects duplicate names contract."""
        first = CallableTool.from_callable(_echo)
        second = CallableTool.from_callable(_echo)

        with self.assertRaisesRegex(ValueError, "duplicate tool names"):
            ToolSet([first, second])
