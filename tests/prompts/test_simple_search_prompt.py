from __future__ import annotations

from pathlib import Path
from typing import Annotated
from unittest import TestCase

from search_harness.core import AgentState, ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolSet, tool
from search_harness.registry import ComponentSpec, EvolutionPolicy, PluginContext
from search_harness.registry.plugin_importer import load_factory


BASELINE_PLUGINS_ROOT = Path(__file__).parents[2] / "harness_templates" / "actor" / "baseline" / "plugins"
PROMPT_ENTRYPOINT = "prompts/simple_search/plugin.py:build"


class SimpleSearchPromptTest(TestCase):
    def test_loads_default_system_prompt_from_resource(self) -> None:
        """Verifies the loads default system prompt from resource contract."""
        prompt = (
            BASELINE_PLUGINS_ROOT / "prompts" / "simple_search" / "templates" / "system.md"
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
    spec = ComponentSpec(
        instance_id="simple_search",
        entrypoint=PROMPT_ENTRYPOINT,
        config={},
        evolution_policy=EvolutionPolicy.FIXED,
    )
    factory = load_factory(BASELINE_PLUGINS_ROOT, spec)
    return factory({}, PluginContext(plugins_root=BASELINE_PLUGINS_ROOT), tools)
