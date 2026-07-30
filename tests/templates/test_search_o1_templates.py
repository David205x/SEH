from __future__ import annotations

from pathlib import Path
from typing import Annotated
from unittest import TestCase

from search_harness.core import (
    AgentState,
    ChatMessage,
    HookModelRequest,
    HookModelResponse,
    HookPhase,
    HookPipeline,
    ModelInput,
    ToolCall,
    ToolResult,
)
from search_harness.core.trace import InMemoryTraceRecorder
from search_harness.framework.tooling import CallableTool, ToolArg, ToolSet, tool
from search_harness.registry import ComponentSpec, EvolutionPolicy, PluginContext
from search_harness.registry.manifest import load_manifest
from search_harness.registry.plugin_importer import load_factory


TEMPLATES_ROOT = (
    Path(__file__).parents[2] / "harness_templates" / "search-o1"
)
RAG_ROOT = TEMPLATES_ROOT / "run_rag_agent" / "plugins"
O1_ROOT = TEMPLATES_ROOT / "o1" / "plugins"
SHOWCASE_ROOT = TEMPLATES_ROOT / "hook_showcase" / "plugins"


class _RecordingHookModelBackend:
    def __init__(self, output: str) -> None:
        self.output = output
        self.requests: list[HookModelRequest] = []

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(raw_output=self.output)


class SearchO1TemplateTest(TestCase):
    def test_manifests_define_the_two_expected_harnesses(self) -> None:
        """Verifies the templates expose agentic search and Search-o1 variants."""

        rag = load_manifest(RAG_ROOT)
        o1 = load_manifest(O1_ROOT)

        self.assertEqual(rag.harness_id, "search_o1_run_rag_agent")
        self.assertEqual(rag.extensions, ())
        self.assertEqual(o1.harness_id, "search_o1")
        self.assertEqual(
            [extension.instance_id for extension in o1.extensions],
            ["reason_in_documents"],
        )

    def test_both_prompts_render_the_search_tool_protocol(self) -> None:
        """Verifies both variants preserve the core tagged tool contract."""

        rag_builder = _build_prompt(
            RAG_ROOT,
            "prompts/agentic_search/plugin.py:build",
        )
        o1_builder = _build_prompt(
            O1_ROOT,
            "prompts/search_o1/plugin.py:build",
        )

        for builder in (rag_builder, o1_builder):
            model_input = builder.build(
                AgentState(question="Find the bridge entity.", max_steps=3)
            )
            system = model_input.messages[0].content
            self.assertIn("<tool_call>", system)
            self.assertIn("<final_answer>", system)
            self.assertIn("`search`", system)

    def test_reason_in_documents_replaces_the_search_observation(self) -> None:
        """Verifies Search-o1 refines passages before the next Actor turn."""

        hook = _build_reason_in_documents_hook()
        backend = _RecordingHookModelBackend(
            "Analysis first.\n\n**Final Information**\n\n"
            "The retrieved passage establishes the bridge relation."
        )
        pipeline = HookPipeline((hook,), model_backend=backend)
        state = AgentState(question="Which entity completes the bridge?", max_steps=3)
        state.model_outputs.append(
            "I need evidence.\n"
            '<tool_call>{"name":"search","arguments":{"query":"bridge relation"}}</tool_call>'
        )
        state.conversation_messages.append(
            ChatMessage(role="assistant", content="Earlier reasoning.")
        )
        store = pipeline.begin_run(state)
        trace = InMemoryTraceRecorder()

        values = pipeline.run_phase(
            HookPhase.POST_TOOL,
            state=state,
            store=store,
            trace=trace,
            stage_values={
                "tool_call": ToolCall(
                    name="search",
                    arguments={"query": "bridge relation", "topk": 5},
                ),
                "tool_result": ToolResult(
                    name="search",
                    content='[{"passages":[{"contents":"raw passage"}]}]',
                    metadata={"request": {"topk": 5}},
                ),
            },
        )

        result = values["tool_result"]
        self.assertEqual(
            result.content,
            "The retrieved passage establishes the bridge relation.",
        )
        self.assertEqual(result.metadata["request"], {"topk": 5})
        self.assertEqual(len(backend.requests), 1)
        reasoner_messages = backend.requests[0].model_input.messages
        self.assertIn("Which entity completes the bridge?", reasoner_messages[1].content)
        self.assertIn("bridge relation", reasoner_messages[1].content)
        self.assertIn("raw passage", reasoner_messages[1].content)
        self.assertEqual(
            [event.event_type for event in trace.events],
            ["hook_model_output", "hook_applied"],
        )


