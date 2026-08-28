"""Shadow Conformance fragment contracts and mechanism adapter tests。"""

from __future__ import annotations

import unittest

from experiments.run_shadow_candidate_conformance import _compiler_candidate
from search_harness.evolution.control.conformance_effects import (
    _mechanism_effect_goal,
    _mechanism_phases,
)
from search_harness.evolution.research.conformance import (
    render_conformance_batch_input,
)
from search_harness.evolution.research.roles.contracts import (
    ShadowConformanceReviewerInput,
    ShadowMechanismSpec,
)


class ShadowConformanceFragmentTest(unittest.TestCase):
    def test_shadow_input_renders_without_legacy_mechanism_conversion(self) -> None:
        mechanism = ShadowMechanismSpec.model_validate(_mechanism())
        role_input = ShadowConformanceReviewerInput(
            mechanism=mechanism,
            trial_refs=["trial_001"],
            reference_observations=[{"trial_ref": "trial_001"}],
            example_id="example_001",
            candidate_trajectory_views=[
                {
                    "replicate_id": "r000",
                    "candidate_trajectory_view": {"events": []},
                }
            ],
        )

        rendered = render_conformance_batch_input(
            role_input.model_dump(mode="json")
        )

        self.assertIn('"kind":"behavioral_intermediate"', rendered)
        self.assertIn('"phase":"pre_final"', rendered)
        self.assertNotIn("phase_rules", rendered)
        self.assertEqual(_mechanism_effect_goal(mechanism), "behavioral_intermediate")
        self.assertEqual(_mechanism_phases(mechanism), {"pre_final"})

    def test_compiler_candidate_accepts_role_or_extracted_artifact(self) -> None:
        candidate = {
            "candidate_digest": "a" * 64,
            "changed_files": {"harness.json": "{}"},
        }

        self.assertEqual(_compiler_candidate(candidate), candidate)
        self.assertEqual(
            _compiler_candidate(
                {"resource_artifacts": {"compiler_candidate": candidate}}
            ),
            candidate,
        )


def _mechanism() -> dict[str, object]:
    return {
        "effect": {
            "kind": "behavioral_intermediate",
            "success": "The Student searches before answering again.",
        },
        "phases": [
            {
                "phase": "pre_final",
                "guards": ["stage.final_decision is accepted"],
                "task": {
                    "kind": "decision",
                    "evaluator": "hook_model",
                    "inputs": [
                        {
                            "name": "candidate",
                            "sources": ["stage.final_decision"],
                        }
                    ],
                    "positive": "The candidate lacks required evidence.",
                    "negative": "The candidate has required evidence.",
                    "uncertain": "The evidence cannot decide.",
                },
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
    }


if __name__ == "__main__":
    unittest.main()
