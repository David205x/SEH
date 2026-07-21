from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.adapter.compiler import (
    CompilerContext,
    CompilerResult,
    apply_compiler_result,
    build_compiler_loop,
    run_compiler,
)
from search_harness.core import ModelInput
from search_harness.registry import build_harness
from search_harness.versioning import HarnessSnapshot, HarnessVersionStore


COMPILER_PLUGINS_ROOT = (
    Path(__file__).parents[3] / "harness_templates" / "adapter" / "compiler" / "baseline" / "plugins"
)


class SequenceModel:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.inputs: list[ModelInput] = []

    def generate(self, model_input: ModelInput) -> str:
        self.inputs.append(model_input)
        return self.outputs.pop(0)


class CompilerTest(TestCase):
    def test_protocol_guard_defers_malformed_final_json(self) -> None:
        """验证 Compiler 在同一对话内修正被 Markdown 包裹的结果 JSON。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            context = _make_context(
                root, HarnessSnapshot.from_directory(_make_actor_plugins(root))
            )
            valid = (
                '<final_answer>{"summary":"Need evidence","edits":[],'
                '"clarification":"Specify the activation condition."}</final_answer>'
            )
            model = SequenceModel(
                [
                    '<final_answer>```json\n{"summary":"bad"}\n```</final_answer>',
                    valid,
                ]
            )
            loop = build_compiler_loop(
                compiler_context=context,
                plugins_root=COMPILER_PLUGINS_ROOT,
                model=model,
                max_steps=2,
            )

            run, result = run_compiler(loop, "Compile the proposal.")

        self.assertEqual(run.status.value, "completed")
        self.assertEqual(len(model.inputs), 2)
        self.assertIn("violates its required result schema", model.inputs[1].messages[-1].content)
        self.assertEqual(result.clarification, "Specify the activation condition.")

    def test_plugins_assemble_and_return_clarification(self) -> None:
        """Verifies the plugins assemble and return clarification contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plugins_root = _make_actor_plugins(root)
            context = _make_context(root, HarnessSnapshot.from_directory(plugins_root))
            components = build_harness(
                COMPILER_PLUGINS_ROOT, runtime_context=context
            )
            model = SequenceModel(
                [
                    '<final_answer>{"summary":"Need an effect boundary",'
                    '"edits":[],"clarification":"Specify the target lifecycle phase."}'
                    "</final_answer>"
                ]
            )
            loop = build_compiler_loop(
                compiler_context=context,
                plugins_root=COMPILER_PLUGINS_ROOT,
                model=model,
                max_steps=2,
            )

            run, result = run_compiler(loop, "Compile the proposal.")

        self.assertEqual(
            [definition.name for definition in components.tools.definitions],
            [
                "list_harness_files",
                "read_harness_file",
                "get_harness_component",
                "get_hook_authoring_guide",
            ],
        )
        self.assertEqual(run.status.value, "completed")
        self.assertIsNotNone(result.clarification)
        self.assertIn("Every new model-created component", model.inputs[0].messages[0].content)
        self.assertIn("context.call_model", model.inputs[0].messages[0].content)

    def test_exposes_versioned_model_inference_authoring_guide(self) -> None:
        """Verifies the exposes versioned model inference authoring guide contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            context = _make_context(
                root, HarnessSnapshot.from_directory(_make_actor_plugins(root))
            )

            guide = context.get_hook_authoring_guide("model_inference")

        self.assertEqual(guide["api_version"], 3)
        self.assertEqual(guide["allowed_profiles"], ["student"])
        self.assertIn("context.call_model", guide["example"])

    def test_exposes_exact_hook_implementation_contract(self) -> None:
        """验证 Compiler 可读取合法 import、BaseHook 和 build 工厂骨架。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            context = _make_context(
                root, HarnessSnapshot.from_directory(_make_actor_plugins(root))
            )

            guide = context.get_hook_authoring_guide("implementation")

        self.assertIn("HookContext", guide["legal_core_imports"])
        self.assertIn("FinalDecisionAction", guide["legal_core_imports"])
        self.assertIn("def build(config: dict[str, Any], context: Any)", guide["minimal_plugin"])
        self.assertIn("HookSpec", guide["forbidden_guesses"])
        self.assertEqual(
            guide["runtime_types"]["FinalDecision"]["fields"],
            ["action", "answer", "feedback"],
        )
        self.assertIn(
            "error", guide["runtime_types"]["HookModelResponse"]["forbidden_guesses"]
        )

    def test_lifecycle_guide_explains_phase_local_stage_state(self) -> None:
        """验证 Compiler 能读取跨 phase 状态传递的权威约束。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            context = _make_context(
                root, HarnessSnapshot.from_directory(_make_actor_plugins(root))
            )

            guide = context.get_hook_authoring_guide("lifecycle")

        rules = " ".join(guide["rules"])
        self.assertIn("Never read stage.model_input from POST_TOOL", rules)
        self.assertIn("extension.* or shared.*", rules)

    def test_exposes_final_decision_authoring_guide(self) -> None:
        """Verifies the Compiler exposes final-decision Hook authoring guidance."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            context = _make_context(
                root, HarnessSnapshot.from_directory(_make_actor_plugins(root))
            )

            guide = context.get_hook_authoring_guide("final_decision")

        self.assertEqual(guide["stage_key"], "stage.final_decision")
        self.assertIn("FinalDecision.defer", guide["actions"]["defer"])
        self.assertIn("cannot be changed back", guide["rules"][2])

    def test_applies_one_transaction_and_validates_without_accepting(self) -> None:
        """Verifies the applies one transaction and validates without accepting contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plugins_root = _make_actor_plugins(root)
            store = HarnessVersionStore(root / "store")
            baseline = store.initialize(plugins_root)
            session = store.start_iteration(parent_version=baseline.version_id)
            result = CompilerResult.from_dict(
                {
                    "summary": "Refine mutable hook",
                    "edits": [
                        {
                            "operation": "write",
                            "path": "extensions/review/plugin.py",
                            "content": "def build(config, context):\n    return ()\n",
                        }
                    ],
                    "clarification": None,
                }
            )

            validation = apply_compiler_result(session, result)
            assert validation is not None
            self.assertTrue(validation.passed)
            self.assertEqual(store.list_iterations()[0].patch_count, 1)
            self.assertEqual(store.list_iterations()[0].status, "pending")
            self.assertEqual(len(store.list_versions()), 1)

    def test_rejects_direction_without_required_evidence(self) -> None:
        """验证 Compiler 拒绝缺失行为证据的问题方向。"""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plugins_root = _make_actor_plugins(root)
            snapshot = HarnessSnapshot.from_directory(plugins_root)
            intervention_log = _write_intervention_log(
                root, snapshot, {"problem": "Too little evidence"}
            )

            with self.assertRaisesRegex(ValueError, "lacks required evidence"):
                CompilerContext.from_intervention_log(
                    intervention_log=intervention_log,
                    parent=snapshot,
                )

    def test_loads_supported_intervention_evidence_into_context(self) -> None:
        """验证 Compiler 读取受支持策略、代表 trial 与验证账本。"""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plugins_root = _make_actor_plugins(root)
            snapshot = HarnessSnapshot.from_directory(plugins_root)
            intervention_log = _write_intervention_log(
                root, snapshot, _direction()
            )

            context = CompilerContext.from_intervention_log(
                intervention_log=intervention_log,
                parent=snapshot,
            )
            initial = context.initial_context()

        self.assertEqual(context.direction_index, 0)
        self.assertEqual(initial["problem_direction"]["problem"], "Premature completion")
        self.assertEqual(initial["selected_trial"]["trial_id"], "trial_001")
        self.assertEqual(len(initial["validation_trials"]), 1)

    def test_rejects_critic_log_bound_to_a_different_parent(self) -> None:
        """Verifies the rejects critic log bound to a different parent contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot = HarnessSnapshot.from_directory(_make_actor_plugins(root))
            intervention_log = _write_intervention_log(
                root,
                snapshot,
                _direction(),
                harness_version="harness_v0009",
            )

            with self.assertRaisesRegex(ValueError, "parent mismatch"):
                CompilerContext.from_intervention_log(
                    intervention_log=intervention_log,
                    parent=snapshot,
                )


