from __future__ import annotations

from pathlib import Path
from typing import Annotated
from unittest import TestCase

from search_harness.framework import AgentState, ToolResult
from search_harness.framework.harness import (
    ComponentDeclaration,
    ComponentFactoryContext,
    ComponentLoader,
)
from search_harness.framework.tools import CallableTool, ToolArg, ToolSet, tool


BASELINE_TEMPLATE_ROOT = (
    Path(__file__).parents[2] / "harness_templates" / "student" / "baseline"
)
PROMPT_ENTRYPOINT = "prompt/component.py:build"


class SimpleSearchPromptTest(TestCase):
    def test_loads_default_system_prompt_from_resource(self) -> None:
        """Verifies the loads default system prompt from resource contract."""
        prompt = (
            BASELINE_TEMPLATE_ROOT
            / "prompt"
            / "system.md"
        ).read_text(encoding="utf-8")

        self.assertIn("<tool_call>", prompt)
        self.assertIn("<final_answer>", prompt)

    def test_builder_uses_default_system_prompt_resource(self) -> None:
        """Verifies the builder uses default system prompt resource contract."""
        builder = _build_prompt(_search_tools())
        model_input = builder.build(
            AgentState(question="Who wrote The Hobbit?", max_steps=2)
        )

        messages = model_input.to_dict()["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("<tool_call>", messages[0]["content"])
        self.assertIn("`search`", messages[0]["content"])
        self.assertIn("`query` (string, required)", messages[0]["content"])
        self.assertIn("`topk` (integer, optional, default=3, minimum=1)", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "Who wrote The Hobbit?")


@tool(name="search")
def _search(
    query: Annotated[str, ToolArg("A concise evidence query.")],
    topk: Annotated[int, ToolArg("Number of passages.", minimum=1)] = 3,
) -> ToolResult:
    """Search a test corpus for evidence."""

    del query, topk
    return ToolResult(name="search", content="")


def _search_tools() -> ToolSet:
    return ToolSet([CallableTool.from_callable(_search)])


def _build_prompt(tools: ToolSet):
    spec = ComponentDeclaration(
        instance_id="simple_search",
        entrypoint=PROMPT_ENTRYPOINT,
        config={},
    )
    factory = ComponentLoader(BASELINE_TEMPLATE_ROOT).load_factory(spec)
    return factory(
        {},
        ComponentFactoryContext(template_root=BASELINE_TEMPLATE_ROOT),
        tools,
    )
