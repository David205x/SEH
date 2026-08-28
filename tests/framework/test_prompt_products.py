"""Managed Hook Prompt Product runtime tests."""

from __future__ import annotations

import hashlib
import json
import unittest
from typing import Literal

from search_harness.framework import (
    AgentState,
    BaseHook,
    FinalDecision,
    HookPhase,
    HookPipeline,
    HookEditOperation,
    HookPromptInput,
    HookPromptProduct,
    InMemoryTrajectoryRecorder,
)
from search_harness.framework.agent.types import HookModelResponse


class _Backend:
    def __init__(self, output: str) -> None:
        self.output = output
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return HookModelResponse(raw_output=self.output)


class _PromptHook(BaseHook):
    def __init__(self, product: HookPromptProduct) -> None:
        super().__init__(
            hook_id="managed_prompt",
            phases=frozenset({HookPhase.PRE_FINAL}),
            model_profiles=frozenset({"student"}),
            max_model_calls_per_invocation=1,
        )
        self.product = product
        self.outputs = []

    def handle(self, context) -> None:
        self.outputs.append(context.call_prompt_product(self.product))


class HookPromptProductTest(unittest.TestCase):
    def test_preserves_exact_prompt_text(self) -> None:
        prompt = "\nReturn one label.\n"

        product = HookPromptProduct(
            product_ref="hook_prompt_test",
            phase="pre_final",
            task_kind="decision",
            inputs=(HookPromptInput("question", ("core.question",)),),
            prompt=prompt,
            thinking_mode="disabled",
            response_adapter="tri_label",
            task_digest="1" * 64,
            input_projection_digest="2" * 64,
            prompt_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        )

        self.assertEqual(product.prompt, prompt)

    def test_calls_exact_prompt_on_current_state_projection(self) -> None:
        prompt = "Return exactly positive, negative, or uncertain."
        product = HookPromptProduct(
            product_ref="hook_prompt_test",
            phase="pre_final",
            task_kind="decision",
            inputs=(
                HookPromptInput("question", ("core.question",)),
                HookPromptInput("candidate", ("stage.final_decision",)),
            ),
            prompt=prompt,
            thinking_mode="enabled",
            response_adapter="tri_label",
            task_digest="1" * 64,
            input_projection_digest="2" * 64,
            prompt_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        )
        backend = _Backend("positive")
        hook = _PromptHook(product)
        pipeline = HookPipeline((hook,), model_backend=backend)
        state = AgentState(question="Who?", max_steps=2, step=1)
        store = pipeline.begin_run(state)

        pipeline.run_phase(
            HookPhase.PRE_FINAL,
            state=state,
            store=store,
            trajectory=InMemoryTrajectoryRecorder(),
            stage_values={"final_decision": FinalDecision.accept("Ada")},
        )

        self.assertEqual(hook.outputs[0].value, "positive")
        request = backend.requests[0]
        self.assertEqual(request.thinking_mode, "enabled")
        self.assertEqual(request.model_input.messages[0].content, prompt)
        projection = json.loads(
            request.model_input.messages[1].content.split("\n", maxsplit=1)[1]
        )
        values = {
            item["name"]: item["sources"][0]["value"]
            for item in projection["inputs"]
        }
        self.assertEqual(values["question"], "Who?")
        self.assertEqual(values["candidate"]["answer"], "Ada")

    def test_invalid_decision_output_normalizes_to_uncertain(self) -> None:
        prompt = "Return one label."
        product = HookPromptProduct(
            product_ref="hook_prompt_test",
            phase="pre_final",
            task_kind="decision",
            inputs=(HookPromptInput("question", ("core.question",)),),
            prompt=prompt,
            thinking_mode="disabled",
            response_adapter="tri_label",
            task_digest="1" * 64,
            input_projection_digest="2" * 64,
            prompt_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        )
        backend = _Backend("maybe")
        hook = _PromptHook(product)
        pipeline = HookPipeline((hook,), model_backend=backend)
        state = AgentState(question="Who?", max_steps=2, step=1)

        pipeline.run_phase(
            HookPhase.PRE_FINAL,
            state=state,
            store=pipeline.begin_run(state),
            trajectory=InMemoryTrajectoryRecorder(),
            stage_values={"final_decision": FinalDecision.accept("Ada")},
        )

        self.assertEqual(hook.outputs[0].value, "uncertain")

    def test_generation_returns_trimmed_text(self) -> None:
        prompt = "Rewrite the selected block."
        product = _product(
            prompt=prompt,
            task_kind="generation",
            response_adapter="raw_text",
        )
        backend = _Backend("  concise rewrite  ")
        hook = _PromptHook(product)
        pipeline = HookPipeline((hook,), model_backend=backend)
        state = AgentState(question="Who?", max_steps=2, step=1)

        pipeline.run_phase(
            HookPhase.PRE_FINAL,
            state=state,
            store=pipeline.begin_run(state),
            trajectory=InMemoryTrajectoryRecorder(),
            stage_values={"final_decision": FinalDecision.accept("Ada")},
        )

        self.assertEqual(hook.outputs[0].value, "concise rewrite")

    def test_structured_edit_returns_validated_operations(self) -> None:
        prompt = "Return structural edit operations."
        product = _product(
            prompt=prompt,
            task_kind="structured_edit",
            response_adapter="structured_edit",
        )
        backend = _Backend(
            json.dumps(
                {
                    "operations": [
                        {
                            "operation": "replace",
                            "block_id": 2,
                            "content": "x",
                        },
                        {"operation": "delete", "block_id": 3},
                    ]
                }
            )
        )
        hook = _PromptHook(product)
        pipeline = HookPipeline((hook,), model_backend=backend)
        state = AgentState(question="Who?", max_steps=2, step=1)

        pipeline.run_phase(
            HookPhase.PRE_FINAL,
            state=state,
            store=pipeline.begin_run(state),
            trajectory=InMemoryTrajectoryRecorder(),
            stage_values={"final_decision": FinalDecision.accept("Ada")},
        )

        self.assertEqual(
            hook.outputs[0].value,
            (
                HookEditOperation(
                    operation="replace",
                    block_id=2,
                    content="x",
                ),
                HookEditOperation(operation="delete", block_id=3),
            ),
        )

    def test_structured_edit_rejects_non_numeric_block_id(self) -> None:
        prompt = "Return structural edit operations."
        product = _product(
            prompt=prompt,
            task_kind="structured_edit",
            response_adapter="structured_edit",
        )
        backend = _Backend(
            '{"operations":[{"operation":"delete","block_id":"3"}]}'
        )
        hook = _PromptHook(product)
        pipeline = HookPipeline((hook,), model_backend=backend)
        state = AgentState(question="Who?", max_steps=2, step=1)

        pipeline.run_phase(
            HookPhase.PRE_FINAL,
            state=state,
            store=pipeline.begin_run(state),
            trajectory=InMemoryTrajectoryRecorder(),
            stage_values={"final_decision": FinalDecision.accept("Ada")},
        )

        self.assertIsNone(hook.outputs[0].value)


def _product(
    *,
    prompt: str,
    task_kind: Literal["generation", "structured_edit"],
    response_adapter: Literal["raw_text", "structured_edit"],
) -> HookPromptProduct:
    return HookPromptProduct(
        product_ref="hook_prompt_test",
        phase="pre_final",
        task_kind=task_kind,
        inputs=(HookPromptInput("question", ("core.question",)),),
        prompt=prompt,
        thinking_mode="disabled",
        response_adapter=response_adapter,
        task_digest="1" * 64,
        input_projection_digest="2" * 64,
        prompt_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )


if __name__ == "__main__":
    unittest.main()