def _make_context(root: Path, snapshot: HarnessSnapshot) -> CompilerContext:
    intervention_log = _write_intervention_log(root, snapshot, _direction())
    return CompilerContext.from_intervention_log(
        intervention_log=intervention_log,
        parent=snapshot,
    )


def _direction() -> dict[str, object]:
    return {
        "problem": "Premature completion",
        "observed_pattern": "Repeated failures occur after tool results.",
        "excluded_causes": ["retriever outage"],
        "desired_behavior": "Continue until requested evidence is covered.",
        "success_criteria": ["More correct multi-hop answers"],
        "constraints": ["Avoid unconditional extra searches"],
    }


def _write_intervention_log(
    root: Path,
    snapshot: HarnessSnapshot,
    direction: dict[str, object],
    *,
    harness_version: str | None = None,
) -> Path:
    critic_log = root / "critic.json"
    critic_log.write_text(
        json.dumps(
            {
                "inputs": _critic_inputs(snapshot),
                "critic_result": {
                    "analysis": "Generalized analysis.",
                    "problem_directions": [direction],
                }
            }
        ),
        encoding="utf-8",
    )
    intervention_log = root / "coordinator.json"
    inputs = _critic_inputs(snapshot)
    inputs["harness_version"] = harness_version or snapshot.version_id
    intervention_log.write_text(
        json.dumps(
            {
                "direction_source": {
                    "critic_log": str(critic_log),
                    "direction_index": 0,
                    "critic_analysis": "Generalized analysis.",
                    "problem_direction": direction,
                    "critic_inputs": inputs,
                },
                "coordinator_result": {
                    "analysis": "Validated across cases.",
                    "verdict": "supported",
                    "selected_trial_id": "trial_001",
                    "recommendation": "Compile the validated behavior.",
                },
                "trials": [
                    {
                        "trial_id": "trial_001",
                        "status": "completed",
                        "hook_guidance": {"post_tool": "Continue gathering evidence."},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return intervention_log


def _critic_inputs(snapshot: HarnessSnapshot) -> dict[str, object]:
    return {
        "harness_version": snapshot.version_id,
        "harness_digest": snapshot.digest,
        "iteration": None,
    }


def _make_actor_plugins(root: Path) -> Path:
    plugins_root = root / "actor-plugins"
    prompt_dir = plugins_root / "prompts" / "base"
    extension_dir = plugins_root / "extensions" / "review"
    prompt_dir.mkdir(parents=True)
    extension_dir.mkdir(parents=True)
    (prompt_dir / "plugin.py").write_text(
        "from search_harness.core import ChatMessage, ModelInput\n"
        "class Prompt:\n"
        "    def build(self, state):\n"
        "        message = ChatMessage(role='user', content=state.question)\n"
        "        return ModelInput.from_messages([message])\n"
        "def build(config, context, tools):\n"
        "    return Prompt()\n",
        encoding="utf-8",
    )
    (extension_dir / "plugin.py").write_text(
        "def build(config, context):\n    return []\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "harness_id": "compiler-test",
        "tools": [],
        "prompt": {
            "instance_id": "base",
            "entrypoint": "prompts/base/plugin.py:build",
            "config": {},
            "evolution_policy": "fixed",
        },
        "extensions": [
            {
                "instance_id": "review",
                "entrypoint": "extensions/review/plugin.py:build",
                "config": {},
                "evolution_policy": "mutable",
            }
        ],
    }
    (plugins_root / "harness.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return plugins_root
