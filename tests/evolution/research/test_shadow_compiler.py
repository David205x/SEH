"""Shadow Compiler binding and packet tests."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from search_harness.evolution.research.resources.stores import (
    CompilerResourceConfig,
    CompilerWorkspaceStore,
)
from search_harness.evolution.research.roles.contracts import ShadowCompilerInput
from search_harness.evolution.research.shadow_compiler import (
    build_managed_prompt_products,
    build_shadow_compiler_capability_packet,
)
from search_harness.evolution.research.shadow_task_inputs import (
    shadow_input_projection_digest,
    shadow_phase_task_digest,
)


class ShadowCompilerTest(unittest.TestCase):
    def test_packet_exposes_binding_without_prompt_text(self) -> None:
        compiler_input = ShadowCompilerInput.model_validate(_compiler_input())

        managed = build_managed_prompt_products(compiler_input)
        packet = build_shadow_compiler_capability_packet(compiler_input)

        self.assertEqual(set(managed), {"pre_final"})
        reference = managed["pre_final"]["product_ref"]
        self.assertEqual(
            packet["selection"]["managed_hook_prompts"]["pre_final"],
            reference,
        )
        rendered = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn(compiler_input.prompt_products[0].prompt, rendered)
        symbols = {item.get("symbol") for item in packet["contracts"]}
        self.assertIn("HookContext.call_prompt_product", symbols)

    def test_store_materializes_and_protects_prompt_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_parent(root)
            compiler_input = ShadowCompilerInput.model_validate(_compiler_input())
            store = CompilerWorkspaceStore.load(
                CompilerResourceConfig(parent_template_root=root)
            )
            store.bind_managed_prompt_products(
                build_managed_prompt_products(compiler_input)
            )
            store.workspace.add_extension(
                instance_id="managed_hook",
                files={
                    "component.py": (
                        "from .managed_prompt_products import PROMPT_PRODUCTS\n"
                        "def build(config, context):\n"
                        "    return context.call_prompt_product(PROMPT_PRODUCTS['pre_final'])\n"
                    )
                },
            )

            result = store.materialize_managed_prompt_products(
                instance_id="managed_hook"
            )

            path = result["path"]
            self.assertIn("managed_prompt_products.py", path)
            with self.assertRaisesRegex(ValueError, "not model-readable"):
                store.read_file(path)
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.write_file(path=path, content="changed")

    def test_store_rejects_direct_model_call_beside_managed_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_parent(root)
            compiler_input = ShadowCompilerInput.model_validate(_compiler_input())
            store = CompilerWorkspaceStore.load(
                CompilerResourceConfig(parent_template_root=root)
            )
            store.bind_managed_prompt_products(
                build_managed_prompt_products(compiler_input)
            )
            store.workspace.add_extension(
                instance_id="managed_hook",
                files={
                    "component.py": (
                        "from .managed_prompt_products import PROMPT_PRODUCTS\n"
                        "def build(config, context):\n"
                        "    context.call_model(HookModelRequest())\n"
                        "    return context.call_prompt_product("
                        "PROMPT_PRODUCTS['pre_final'])\n"
                    )
                },
            )
            store.materialize_managed_prompt_products(
                instance_id="managed_hook"
            )

            errors = store._managed_prompt_binding_errors()

            self.assertTrue(
                any("direct Hook model call" in error for error in errors)
            )

    def test_store_rejects_copied_managed_prompt_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_parent(root)
            compiler_input = ShadowCompilerInput.model_validate(_compiler_input())
            store = CompilerWorkspaceStore.load(
                CompilerResourceConfig(parent_template_root=root)
            )
            store.bind_managed_prompt_products(
                build_managed_prompt_products(compiler_input)
            )
            prompt = compiler_input.prompt_products[0].prompt
            store.workspace.add_extension(
                instance_id="managed_hook",
                files={
                    "component.py": (
                        "from .managed_prompt_products import PROMPT_PRODUCTS\n"
                        f"COPIED = {prompt!r}\n"
                        "def build(config, context):\n"
                        "    return context.call_prompt_product("
                        "PROMPT_PRODUCTS['pre_final'])\n"
                    )
                },
            )
            store.materialize_managed_prompt_products(
                instance_id="managed_hook"
            )

            errors = store._managed_prompt_binding_errors()

            self.assertTrue(
                any("copies program-managed" in error for error in errors)
            )

    def test_shadow_packet_blocks_requery_and_caps_missing_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_parent(root)
            compiler_input = ShadowCompilerInput.model_validate(_compiler_input())
            store = CompilerWorkspaceStore.load(
                CompilerResourceConfig(parent_template_root=root)
            )
            packet = build_shadow_compiler_capability_packet(compiler_input)
            store.bind_capability_packet(packet)

            repeated = store.query_hook_api("StateRef")
            missing = [
                store.query_hook_api(f"missing_symbol_{index}")
                for index in range(1, 5)
            ]

            self.assertEqual(
                repeated["reason"],
                "already_in_capability_packet",
            )
            self.assertEqual(store.exact_query_budget, 3)
            self.assertEqual(
                missing[-1]["reason"],
                "query_budget_exhausted",
            )


def _compiler_input() -> dict[str, object]:
    task = {
        "kind": "decision",
        "evaluator": "hook_model",
        "inputs": [
            {"name": "question", "sources": ["core.question"]},
            {
                "name": "candidate",
                "sources": ["stage.final_decision"],
            },
        ],
        "positive": "The answer lacks evidence.",
        "negative": "The answer has direct evidence.",
        "uncertain": "The evidence cannot decide.",
    }
    prompt = "Return exactly positive, negative, or uncertain."
    return {
        "mechanism": {
            "effect": {
                "kind": "behavioral_intermediate",
                "success": "The Student searches again.",
            },
            "phases": [
                {
                    "phase": "pre_final",
                    "guards": ["stage.final_decision is present"],
                    "task": task,
                    "on_success": "Replace stage.final_decision with defer.",
                    "fallback": {
                        "default": "continue_without_change",
                        "uncertain": None,
                        "exhausted": None,
                    },
                    "activation_limit": 1,
                }
            ],
            "state": [],
            "constraints": [],
        },
        "prompt_products": [
            {
                "phase": "pre_final",
                "task_digest": shadow_phase_task_digest(
                    phase="pre_final",
                    task=task,
                ),
                "input_projection_digest": shadow_input_projection_digest(
                    phase="pre_final",
                    inputs=task["inputs"],
                ),
                "prompt": prompt,
                "thinking_mode": "enabled",
                "response_adapter": "tri_label",
            }
        ],
    }


def _write_parent(root: Path) -> None:
    (root / "prompt").mkdir(parents=True)
    (root / "output").mkdir()
    (root / "prompt" / "component.py").write_text(
        "def build(config, context, tools):\n    return object()\n",
        encoding="utf-8",
    )
    (root / "output" / "component.py").write_text(
        "def build(config, context):\n    return object()\n",
        encoding="utf-8",
    )
    (root / "harness.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "harness_id": "test",
                "tools": [],
                "prompt": {
                    "instance_id": "prompt",
                    "entrypoint": "prompt/component.py:build",
                    "config": {},
                },
                "output": {
                    "instance_id": "output",
                    "entrypoint": "output/component.py:build",
                    "config": {},
                },
                "extensions": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "evolution.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "harness_id": "test",
                "components": {"prompt": "fixed", "output": "fixed"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