class HookShowcaseTemplateTest(TestCase):
    def test_showcase_registers_three_ordered_hooks(self) -> None:
        """Verifies monitoring, editing, and injection are separate components."""

        manifest = load_manifest(SHOWCASE_ROOT)

        self.assertEqual(
            [extension.instance_id for extension in manifest.extensions],
            [
                "lifecycle_monitor",
                "search_query_editor",
                "result_guidance",
            ],
        )

    def test_hooks_monitor_edit_and_inject_across_phases(self) -> None:
        """Verifies the showcase demonstrates the three Hook mutation patterns."""

        hooks = _build_manifest_hooks(SHOWCASE_ROOT)
        pipeline = HookPipeline(hooks)
        state = AgentState(question="Find the bridge entity.", max_steps=3)
        store = pipeline.begin_run(state)
        trace = InMemoryTraceRecorder()

        pipeline.run_phase(
            HookPhase.PRE_PROMPT,
            state=state,
            store=store,
            trace=trace,
        )
        pre_tool = pipeline.run_phase(
            HookPhase.PRE_TOOL,
            state=state,
            store=store,
            trace=trace,
            stage_values={
                "tool_call": ToolCall(
                    name="search",
                    arguments={"query": "  bridge   entity  ", "topk": 99},
                )
            },
        )
        edited_call = pre_tool["tool_call"]
        pipeline.run_phase(
            HookPhase.POST_TOOL,
            state=state,
            store=store,
            trace=trace,
            stage_values={
                "tool_call": edited_call,
                "tool_result": ToolResult(
                    name="search",
                    content="retrieved evidence",
                ),
            },
        )
        post_prompt = pipeline.run_phase(
            HookPhase.POST_PROMPT,
            state=state,
            store=store,
            trace=trace,
            stage_values={
                "model_input": ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content="system"),
                        ChatMessage(role="user", content=state.question),
                        ChatMessage(role="user", content="retrieved evidence"),
                    ]
                )
            },
        )

        self.assertEqual(
            edited_call.arguments,
            {"query": "bridge entity", "topk": 5},
        )
        injected = post_prompt["model_input"].messages[-1]
        self.assertEqual(injected.role, "user")
        self.assertIn('search for "bridge entity"', injected.content)
        self.assertEqual(
            state.hook_state["extension.lifecycle_monitor.phase_counts"],
            {
                "pre_prompt": 1,
                "pre_tool": 1,
                "post_tool": 1,
                "post_prompt": 1,
            },
        )
        self.assertEqual(
            state.hook_state["extension.result_guidance.pending_query"],
            "",
        )


@tool(name="search")
def _search(
    query: Annotated[str, ToolArg("A concise evidence query.")],
    topk: Annotated[int, ToolArg("Number of passages.", minimum=1)] = 5,
) -> ToolResult:
    """Return one synthetic passage."""

    del query, topk
    return ToolResult(name="search", content="synthetic passage")


def _build_prompt(root: Path, entrypoint: str):
    spec = ComponentSpec(
        instance_id="prompt",
        entrypoint=entrypoint,
        config={},
        evolution_policy=EvolutionPolicy.FIXED,
    )
    factory = load_factory(root, spec)
    return factory(
        {},
        PluginContext(plugins_root=root),
        ToolSet([CallableTool.from_callable(_search)]),
    )


def _build_reason_in_documents_hook():
    entrypoint = "extensions/reason_in_documents/plugin.py:build"
    config = {"max_history_chars": 8000, "max_document_chars": 16000}
    spec = ComponentSpec(
        instance_id="reason_in_documents",
        entrypoint=entrypoint,
        config=config,
        evolution_policy=EvolutionPolicy.FIXED,
    )
    factory = load_factory(O1_ROOT, spec)
    return factory(config, PluginContext(plugins_root=O1_ROOT))


def _build_manifest_hooks(root: Path):
    manifest = load_manifest(root)
    hooks = []
    for spec in manifest.extensions:
        factory = load_factory(root, spec)
        produced = factory(dict(spec.config), PluginContext(plugins_root=root))
        hooks.extend(
            [produced] if not isinstance(produced, (tuple, list)) else produced
        )
    return tuple(hooks)
