"""Shadow Mechanism Distiller 协议与输入目录测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from search_harness.evolution.research.roles.contracts import (
    ShadowDistillationResult,
)
from search_harness.evolution.research.shadow_task_inputs import (
    project_shadow_task_inputs,
    shadow_input_projection_digest,
    shadow_task_source_catalog,
)

from experiments.validate_shadow_mechanism_distiller import (
    _shadow_provenance,
)


class ShadowDistillationContractTest(unittest.TestCase):
    def test_accepts_multiphase_generation_and_decision_mechanism(self) -> None:
        result = ShadowDistillationResult.model_validate(_valid_result())

        self.assertEqual(result.outcome, "distilled")
        self.assertIsNotNone(result.mechanism)
        assert result.mechanism is not None
        self.assertEqual(
            [phase.task.kind for phase in result.mechanism.phases],
            ["generation", "decision"],
        )

    def test_rejects_distilled_result_without_mechanism(self) -> None:
        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(
                {
                    "outcome": "distilled",
                    "mechanism": None,
                    "obligation": None,
                }
            )

    def test_rejects_non_success_result_with_mechanism(self) -> None:
        value = _valid_result()
        value["outcome"] = "needs_evidence"
        value["obligation"] = "Collect one independent negative Trial."

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)


class ShadowTaskInputProjectionTest(unittest.TestCase):
    def test_catalog_marks_core_global_and_stage_phase_local(self) -> None:
        catalog = shadow_task_source_catalog()["sources"]

        self.assertEqual(catalog["core.question"]["phases"], "all")
        self.assertNotIn("core.final_answer", catalog)
        self.assertEqual(
            catalog["stage.final_decision"]["phases"],
            ["pre_final"],
        )
        self.assertIn(
            "parsed final answer",
            catalog["stage.final_decision"]["description"],
        )
        self.assertIn(
            "use stage.final_decision",
            catalog["core.parsed_outputs"]["description"],
        )

    def test_projection_digest_is_stable_and_order_sensitive(self) -> None:
        inputs = [
            {"name": "question", "sources": ["core.question"]},
            {"name": "candidate", "sources": ["stage.final_decision"]},
        ]

        first = shadow_input_projection_digest(
            phase="pre_final",
            inputs=inputs,
        )
        repeated = shadow_input_projection_digest(
            phase="pre_final",
            inputs=inputs,
        )
        reversed_digest = shadow_input_projection_digest(
            phase="pre_final",
            inputs=list(reversed(inputs)),
        )

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, reversed_digest)

    def test_projects_source_values_into_fixed_json_view(self) -> None:
        values = {
            "core.question": "Who won?",
            "state.plan": "Search both entities.",
        }

        projected = project_shadow_task_inputs(
            phase="pre_final",
            inputs=[
                {"name": "question", "sources": ["core.question"]},
                {"name": "plan", "sources": ["state.plan"]},
            ],
            get_state=values.__getitem__,
            state_types={"plan": "str"},
        )

        self.assertEqual(projected["phase"], "pre_final")
        self.assertEqual(
            projected["inputs"][1]["sources"][0]["value"],
            "Search both entities.",
        )
        self.assertEqual(len(projected["projection_digest"]), 64)

    def test_provenance_binds_exact_mechanism(self) -> None:
        mechanism = _valid_result()["mechanism"]
        source = {
            "path": Path("source.json"),
            "resources": SimpleNamespace(
                trial_files=[Path("trial_001.json")]
            ),
        }

        first = _shadow_provenance(
            source=source,
            role_artifact=Path("role.json"),
            mechanism=mechanism,
        )
        changed = dict(mechanism)
        changed["constraints"] = ["changed"]
        second = _shadow_provenance(
            source=source,
            role_artifact=Path("role.json"),
            mechanism=changed,
        )

        self.assertNotEqual(
            first["mechanism_digest"],
            second["mechanism_digest"],
        )

    def test_rejects_null_obligation_string_on_non_success(self) -> None:
        value = {
            "outcome": "needs_evidence",
            "mechanism": None,
            "obligation": "null",
        }

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_noncanonical_noop_fallback(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][0]["fallback"]["default"] = (
            "Leave everything unchanged."
        )

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_redundant_fallback_override(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][0]["fallback"]["uncertain"] = (
            "continue_without_change"
        )

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_stage_source_unavailable_at_phase(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][0]["task"]["inputs"][0][
            "sources"
        ] = ["stage.final_decision"]

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_terminal_final_answer_as_task_source(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][1]["task"]["inputs"][1][
            "sources"
        ] = ["core.final_answer"]

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_terminal_final_answer_in_guard(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][1]["guards"] = [
            "core.final_answer is present"
        ]

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_undeclared_state_source(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][1]["task"]["inputs"][0][
            "sources"
        ] = ["state.missing"]

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_generation_action_without_output_binding(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][0]["on_success"] = (
            "Append one generated plan."
        )

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_state_reference_missing_from_declarations(self) -> None:
        value = _valid_result()
        value["mechanism"]["phases"][0]["guards"] = [
            "state.missing is false"
        ]

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_constraint_state_reference_without_declaration(
        self,
    ) -> None:
        value = _valid_result()
        value["mechanism"]["constraints"] = [
            "Record changes to state.missing."
        ]

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)

    def test_rejects_declared_but_unused_state(self) -> None:
        value = _valid_result()
        value["mechanism"]["state"].append(
            {"name": "unused", "value_type": "bool", "initial": False}
        )

        with self.assertRaises(ValidationError):
            ShadowDistillationResult.model_validate(value)


def _valid_result() -> dict[str, object]:
    return {
        "outcome": "distilled",
        "mechanism": {
            "effect": {
                "kind": "behavioral_intermediate",
                "success": "The Student follows a generated plan before answering.",
            },
            "phases": [
                {
                    "phase": "post_prompt",
                    "guards": ["state.plan is empty"],
                    "task": {
                        "kind": "generation",
                        "evaluator": "hook_model",
                        "inputs": [
                            {
                                "name": "task",
                                "sources": ["core.question"],
                            }
                        ],
                        "output_name": "generated_plan",
                        "requirement": "Generate a plan without answer facts.",
                    },
                    "on_success": (
                        "Store generated_plan in state.plan and append it to the "
                        "Student context."
                    ),
                    "fallback": {
                        "default": "continue_without_change",
                        "uncertain": None,
                        "exhausted": None,
                    },
                    "activation_limit": 1,
                },
                {
                    "phase": "pre_final",
                    "guards": ["state.plan is non-empty"],
                    "task": {
                        "kind": "decision",
                        "evaluator": "hook_model",
                        "inputs": [
                            {
                                "name": "plan",
                                "sources": ["state.plan"],
                            },
                            {
                                "name": "candidate",
                                "sources": ["stage.final_decision"],
                            },
                        ],
                        "positive": "A required plan step is missing.",
                        "negative": "All required plan steps are complete.",
                        "uncertain": "The evidence cannot establish completion.",
                    },
                    "on_success": "Defer the final answer once with fixed feedback.",
                    "fallback": {
                        "default": "continue_without_change",
                        "uncertain": None,
                        "exhausted": None,
                    },
                    "activation_limit": 1,
                },
            ],
            "state": [
                {
                    "name": "plan",
                    "value_type": "str",
                    "initial": "",
                }
            ],
            "constraints": ["Do not inject answer facts."],
        },
        "obligation": None,
    }


if __name__ == "__main__":
    unittest.main()
