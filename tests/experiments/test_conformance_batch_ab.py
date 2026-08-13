"""Shadow Conformance batch view tests."""

from __future__ import annotations

import unittest

from experiments.teacher_query_views.conformance import (
    ShadowConformanceBatch,
    compact_reference_observations,
    validate_shadow_batch,
)


class ShadowConformanceBatchTest(unittest.TestCase):
    def test_compact_reference_keeps_effect_and_removes_patch_text(self) -> None:
        observations = compact_reference_observations(
            [
                {
                    "trial_ref": "trial_001",
                    "phase_plan": [
                        {
                            "phase": "post_tool",
                            "max_activations": 1,
                            "instruction": "case-specific instruction",
                        }
                    ],
                    "activation_counts": {"post_tool": 1},
                    "phase_effects": [
                        {
                            "phase": "post_tool",
                            "action_kind": "apply_context_patch",
                            "modified": True,
                            "next_model_decision": {
                                "kind": "tool_call",
                                "tool_name": "search",
                            },
                        }
                    ],
                    "context_changes": [
                        {
                            "phase": "post_tool",
                            "action": {
                                "kind": "apply_context_patch",
                                "reason": "case-specific reason",
                            },
                            "model_input_change": {
                                "before_count": 4,
                                "after_count": 5,
                                "changed_blocks": [
                                    {
                                        "block_id": 5,
                                        "before": None,
                                        "after": {
                                            "role": "user",
                                            "content": "case-specific content",
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                }
            ]
        )

        self.assertEqual(observations[0]["trial_ref"], "trial_001")
        self.assertEqual(
            observations[0]["context_effects"][0]["changed_blocks"][0],
            {
                "block_id": 5,
                "change_kind": "inserted",
                "role_before": None,
                "role_after": "user",
            },
        )
        self.assertNotIn("case-specific", str(observations))

    def test_batch_requires_exact_replicate_order(self) -> None:
        batch = ShadowConformanceBatch.model_validate(
            {
                "findings": [
                    {
                        "replicate_id": "r000",
                        "verdict": "faithful",
                        "observed_phases": ["post_tool"],
                        "assessment": "The declared phase was faithful.",
                    },
                    {
                        "replicate_id": "r001",
                        "verdict": "faithful",
                        "observed_phases": ["post_tool"],
                        "assessment": "The declared phase was faithful.",
                    },
                ]
            }
        )
        validate_shadow_batch(
            batch,
            expected_replicate_ids=["r000", "r001"],
        )
        with self.assertRaises(ValueError):
            validate_shadow_batch(
                batch,
                expected_replicate_ids=["r001", "r000"],
            )


if __name__ == "__main__":
    unittest.main()
